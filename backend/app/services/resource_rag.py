"""V_2 학습 자료 RAG 검색. 기존 벡터 SELECT만 사용하고 DB에는 쓰지 않는다."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import math
from threading import Lock
from time import perf_counter
from weakref import WeakValueDictionary
from app import db
from app import regulation_embeddings as embeddings
from app.agents.resource_recommendations import RecommendationError, candidate_pools
from app.services import book_candidates, course_focus, resource_evidence

MODEL = embeddings.BGE_MODEL
DIMENSIONS = embeddings.BGE_DIMENSIONS
VERSION = 'resource-pgvector-rag/v36-shared-books'
PER_KIND = 6
COURSE_REVIEW = 20
FIELDS = ('id','title','provider','cost','hours','estimated','image','url','skills','content','curriculum')


def version_for(course=None):
    from app.services.crash_courses import is_crash, VERSION as CRASH_VERSION
    return VERSION + '/' + CRASH_VERSION if is_crash(course) else VERSION


def skill_query(project: dict, name: str, application: str | None) -> str:
    return json.dumps({'goal': project.get('goal'), 'skill': name,
                       **({'application': application} if application else {}),
                       'desiredCompetencies': project.get('desiredCompetencies'),
                       'projectSummary': project.get('projectSummary')}, ensure_ascii=False, sort_keys=True)


def _unscoped_book_query(project: dict, skill: dict) -> str:
    """코스 선택 전 공통 추천은 기존 학습자 맥락을 사용한다."""
    return json.dumps({
        'learnerKnowledge':project.get('learnerKnowledge') or {},
        'learningDirection':'이미 사용하는 기술의 입문 반복보다 프로젝트에 필요한 새 개념·심화·적용 중심',
        'projectGoal': str(project.get('goal') or '')[:500],
        'projectSummary': str(project.get('projectSummary') or '')[:2500],
        'desiredCompetencies': str(project.get('desiredCompetencies') or '')[:500],
        'skill': skill['name'], 'application': str(skill.get('application') or '')[:600],
        'course': {key: '' for key in ('id','name','reason','scope')},
    }, ensure_ascii=False, sort_keys=True)


def validate_vectors(vectors, count):
    if not isinstance(vectors, (list,tuple)) or len(vectors) != count:
        raise RecommendationError('자료 검색 임베딩 개수가 일치하지 않아요.')
    for vector in vectors:
        if (not isinstance(vector,(list,tuple)) or len(vector)!=DIMENSIONS or
            not all(isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) for value in vector) or
            not any(vector)):
            raise RecommendationError('자료 검색 임베딩은 유효한 BGE-M3 1024차원 벡터여야 해요.')
    return vectors


@lru_cache(maxsize=128)
def cached_vectors(texts: tuple[str,...]):
    return tuple(tuple(vector) for vector in validate_vectors(embeddings.embed(list(texts)),len(texts)))


_query_locks = WeakValueDictionary()
_query_locks_guard = Lock()


def _shared_vectors(texts):
    # 동시 요청이 같은 캐시 미스에서 임베딩을 여러 번 시작하는 일을 막는다.
    with _query_locks_guard:
        lock = _query_locks.setdefault(texts, Lock())
    with lock:
        return cached_vectors(texts)


def search_vectors(resource_type, ids, vector, limit, free_only, *, read=None):
    # 스킬·종류·사용 가능 여부는 ids에 반영하고, 최신 0원 조건도 LIMIT 이전에 적용한다.
    if not ids:return []
    read = read or db.all_
    return read("""SELECT e.resource_id, m.cost_won AS current_cost,
            1-(e.embedding <=> CAST(:query AS vector)) AS similarity
        FROM public.learning_resource_embeddings e
        JOIN growpath_bge_meta.inputs p ON p.kind=e.resource_type AND p.source_id=e.resource_id
            AND p.source_sha256=e.input_sha256 AND p.model_revision=:revision
        JOIN app_ext.resource_meta m ON m.resource_key =
            CASE WHEN e.resource_type='books' THEN 'book_' || e.resource_id ELSE e.resource_id END
        WHERE e.resource_type=:kind AND e.resource_id=ANY(:ids)
            AND e.embedding_model=:model AND e.dimensions=:dims AND e.embedding IS NOT NULL
            AND e.input_version='db-resource-fields-and-skill-links/v1'
            AND (NOT :free_only OR m.cost_won=0)
        ORDER BY e.embedding <=> CAST(:query AS vector), e.resource_id LIMIT :limit""",
        query=json.dumps(vector,allow_nan=False),kind=resource_type,ids=ids,model=MODEL,dims=DIMENSIONS,
        revision=embeddings.PROVENANCE['model_revision'],limit=limit,free_only=free_only)


def retrieve(project, selection, items, course=None, *, embed=None, search=None, book_search=None):
    started=perf_counter()
    free_only=bool(course and course.get('id')=='A1')
    track = (course or {}).get('id')
    shared = resource_evidence.course_selection(project, selection, course)
    all_pools = candidate_pools(dict(project, selectedCourse=None), selection, items,
                                limit=max(1, len(items)), rank_courses=False)
    active = [i for i, pool in enumerate(all_pools) if pool['courses'] or pool['books']]
    pools = [dict(name=pool['name'], application=pool['application'], courses=[], books=[]) for pool in all_pools]
    if not active:
        return pools,{'version':version_for(course),'model':MODEL,'perKind':PER_KIND,'perCourse':PER_KIND,
                      'maxUniqueBooks':book_candidates.LIMIT,'matches':[],'elapsedMs':round((perf_counter()-started)*1000)}
    queries = {}
    for i in active:
        name = all_pools[i]['name']
        common = skill_query(project, name, (selection.get('commonApplications') or {}).get(name))
        if all_pools[i]['courses']:
            queries[i, 'courses'] = common
        if all_pools[i]['books']:
            queries[i, 'books'] = common if track else _unscoped_book_query(project, selection['skills'][i])
    texts = tuple(sorted(set(queries.values())))
    vectors = dict(zip(texts, validate_vectors((embed or _shared_vectors)(texts), len(texts)), strict=True))
    search = search or search_vectors
    matches = []
    from app.services import crash_courses
    crash_cache = {}
    def has_learning_evidence(rid, name, allow_audit_gap):
        if rid not in crash_cache:
            crash_cache[rid] = resource_evidence.facts(items[rid], project, shared)
        info = crash_cache[rid]
        spec = next(skill for skill in shared['skills'] if skill['name'] == name)
        return resource_evidence.course_applicable(info, spec, allow_audit_gap=allow_audit_gap)

    for index in active:
        for key, kind, prefix in [('courses','courses',''), ('books','books','book_')]:
            allowed = {row['id'].removeprefix(prefix): row for row in all_pools[index][key]}
            if not allowed:
                continue
            vector = vectors[queries[index, key]]
            scoped_course = track in ('A1', 'A2', 'A3')
            review_limit = (COURSE_REVIEW if key == 'courses' else book_candidates.REVIEW_LIMIT) if scoped_course else PER_KIND
            limit = len(allowed) if scoped_course and key == 'courses' else review_limit
            if key == 'books' and scoped_course and book_search is not None:
                rows = book_search(pools[index]['name'], queries[index, key], list(allowed), vector, limit)
            else:
                rows = search(kind, list(allowed), vector, limit, False)
            if not rows:
                raise RecommendationError('조건에 맞는 자료의 검색 벡터를 찾지 못했어요. 등록된 임베딩 상태를 확인해 주세요.')
            if scoped_course and key == 'courses':
                unique_ids = set()
                for row in rows:
                    rid = row['resource_id']
                    if rid not in allowed or rid in unique_ids:
                        raise RecommendationError('벡터 검색 결과가 허용된 자료와 일치하지 않아요.')
                    unique_ids.add(rid)
                    if not isinstance(row.get('similarity'), (int, float)) or not math.isfinite(row['similarity']):
                        raise RecommendationError('자료 검색 유사도가 올바르지 않아요.')
                rows = [dict(row, current_cost=row.get('current_cost', allowed[row['resource_id']].get('cost'))) for row in rows]
                spec = shared['skills'][index]
                rows = course_focus.course_window(rows, items, spec['name'], resource_evidence.requested_topics(spec),
                                                  track, review_limit, has_learning_evidence)
            seen=set()
            found = []
            for match in rows[:review_limit]:
                rid=str(match['resource_id'])
                if rid not in allowed or rid in seen:raise RecommendationError('벡터 검색 결과가 허용된 자료와 일치하지 않아요.')
                row=deepcopy(allowed[rid]);row['cost']=match.get('current_cost',row.get('cost'))
                if free_only and key == 'courses' and row.get('cost')!=0:raise RecommendationError('Free Course 검색에 유료 자료가 포함됐어요.')
                score=match.get('similarity')
                if score is None or not math.isfinite(float(score)):raise RecommendationError('자료 검색 유사도가 올바르지 않아요.')
                seen.add(rid)
                found.append({**{field:row.get(field) for field in FIELDS},'retrievalScore':float(score),
                              **({'difficulty':row.get('difficulty')} if key == 'courses' else {}),
                              **({'timeStatus':items[rid].get('timeStatus')} if key == 'courses' and crash_courses.is_crash(course) else {})})
            if key == 'courses' and crash_courses.is_crash(course):
                for row in found:
                    if row['id'] not in crash_cache:
                        crash_cache[row['id']] = crash_courses.facts(items[row['id']], project, shared)
                # 20개 검토 결과를 스킬별로 먼저 6개로 자르면 공통 단기 강좌를 잃을 수 있다.
                found = crash_courses.rank(found, project, shared, shared['skills'][index], cache=crash_cache)
            elif key == 'courses' and scoped_course:
                found = resource_evidence.rank_applicable(found, project, shared, shared['skills'][index], course,
                                                          limit=PER_KIND, sources=items, cache=crash_cache)
            pools[index][key] = found
            for row in found:
                matches.append({'skill':pools[index]['name'],'resourceId':row['id'],'similarity':row['retrievalScore']})
    if crash_courses.is_crash(course):
        pools = crash_courses.share_candidates(pools, project, shared, items, cache=crash_cache)
        matches = [{'skill':pool['name'],'resourceId':row['id'],'similarity':row.get('retrievalScore'),
                    **({'sourceSkill':row['sourceSkill'],'sharedCandidate':True} if row.get('sharedCandidate') else {})}
                   for pool in pools for key in ('courses','books') for row in pool[key]]
    return pools,{'version':version_for(course),'model':MODEL,'perKind':PER_KIND,
                  'perCourse':PER_KIND,'bookReview':book_candidates.REVIEW_LIMIT,
                  'maxUniqueBooks':book_candidates.LIMIT,'matches':matches,'elapsedMs':round((perf_counter()-started)*1000)}

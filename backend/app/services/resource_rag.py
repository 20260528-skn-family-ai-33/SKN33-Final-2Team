"""V_2 학습 자료 RAG 검색. 기존 벡터 SELECT만 사용하고 DB에는 쓰지 않는다."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import math
from time import perf_counter
from app import db, llm
from app.agents.resource_recommendations import RecommendationError, candidate_pools

MODEL = 'text-embedding-3-small'
DIMENSIONS = 1536
VERSION = 'resource-pgvector-rag/v2'
PER_KIND = 6
FIELDS = ('id','title','provider','cost','hours','estimated','image','url','skills','content','curriculum')


def query_text(project: dict, skill: dict, course: dict | None) -> str:
    return json.dumps({
        'projectGoal': str(project.get('goal') or '')[:500],
        'projectSummary': str(project.get('projectSummary') or '')[:2500],
        'desiredCompetencies': str(project.get('desiredCompetencies') or '')[:500],
        'skill': skill['name'], 'application': str(skill.get('application') or '')[:600],
        'course': {key: str((course or {}).get(key) or '')[:500] for key in ('id','name','reason','scope')},
    }, ensure_ascii=False, sort_keys=True)


def validate_vectors(vectors, count):
    if not isinstance(vectors, (list,tuple)) or len(vectors) != count:
        raise RecommendationError('자료 검색 임베딩 개수가 일치하지 않아요.')
    for vector in vectors:
        if (not isinstance(vector,(list,tuple)) or len(vector)!=DIMENSIONS or
            not all(isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) for value in vector) or
            not any(vector)):
            raise RecommendationError('자료 검색 임베딩은 유효한 1536차원 벡터여야 해요.')
    return vectors


@lru_cache(maxsize=128)
def cached_vectors(texts: tuple[str,...]):
    if llm.embed_model()!=MODEL:
        raise RecommendationError('자료 검색에는 저장된 벡터와 같은 text-embedding-3-small 모델이 필요해요.')
    if not llm.embed_ready():
        raise RecommendationError('자료 검색 임베딩에 필요한 OpenAI 키가 없어요.')
    return tuple(tuple(vector) for vector in validate_vectors(llm.embed(list(texts)),len(texts)))


def search_vectors(resource_type, ids, vector, limit, free_only):
    # 스킬·종류·사용 가능 여부는 ids에 반영하고, 최신 0원 조건도 LIMIT 이전에 적용한다.
    if not ids:return []
    return db.all_("""SELECT e.resource_id, m.cost_won AS current_cost,
            1-(e.embedding <=> CAST(:query AS vector)) AS similarity
        FROM public.learning_resource_embeddings e
        JOIN app_ext.resource_meta m ON m.resource_key =
            CASE WHEN e.resource_type='books' THEN 'book_' || e.resource_id ELSE e.resource_id END
        WHERE e.resource_type=:kind AND e.resource_id=ANY(:ids)
            AND e.embedding_model=:model AND e.dimensions=:dims AND e.embedding IS NOT NULL
            AND (NOT :free_only OR m.cost_won=0)
        ORDER BY e.embedding <=> CAST(:query AS vector), e.resource_id LIMIT :limit""",
        query=json.dumps(vector,allow_nan=False),kind=resource_type,ids=ids,model=MODEL,dims=DIMENSIONS,limit=limit,free_only=free_only)


def retrieve(project, selection, items, course=None, *, embed=None, search=None):
    started=perf_counter()
    free_only=bool(course and course.get('id')=='A1')
    # 개수 제한 없이 조건을 적용하고, 벡터 순위로 정렬한 뒤 6개로 줄인다.
    all_pools=candidate_pools(project,selection,items,limit=max(1,len(items)),free_only=free_only)
    active=[index for index,pool in enumerate(all_pools) if pool['courses'] or pool['books']]
    pools=[{'name':pool['name'],'application':pool['application'],'courses':[],'books':[]} for pool in all_pools]
    if not active:
        return pools,{'version':VERSION,'model':MODEL,'perKind':PER_KIND,'matches':[],'elapsedMs':round((perf_counter()-started)*1000)}
    texts=tuple(query_text(project,selection['skills'][index],course) for index in active)
    vectors=validate_vectors((embed or cached_vectors)(texts),len(texts))
    search=search or search_vectors
    matches=[]
    for index,vector in zip(active,vectors):
        for key,kind,prefix in [('courses','courses',''),('books','books','book_')]:
            allowed={row['id'][len(prefix):] if prefix and row['id'].startswith(prefix) else row['id']: row for row in all_pools[index][key]}
            rows=search(kind,list(allowed),vector,PER_KIND,free_only) if allowed else []
            seen=set()
            for match in rows[:PER_KIND]:
                rid=str(match['resource_id'])
                if rid not in allowed or rid in seen:raise RecommendationError('벡터 검색 결과가 허용된 자료와 일치하지 않아요.')
                row=deepcopy(allowed[rid]);row['cost']=match.get('current_cost',row.get('cost'))
                if free_only and row.get('cost')!=0:raise RecommendationError('Free Course 검색에 유료 자료가 포함됐어요.')
                score=match.get('similarity')
                if score is None or not math.isfinite(float(score)):raise RecommendationError('자료 검색 유사도가 올바르지 않아요.')
                seen.add(rid)
                pools[index][key].append({**{field:row.get(field) for field in FIELDS},'retrievalScore':float(score)})
                matches.append({'skill':pools[index]['name'],'resourceId':row['id'],'similarity':float(score)})
            if allowed and not rows:
                # 벡터가 없는 자료를 키워드 검색으로 몰래 대체하지 않는다.
                raise RecommendationError('조건에 맞는 자료의 검색 벡터를 찾지 못했어요. 등록된 임베딩 상태를 확인해 주세요.')
    return pools,{'version':VERSION,'model':MODEL,'perKind':PER_KIND,'matches':matches,'elapsedMs':round((perf_counter()-started)*1000)}

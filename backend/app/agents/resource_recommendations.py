"""선정 스킬별 자료 후보 및 AI 추천 계약. 운영 결과 화면에는 아직 연결하지 않는다."""
from __future__ import annotations
from collections.abc import Callable
from copy import deepcopy
import re
from typing import Any

from .resource_instructions import COMMON as SYSTEM, instructions


class RecommendationError(ValueError):
    pass


def _course_diagnostic(row: dict, has_candidates: bool, has_choices: bool) -> dict | None:
    value = row.get('courseDiagnostic')
    if value is None:
        return None  # 기존 저장 응답·key 전용 응답과 호환한다.
    reasons = {'no_candidates', 'insufficient_evidence', 'stack_mismatch', 'scope_gap', 'longer_for_coverage'}
    if (not isinstance(value, dict) or set(value) != {'reason', 'detail'}
            or not isinstance(value.get('reason'), str) or value['reason'] not in reasons
            or not isinstance(value.get('detail'), str) or not 1 <= len(value['detail'].strip()) <= 240):
        raise RecommendationError('강좌 진단 사유와 설명(1~240자)을 확인해 주세요.')
    # 일부 자료를 추천하면서 남은 근거·범위·기술 부족을 설명할 수도 있다.
    # 실제 후보/선택의 존재를 단정하는 두 사유만 구조적 모순을 검사한다.
    if ((value['reason'] == 'longer_for_coverage' and not has_choices)
            or (value['reason'] == 'no_candidates' and (has_candidates or has_choices))):
        raise RecommendationError('강좌 진단 사유가 제공 후보·선택 결과와 일치하지 않습니다.')
    return {'reason': value['reason'], 'detail': value['detail'].strip()}


def _empty_skill(name: str) -> dict:
    return {'name': name, 'courses': [], 'books': [], 'selectedCourse': None, 'selectedBooks': [],
            'courseDiagnostic': {'reason': 'no_candidates', 'detail': '조건에 맞는 강좌 후보가 없습니다.'}}


def candidate_pools(project: dict, selection: dict, items: dict[str, dict], limit: int = 6, *, free_only: bool = False,
                    course: dict | None = None, rank_courses: bool = True) -> list[dict]:
    rows = selection.get('skills')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5:
        raise RecommendationError('선정 스킬 1~5개가 필요합니다.')
    names = [row.get('name') if isinstance(row, dict) else None for row in rows]
    if any(not isinstance(name, str) or not name.strip() for name in names) or len(set(names)) != len(names):
        raise RecommendationError('선정 스킬 이름을 확인해 주세요.')
    if limit < 1:
        raise RecommendationError('후보 수는 1 이상이어야 합니다.')
    text = ' '.join(str(project.get(key) or '') for key in ('goal', 'projectSummary', 'desiredCompetencies'))
    terms = set(re.findall(r'[a-z]{3,}|[가-힣]{2,}', text.lower()))
    def score(item):
        evidence = (str(item.get('title') or '') + ' ' + str(item.get('content') or '')).lower()
        return sum(term in evidence for term in terms)
    from app.learner_knowledge import exclusion
    knowledge=project.get('learnerKnowledge') or {}
    from app.services import crash_courses
    course = course or project.get('selectedCourse')
    pools = []
    crash_cache = {}
    for skill in rows:
        by_kind = {}
        for kind, key in (('course', 'courses'), ('book', 'books')):
            # 스킬·종류·사용 가능 여부를 후보 개수 제한보다 먼저 적용한다.
            available = [row for row in items.values() if row.get('usable') and row.get('type') == kind and not exclusion(row,knowledge,str(project.get('goal') or '')) and skill['name'] in (row.get('skills') or []) and (not free_only or kind == 'book' or (row.get('cost') == 0 and not isinstance(row.get('cost'), bool)))]
            available.sort(key=lambda row: (-score(row), str(row.get('title') or ''), row['id']))
            if kind == 'course' and rank_courses and crash_courses.is_crash(course):
                available = crash_courses.rank(available, project, selection, skill, cache=crash_cache)
            fields = ('id', 'title', 'provider', 'cost', 'hours', 'estimated', 'image', 'url', 'skills', 'content', 'curriculum')
            if kind == 'course' and crash_courses.is_crash(course):
                fields += ('timeStatus',)
            by_kind[key] = [deepcopy({field: row.get(field) for field in fields})
                for row in available[:limit]]
        pools.append({'name': skill['name'], 'application': skill.get('application') or '', **by_kind})
    return pools


def recommend_resources(project: dict, selection: dict, items: dict[str, dict],
                        generate: Callable[[str, dict], dict], *, course: dict | None = None, retrieved_pools: list[dict] | None = None) -> dict:
    project = dict(project, selectedCourse=deepcopy(course or project.get('selectedCourse')))
    pools = retrieved_pools if retrieved_pools is not None else candidate_pools(project, selection, items, free_only=bool(course and course.get('id') == 'A1'), course=course)
    if not any(row['courses'] or row['books'] for row in pools):
        return {'skills': [_empty_skill(row['name']) for row in pools]}
    # 원문·개인 식별정보 대신 프로젝트 맥락과 확인된 자료 후보를 전달한다.
    from app.services import crash_courses
    from app.services import resource_evidence
    from app.services import book_candidates
    crash_cache = {}
    if crash_courses.is_crash(course):
        pools = crash_courses.share_candidates(pools, project, selection, items, cache=crash_cache)
    pools, common_books = book_candidates.common_pool(pools, items)
    if not any(pool['courses'] or pool['books'] for pool in pools):
        return {'skills': [_empty_skill(pool['name']) for pool in pools]}
    names = [pool['name'] for pool in pools]
    book_catalog = book_candidates.model_catalog(common_books, items, names)
    book_refs = {book['id']: f'B{index}' for index, book in enumerate(common_books, 1)}
    # 같은 강좌는 여러 스킬에서 한 키를 공유한다. 별칭을 서로 다른 자료로 고르는 혼동을 막는다.
    course_refs = {}
    for si, pool in enumerate(pools, 1):
        for ri, row in enumerate(pool['courses'], 1):
            course_refs.setdefault(row['id'], f'S{si}-C{ri}')
    references = {key: ('courses', rid) for rid, key in course_refs.items()}
    references.update({book_refs[row['id']]: ('books', row['id']) for row in common_books})
    provided = {key: {row['id']: (pool['name'], row) for pool in pools for row in pool[key]}
                for key in ('courses', 'books')}
    # 같은 원본 강좌여도 스킬별로 발췌가 다르므로 입력 카드는 별도 객체로 만든다.
    evidence_pools = [deepcopy(pool) for pool in pools]
    for si, pool in enumerate(evidence_pools, 1):
        pool['maxBooks'] = min(3, len(pool['books']))
        for key in ('courses', 'books'):
            if key == 'books':
                pool[key] = [{'choiceKey': book_refs[row['id']]} for row in pool[key]]
                continue
            for ri, row in enumerate(pool[key], 1):
                row['choiceKey'] = course_refs[row['id']]
                row.pop('id', None)
                row['title'] = resource_evidence.normalize(row.get('title'))
                row['content'] = resource_evidence.normalize(row.get('content'))[:350]
                curriculum = row.pop('curriculum', None)
                outline = (curriculum.get('items') or []) if isinstance(curriculum, dict) else []
                if not isinstance(outline, list):
                    outline = []
                row['outline'] = [{field: str(part.get(field) or '')[:100] for field in ('section', 'title')}
                                  for part in outline[:3] if isinstance(part, dict)]
                if key == 'courses':
                    original = pools[si - 1][key][ri - 1]
                    source = items.get(original['id'], original)
                    if original['id'] not in crash_cache:
                        crash_cache[original['id']] = resource_evidence.facts(source, project, selection)
                    row['outline'] = resource_evidence.outline(source, project, selection, selection['skills'][si - 1], course,
                                                             info=crash_cache[original['id']])
                    info = crash_cache[original['id']]
                    row['learningEvidence'] = {key: value for key, value in info['suitability'][pool['name']].items()
                                               if key != 'stageGap'}
                    row['applicableSelectedSkills'] = [name for name in names if resource_evidence.suitable(info, name)]
                    if crash_courses.is_crash(course):
                        row['supportedSelectedSkills'] = info['supported']
                row.pop('image', None)
                row.pop('url', None)
                row.pop('skills', None)
                row['eligibleSkills'] = [name for name in names if name in (source.get('skills') or [])]
    payload = {'project': {key: project.get(key) for key in ('goal', 'projectSummary', 'desiredCompetencies')}, 'skills': evidence_pools}
    payload['bookCatalog'] = book_catalog
    if crash_courses.is_crash(course):
        payload['crashStudyPlan'] = crash_courses.study_plan(pools, project, selection, course_refs, cache=crash_cache)
    payload['learnerKnowledge']=deepcopy(project.get('learnerKnowledge') or {})
    payload['hrContext']=deepcopy(project.get('hrContext') or {})
    # 자료 선택에는 코스 방향·선정 역량이 필요하다. 이전 활동 전문·저장용 출처를 중복 전송하지 않는다.
    payload['course'] = ({key: deepcopy(course[key]) for key in
                         ('id', 'name', 'tagline', 'reason', 'scope', 'weeklyHours', 'weeks', 'learningSkills') if key in course}
                        if isinstance(course, dict) else None)
    payload['project']['details'] = deepcopy(project.get('details') or {})
    goal, desired = payload['project']['goal'], payload['project']['desiredCompetencies']
    if isinstance(goal, str) and isinstance(desired, str) and goal.strip() == desired.strip():
        payload['project'].pop('desiredCompetencies')
    raw = generate(instructions(course), payload)
    rows = raw.get('skills') if isinstance(raw, dict) else None
    if not isinstance(rows, list) or len(rows) != len(pools):
        raise RecommendationError('스킬별 추천 결과 수가 일치하지 않습니다.')
    by_name = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('name') not in [p['name'] for p in pools] or row['name'] in by_name:
            raise RecommendationError('추천 스킬이 입력과 다르거나 중복되었습니다.')
        by_name[row['name']] = row
    result = []
    for si, pool in enumerate(pools, 1):
        row = by_name[pool['name']]
        output = {'name': pool['name']}
        for key in ('courses', 'books'):
            picked = row.get(key)
            if not isinstance(picked, list) or len(picked) > 3:
                raise RecommendationError('강좌와 도서는 각각 최대 3개 추천합니다.')
            candidates = {r['id']: r for r in pool[key]}
            seen, cards = set(), []
            for recommendation in picked:
                if not isinstance(recommendation, dict):
                    raise RecommendationError('자료 추천 형식이 올바르지 않습니다.')
                reference = recommendation.get('key')
                if reference is not None and (not isinstance(reference, str) or reference not in references or references[reference][0] != key):
                    raise RecommendationError('해당 스킬·자료 종류의 후보 키가 아닙니다.')
                rid = references[reference][1] if reference is not None else recommendation.get('id')
                source = items.get(rid) if isinstance(rid, str) else None
                if (not source or source.get('type') != ('course' if key == 'courses' else 'book')
                        or not source.get('usable') or pool['name'] not in (source.get('skills') or [])
                        or rid not in provided[key] or rid in seen or (key == 'books' and rid not in candidates)):
                    raise RecommendationError('후보에 없거나 중복된 자료입니다.')
                card = deepcopy(candidates.get(rid) or provided[key][rid][1])
                if rid not in candidates:
                    card.pop('retrievalScore', None)
                    card.update(sharedCandidate=True, sourceSkill=provided[key][rid][0])
                if any(field in recommendation and (not isinstance(recommendation[field], str) or not recommendation[field].strip()) for field in ('why', 'knowledge')):
                    raise RecommendationError('추천 이유와 기대 지식 역량이 필요합니다.')
                seen.add(rid)
                cards.append({**card, 'why': recommendation.get('why', '').strip(),
                              'knowledge': recommendation.get('knowledge', '').strip(), 'aiRecommended': len(cards) == 0})
            if key == 'courses' and crash_courses.is_crash(course):
                # 모델이 고른 강좌만 정렬하며 후보 밖 자료나 사용자의 선택을 추가·변경하지 않는다.
                diagnostic = _course_diagnostic(row, bool(pool['courses']), bool(cards))
                preferred = cards[0] if cards and diagnostic and diagnostic['reason'] == 'longer_for_coverage' else None
                cards = crash_courses.rank(cards, project, selection, selection['skills'][si - 1], cache=crash_cache, similarity_gate=False)
                if preferred is not None:
                    cards = [preferred] + [card for card in cards if card['id'] != preferred['id']]
                for index, card in enumerate(cards):
                    card['aiRecommended'] = index == 0
            output[key] = cards
        output['selectedCourse'] = output['courses'][0]['id'] if output['courses'] else None
        output['selectedBooks'] = [output['books'][0]['id']] if output['books'] else []
        diagnostic = _course_diagnostic(row, bool(pool['courses']), bool(output['courses']))
        if diagnostic is not None:
            output['courseDiagnostic'] = diagnostic
        elif not pool['courses']:
            output['courseDiagnostic'] = _empty_skill(pool['name'])['courseDiagnostic']
        result.append(output)
    if crash_courses.is_crash(course):
        result = crash_courses.align_shared_courses(result, project, selection, crash_cache)
        for row in result:
            row['selectedCourse'] = row['courses'][0]['id'] if row['courses'] else None
            for index, card in enumerate(row['courses']):
                card['aiRecommended'] = index == 0
    return {'skills': result}


def validate_choices(recommendations: dict, choices: dict) -> None:
    if not isinstance(choices, dict) or set(choices) != {row['name'] for row in recommendations['skills']}:
        raise RecommendationError('스킬별 자료 선택을 확인해 주세요.')
    for row in recommendations['skills']:
        selected = choices[row['name']]
        if not isinstance(selected, dict):
            raise RecommendationError('자료 선택 형식이 올바르지 않습니다.')
        enabled = selected.get('enabled', True)
        if type(enabled) is not bool:
            raise RecommendationError('스킬 선택 여부는 참/거짓이어야 합니다.')
        course, books = selected.get('course'), selected.get('books')
        allowed_courses = {r['id'] for r in row['courses']}
        allowed_books = {r['id'] for r in row['books']}
        if course is not None and not isinstance(course, str):
            raise RecommendationError('강좌는 한 개만 선택할 수 있습니다.')
        if course not in allowed_courses and not (course is None and (not allowed_courses or not enabled)):
            raise RecommendationError('추천한 강좌 중 1개를 선택해 주세요.')
        if not isinstance(books, list) or len(books) > 3 or any(not isinstance(key, str) for key in books) or len(set(books)) != len(books) or not set(books).issubset(allowed_books):
            raise RecommendationError('추천한 도서는 최대 3권까지 선택할 수 있습니다.')


def recommend_from_catalog(ctx: Any, pre: dict, course: dict | None = None) -> dict:
    from app import catalog
    from app.agents import runtime
    if not ctx.live:
        raise RecommendationError('AI 추천에는 사용 가능한 실제 모델이 필요합니다.')
    from app.services.resource_rag import retrieve
    items = catalog.items()
    from app.learner_knowledge import from_profile,hr_context
    project=dict(pre['project'],learnerKnowledge=from_profile(pre.get('profile')),hrContext=hr_context(pre.get('profile')))
    project['selectedCourse'] = deepcopy(course)
    pools, retrieval = retrieve(project, pre['selection'], items, course)
    result = recommend_resources(project, pre['selection'], items,
        lambda system, payload: runtime.llm_json(ctx, system, payload, role='resources'), course=course, retrieved_pools=pools)
    result['retrieval'] = retrieval
    return result


def validate_skill_order(recommendations: dict, order: list[str]) -> None:
    names = {row['name'] for row in recommendations['skills']}
    if not isinstance(order, list) or any(not isinstance(name, str) for name in order) or len(order) != len(names) or len(set(order)) != len(order) or set(order) != names:
        raise RecommendationError('선정 스킬을 빠짐없이 한 번씩 포함한 순서가 필요합니다.')

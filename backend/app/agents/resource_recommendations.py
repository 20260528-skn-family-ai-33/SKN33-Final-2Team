"""선정 스킬별 자료 후보 및 AI 추천 계약. 운영 결과 화면에는 아직 연결하지 않는다."""
from __future__ import annotations
from collections.abc import Callable
from copy import deepcopy
import logging
import math
import re
from typing import Any

from .resource_instructions import COMMON as SYSTEM, instructions
from app import course_levels

logger = logging.getLogger(__name__)


class RecommendationError(ValueError):
    pass


_BOOK_REASONS = {'no_candidates', 'insufficient_evidence', 'scope_gap'}
_COURSE_REASONS = _BOOK_REASONS | {'stack_mismatch', 'longer_for_coverage'}
_DIAGNOSTIC_LIMIT = 240
_CANDIDATE_TOKEN = re.compile(r'(?<![A-Za-z0-9_])(?:S[0-9]+-C[0-9]+|B[0-9]+)(?![A-Za-z0-9_])')
_COMPARISON_LABEL = '비교 후보'


def _diagnostic(row: dict, kind: str, has_candidates: bool, has_choices: bool) -> dict | None:
    """진단은 선택을 설명하는 보조 정보다. 형식이 틀렸다고 검증된 자료 선택까지 실패시키지 않는다.

    사용할 수 없는 진단은 버리고 기록한다. 호출 측은 후보·선택 상태로 계산한 서버 안내를 대신 붙인다."""
    value = row.get(f'{kind}Diagnostic')
    if value is None:
        return None  # 기존 저장 응답·key 전용 응답과 호환한다.
    reasons = _COURSE_REASONS if kind == 'course' else _BOOK_REASONS
    if (not isinstance(value, dict) or not isinstance(value.get('reason'), str) or value['reason'] not in reasons
            or not isinstance(value.get('detail'), str) or not value['detail'].strip()):
        logger.warning('자료 진단 형식 오류로 서버 안내 사용: kind=%s', kind)
        return None
    # 일부 자료를 추천하면서 남은 근거·범위·기술 부족을 설명할 수도 있다.
    # 실제 후보/선택의 존재를 단정하는 두 사유만 구조적 모순을 검사한다.
    if ((value['reason'] == 'longer_for_coverage' and not has_choices)
            or (value['reason'] == 'no_candidates' and (has_candidates or has_choices))):
        logger.warning('자료 진단 사유가 후보·선택과 모순되어 서버 안내 사용: kind=%s reason=%s', kind, value['reason'])
        return None
    detail = value['detail'].strip()
    if len(detail) > _DIAGNOSTIC_LIMIT:
        detail = detail[:_DIAGNOSTIC_LIMIT - 1].rstrip() + '…'
    return {'reason': value['reason'], 'detail': detail}


def _display_diagnostic(diagnostic: dict, titles: dict[str, str]) -> dict:
    """원문은 보존하고, 제목을 배치할 공간은 후보 키에서만 확보한다."""
    detail = diagnostic['detail']
    matches = list(_CANDIDATE_TOKEN.finditer(detail))
    if not matches:
        return diagnostic
    budget = _DIAGNOSTIC_LIMIT - len(detail) + sum(len(match[0]) for match in matches)
    labels = [titles.get(match[0], '') for match in matches]

    # 긴 제목에 같은 상한을 적용하고, 확보된 공간에 맞을 때까지 상한을 줄인다.
    for limit in range(48, 5, -1):
        display = []
        for title in labels:
            if len(title) > limit:
                title = title[:limit - 1].rstrip() + '…'
            display.append(f'「{title}」' if title else _COMPARISON_LABEL)
        if sum(map(len, display)) <= budget:
            break
    else:
        display = [f'「{title}」' if title and len(title) + 2 <= len(_COMPARISON_LABEL) else _COMPARISON_LABEL
                   for title in labels]
        if sum(map(len, display)) > budget:
            # 짧은 도서 키가 많으면 중립 표현도 예산을 넘길 수 있다. 그때는 화면이 원문을 가려 표시한다.
            return diagnostic
    replacements = iter(display)
    return {**diagnostic, 'displayDetail': _CANDIDATE_TOKEN.sub(lambda _: next(replacements), detail)}


def _no_candidates(kind: str) -> dict:
    return {'reason': 'no_candidates', 'detail': f'조건에 맞는 {kind} 후보가 없습니다.'}


def _recover_cross_skill_courses(by_name, payload, references, eligibility, generate):
    """다른 스킬에만 허용된 강좌 키는 제외하고, 유효한 선택이 전혀 없는 칸만 한 번 재선택한다."""
    from app.llm import LlmError

    retry = []
    for pool in payload['skills']:
        name = pool['name']
        row = by_name[name]
        picked = row.get('courses')
        if not isinstance(picked, list) or len(picked) > 3:
            continue  # 응답 구조·허위 키·종류·중복 등은 기존 검증에서 거절한다.
        kept = []
        for pick in picked:
            key = pick.get('key') if isinstance(pick, dict) else None
            ref = references.get(key) if isinstance(key, str) else None
            if (ref and ref[0] == 'courses' and eligibility[ref[1]] and pick.get('id', ref[1]) == ref[1]
                    and name not in eligibility[ref[1]]):
                continue
            kept.append(pick)
        if len(kept) == len(picked):
            continue
        by_name[name] = {**row, 'courses': kept}
        if not kept:
            by_name[name]['courseDiagnostic'] = {
                'reason': 'insufficient_evidence', 'detail': '모델이 이 스킬에 맞는 강좌를 선택하지 못했습니다.'}
            cards = [c for c in pool['courses'] if name in c['eligibleSkills']]
            if cards:
                retry.append({'name': name, 'application': pool.get('application'), 'courses': cards})
    if not retry:
        return
    # 비용과 지연을 제한한다. 재선택 응답은 요청한 칸의 로컬 키만 받을 수 있다.
    try:
        raw = generate('목표와 각 스킬에 적합한 강좌를 다시 선택하세요. 각 칸의 courses에 있는 choiceKey만 '
                       '사용하세요. 적합한 것이 없으면 빈 배열을 쓰세요. '
                       'JSON: {"skills":[{"name":"입력 스킬명","courses":[{"key":"choiceKey"}]}]}',
                       {'project': payload['project'], 'course': (payload['course'] or {}).get('id'), 'skills': retry})
    except (ValueError, LlmError, TimeoutError) as exc:
        logger.warning('강좌 재선택 실패: %s', type(exc).__name__)
        return
    rows = raw.get('skills') if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return
    for pool in retry:
        matches = [r for r in rows if isinstance(r, dict) and r.get('name') == pool['name']]
        picks = matches[0].get('courses') if len(matches) == 1 else None
        if not isinstance(picks, list) or not 0 < len(picks) <= 3:
            continue
        allowed = {c['choiceKey'] for c in pool['courses']}
        keys = [p.get('key') if isinstance(p, dict) else None for p in picks]
        if all(isinstance(k, str) and k in allowed for k in keys) and len(set(keys)) == len(keys):
            row = by_name[pool['name']]
            row['courses'] = [{'key': k} for k in keys]
            row.pop('courseDiagnostic', None)


def _empty_skill(name: str) -> dict:
    return {'name': name, 'courses': [], 'books': [], 'selectedCourse': None, 'selectedBooks': [],
            'courseDiagnostic': _no_candidates('강좌'), 'bookDiagnostic': _no_candidates('도서')}


def _missing_stack_diagnostic(profiles: list[dict]) -> dict:
    stacks = ', '.join(sorted({stack for profile in profiles for stack in profile['missingStack']}))
    return {'reason': 'insufficient_evidence', 'detail': f'필요 기술({stacks})의 학습 근거를 확인할 수 없습니다.'}


def _course_gap(name: str, candidates: list[dict], cache: dict) -> dict:
    if not candidates:
        return _no_candidates('강좌')
    profiles = [cache[card['id']]['suitability'][name] for card in candidates]
    if any(profile['suitable'] for profile in profiles):
        return {'reason': 'insufficient_evidence', 'detail': '후보가 있었으나 모델 응답에서 선택 근거를 확인하지 못했습니다.'}
    relevant = [profile for profile in profiles if profile['evidenceLevel'] in ('conceptual', 'applied')]
    if relevant and all(p['missingStack'] or p['conflictingStack'] for p in relevant):
        if all(p['conflictingStack'] for p in relevant):
            return {'reason': 'stack_mismatch', 'detail': '후보의 구현 기술이 목표에서 요구한 기술과 다릅니다.'}
        return _missing_stack_diagnostic(relevant)
    if relevant and all(not cache[card['id']]['scopeEvidence'][name] for card in candidates
                        if cache[card['id']]['suitability'][name] in relevant):
        return {'reason': 'scope_gap', 'detail': '후보의 학습 내용에서 이 스킬에 필요한 적용 범위를 확인할 수 없습니다.'}
    return {'reason': 'insufficient_evidence', 'detail': '목차와 소개를 검토했으나 추천을 확정할 강좌 근거가 부족합니다.'}


def _finalize_crash(result: list[dict], pools: list[dict], selection: dict, project: dict, cache: dict) -> None:
    from app.services import crash_courses as crash
    from app.services.resource_evidence import hours
    # 공통 검사 뒤 모델이 고른 목록은 보존한다. 기존 조합 선호는 첫 추천 순서에만 적용한다.
    chosen = crash.shortest_bundle(result, project, selection, cache)
    default = crash.shortest_bundle(pools, project, selection, cache)
    for output, pool in zip(result, pools):
        name, cards = output['name'], output['courses']
        ordered = crash.rank(cards, project, selection, {'name': name}, cache=cache)
        if name in chosen:
            first = chosen[name]
            ordered = [first] + [card for card in ordered if card['id'] != first['id']]
        output['courses'] = ordered
        if not output['courses'] and 'courseDiagnostic' not in output:
            output['courseDiagnostic'] = _course_gap(name, pool['courses'], cache)
        for index, card in enumerate(output['courses']):
            card['aiRecommended'] = index == 0
        output['selectedCourse'] = output['courses'][0]['id'] if output['courses'] else None

    # 같은 스킬을 다루며 시간이 확인된 두 조합에서만 중복을 제외한 시간을 비교한다.
    selected = {row['name']: row['courses'][0] for row in result if row['courses']}
    default_rows = {row['id']: row for row in default.values()}.values()
    selected_rows = {row['id']: row for row in selected.values()}.values()
    longer = False
    if selected and selected.keys() == default.keys() and all(
        crash.time_certainty(row) == 'confirmed' for row in (*default_rows, *selected_rows)
    ):
        default_hours = math.fsum(hours(row) for row in default_rows)
        selected_hours = math.fsum(hours(row) for row in selected_rows)
        longer = selected_hours > default_hours and not math.isclose(selected_hours, default_hours, abs_tol=1e-9)
    for output in result:
        name = output['name']
        if ((output.get('courseDiagnostic') or {}).get('reason') == 'longer_for_coverage'
                and (not longer or name not in default or default[name]['id'] == output['selectedCourse'])):
            del output['courseDiagnostic']


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
            track = course.get('id') if isinstance(course, dict) else course
            if kind == 'course' and track in ('A2', 'A3'):
                available.sort(key=lambda r: course_levels.preference(r, track))
            if kind == 'course' and rank_courses and crash_courses.is_crash(course):
                available = crash_courses.rank(available, project, selection, skill, cache=crash_cache)
            fields = ('id', 'title', 'provider', 'cost', 'hours', 'estimated', 'image', 'url', 'skills', 'content', 'curriculum')
            if kind == 'course' and crash_courses.is_crash(course):
                fields += ('timeStatus',)
            if kind == 'course':
                fields += ('difficulty', 'difficultyEstimated', 'difficultyBasis', 'difficultySource')
            by_kind[key] = [deepcopy({field: row.get(field) for field in fields})
                for row in available[:limit]]
        pools.append({'name': skill['name'], 'application': skill.get('application') or '', **by_kind})
    return pools


def recommend_resources(project: dict, selection: dict, items: dict[str, dict],
                        generate: Callable[[str, dict], dict], *, course: dict | None = None, retrieved_pools: list[dict] | None = None) -> dict:
    project = dict(project, selectedCourse=deepcopy(course or project.get('selectedCourse')))
    from app.services import resource_evidence
    plan_selection = selection
    selection = resource_evidence.course_selection(project, selection, course)
    pools = retrieved_pools if retrieved_pools is not None else candidate_pools(project, selection, items, free_only=bool(course and course.get('id') == 'A1'), course=course)
    if not any(row['courses'] or row['books'] for row in pools):
        return {'skills': [_empty_skill(row['name']) for row in pools]}
    # 원문·개인 식별정보 대신 프로젝트 맥락과 확인된 자료 후보를 전달한다.
    from app.services import crash_courses
    from app.services import book_candidates
    crash_cache = {}
    is_crash = crash_courses.is_crash(course)
    track = (course or {}).get('id')
    rejected_diagnostics = {}
    if track in ('A1', 'A2', 'A3'):
        # 직접 호출과 저장 후보의 재사용도 검색 진입점과 같은 가격·수준·관련성 문턱을 통과한다.
        filtered = []
        for pool, skill in zip(pools, selection['skills'], strict=True):
            courses, rejected = [], []
            for row in pool['courses']:
                source = items.get(row['id'], row)
                if not course_levels.eligible({**source, 'cost': row.get('cost')}, track):
                    continue
                if row['id'] not in crash_cache:
                    crash_cache[row['id']] = resource_evidence.facts(source, project, selection)
                if resource_evidence.course_applicable(crash_cache[row['id']], skill):
                    courses.append(row)
                else:
                    rejected.append(row)
            if rejected and not courses:
                rejected_diagnostics[pool['name']] = _course_gap(pool['name'], rejected, crash_cache)
            filtered.append({**pool, 'courses': courses})
        pools = filtered
    if is_crash:
        pools = crash_courses.share_candidates(pools, project, selection, items, cache=crash_cache)
    pools, common_books = book_candidates.common_pool(pools, items, selection=plan_selection)
    if not any(pool['courses'] or pool['books'] for pool in pools):
        return {'skills': [dict(_empty_skill(pool['name']), **(
            {'courseDiagnostic': rejected_diagnostics[pool['name']]} if pool['name'] in rejected_diagnostics else {}))
            for pool in pools]}
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
    local_courses = {pool['name']: {row['id'] for row in pool['courses']} for pool in pools}
    for rid, (_, original) in provided['courses'].items():
        if rid not in crash_cache:
            crash_cache[rid] = resource_evidence.facts(items.get(rid, original), project, selection)
    skill_specs = {skill['name']: skill for skill in selection['skills']}
    course_eligibility = {rid: [name for name in names if name in (items.get(rid, original).get('skills') or [])
                               and (track not in ('A1', 'A2', 'A3') or resource_evidence.course_applicable(crash_cache[rid], skill_specs[name]))
                               and (not is_crash or rid in local_courses[name]
                                    or resource_evidence.suitable(crash_cache[rid], name))]
                          for rid, (_, original) in provided['courses'].items()}
    # 같은 원본 강좌여도 스킬별로 발췌가 다르므로 입력 카드는 별도 객체로 만든다.
    evidence_pools = [deepcopy(pool) for pool in pools]
    for si, pool in enumerate(evidence_pools, 1):
        pool['maxBooks'] = min(3, len(pool['books']))
        pool['books'] = [{'choiceKey': book_refs[row['id']]} for row in pool['books']]
        skill = selection['skills'][si - 1]
        for ri, row in enumerate(pool['courses'], 1):
            rid = row.pop('id')
            row['choiceKey'] = course_refs[rid]
            slot = f'S{si}-C{ri}'
            if slot != row['choiceKey']:
                row['slotKey'] = slot
                if references.setdefault(slot, ('courses', rid)) != ('courses', rid):
                    raise RecommendationError('강좌 후보 키가 서로 다른 자료를 가리킵니다.')
            info = crash_cache[rid]
            row['title'] = resource_evidence.normalize(row.get('title'))
            row['content'] = resource_evidence.description_excerpt(info, project, skill, course)
            row['outline'] = resource_evidence.outline(items.get(rid, {}), project, selection, skill, course, info=info)
            row['learningEvidence'] = {key: value for key, value in info['suitability'][pool['name']].items()
                                       if key not in ('stageGap', 'appliedDescription')}
            row['learningEvidence']['scopeMatch'] = info['scopeEvidence'][pool['name']]
            row['applicableSelectedSkills'] = [name for name in names if resource_evidence.suitable(info, name)]
            row['eligibleSkills'] = course_eligibility[rid]
            if is_crash:
                row['supportedSelectedSkills'] = info['supported']
                row['timeStatus'] = crash_courses.time_certainty(row)
            for field in ('image', 'url', 'skills', 'curriculum'):
                row.pop(field, None)
    payload = {'project': {key: project.get(key) for key in ('goal', 'projectSummary', 'desiredCompetencies')}, 'skills': evidence_pools}
    payload['bookCatalog'] = book_catalog
    if is_crash:
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
    _recover_cross_skill_courses(by_name, payload, references, course_eligibility, generate)
    candidate_titles = {key: ' '.join(resource_evidence.normalize(provided[kind][rid][1].get('title')).split())
                        for key, (kind, rid) in references.items()}
    result = []
    for pool in pools:
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
                if 'key' in recommendation and (not isinstance(reference, str) or reference not in references or references[reference][0] != key):
                    raise RecommendationError('해당 스킬·자료 종류의 후보 키가 아닙니다.')
                rid = references[reference][1] if reference is not None else recommendation.get('id')
                if 'id' in recommendation and recommendation['id'] != rid:
                    raise RecommendationError('후보 키와 자료 ID가 일치하지 않습니다.')
                source = items.get(rid) if isinstance(rid, str) else None
                if (not source or source.get('type') != ('course' if key == 'courses' else 'book')
                        or not source.get('usable') or pool['name'] not in (source.get('skills') or [])
                        or rid not in provided[key] or rid in seen or (key == 'books' and rid not in candidates)
                        or (key == 'courses' and not course_levels.eligible(
                            {**source, 'cost': provided[key][rid][1].get('cost')}, track))
                        or (key == 'courses' and pool['name'] not in course_eligibility[rid])):
                    raise RecommendationError('후보에 없거나 중복된 자료입니다.')
                card = deepcopy(candidates.get(rid) or provided[key][rid][1])
                if key == 'courses':
                    card.pop('unverifiedTargetTopics', None)
                    gaps = resource_evidence.target_gaps(crash_cache[rid], pool['name'])
                    if gaps:
                        card['unverifiedTargetTopics'] = gaps
                if rid not in candidates:
                    card.pop('retrievalScore', None)
                    card.update(sharedCandidate=True, sourceSkill=provided[key][rid][0])
                if any(field in recommendation and (not isinstance(recommendation[field], str) or not recommendation[field].strip()) for field in ('why', 'knowledge')):
                    raise RecommendationError('추천 이유와 기대 지식 역량이 필요합니다.')
                seen.add(rid)
                cards.append({**card, 'why': recommendation.get('why', '').strip(),
                              'knowledge': recommendation.get('knowledge', '').strip(), 'aiRecommended': len(cards) == 0})
            output[key] = cards
        output['selectedCourse'] = output['courses'][0]['id'] if output['courses'] else None
        output['selectedBooks'] = [output['books'][0]['id']] if output['books'] else []
        eligible = [card for rid, (_, card) in provided['courses'].items() if pool['name'] in course_eligibility[rid]]
        diagnostic = _diagnostic(row, 'course', bool(eligible), bool(output['courses']))
        if diagnostic and diagnostic['reason'] == 'stack_mismatch':
            profiles = [crash_cache[card['id']]['suitability'][pool['name']] for card in eligible]
            if any(p['missingStack'] for p in profiles) and not any(p['conflictingStack'] for p in profiles):
                diagnostic = _missing_stack_diagnostic(profiles)
        if diagnostic:
            output['courseDiagnostic'] = _display_diagnostic(diagnostic, candidate_titles)
        elif not is_crash and not output['courses']:
            output['courseDiagnostic'] = rejected_diagnostics.get(pool['name']) or _course_gap(pool['name'], eligible, crash_cache)
        diagnostic = _diagnostic(row, 'book', bool(pool['books']), bool(output['books']))
        if not pool['books']:
            output['bookDiagnostic'] = _no_candidates('도서')
        elif diagnostic:
            output['bookDiagnostic'] = _display_diagnostic(diagnostic, candidate_titles)
        elif not output['books']:
            output['bookDiagnostic'] = {'reason': 'insufficient_evidence',
                                        'detail': '도서 후보가 있었으나 모델 응답에서 선택 근거를 확인하지 못했습니다.'}
        result.append(output)
    if is_crash:
        _finalize_crash(result, pools, selection, project, crash_cache)
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


def recommend_from_catalog(ctx: Any, pre: dict, course: dict | None = None, *,
                           completed: frozenset[str] = frozenset()) -> dict:
    from app import catalog
    from app.agents import runtime
    if not ctx.live:
        raise RecommendationError('AI 추천에는 사용 가능한 실제 모델이 필요합니다.')
    from app.services.resource_rag import retrieve
    items = catalog.items()
    if completed:
        items = {rid: item for rid, item in items.items() if rid not in completed or item['type'] != 'course'}
    from app.learner_knowledge import from_profile,hr_context
    project=dict(pre['project'],learnerKnowledge=from_profile(pre.get('profile')),hrContext=hr_context(pre.get('profile')))
    project['selectedCourse'] = deepcopy(course)
    selection = dict(pre['selection'], commonApplications=pre.get('_commonApplications') or {})
    pools, retrieval = retrieve(project, selection, items, course)
    result = recommend_resources(project, selection, items,
        lambda system, payload: runtime.llm_json(ctx, system, payload, role='resources'), course=course, retrieved_pools=pools)
    result['retrieval'] = retrieval
    return result


def validate_skill_order(recommendations: dict, order: list[str]) -> None:
    names = {row['name'] for row in recommendations['skills']}
    if not isinstance(order, list) or any(not isinstance(name, str) for name in order) or len(order) != len(names) or len(set(order)) != len(order) or set(order) != names:
        raise RecommendationError('선정 스킬을 빠짐없이 한 번씩 포함한 순서가 필요합니다.')

"""Crash 자료의 관련성 범위 안에서 학습시간·선정 스킬 공동 학습 근거를 평가한다."""
from __future__ import annotations

import math
from app import course_levels
from app.services.course_focus import distinct_courses
from copy import deepcopy
from app.services.resource_evidence import course_applicable, facts, focus_priority, hours, suitable, suitability_key, target_gaps

VERSION = 'crash-short-courses/v15-preserve-valid-model-choices'


def is_crash(course) -> bool:
    return (course.get('id') if isinstance(course, dict) else course) == 'A2'


def quality(info: dict, skill: str) -> tuple:
    return (not suitable(info, skill), *suitability_key(info, skill))


def time_certainty(row: dict) -> str:
    if hours(row) is None or row.get('timeStatus') == 'unknown':
        return 'unknown'
    if 'hours' in (row.get('estimated') or []) or row.get('timeStatus') == 'estimated':
        return 'estimated'
    return 'confirmed'


def rank(rows: list[dict], project: dict, selection: dict, skill: dict, *, limit: int | None = None,
         cache: dict | None = None) -> list[dict]:
    """필수 근거를 충족한 후보는 벡터 점수로 제거하지 않는다."""
    rows = [row for row in rows if course_levels.eligible(row, 'A2')]
    cache = cache if cache is not None else {}
    for row in rows:
        if row['id'] not in cache:
            cache[row['id']] = facts(row, project, selection)
    def topic_quality(row):
        info = cache[row['id']]
        return (not suitable(info, skill['name']), *suitability_key(info, skill['name']))
    def key(row):
        info = cache[row['id']]
        duration = hours(row)
        certainty = ('confirmed', 'estimated', 'unknown').index(time_certainty(row))
        coverage = max(1, sum(suitable(info, selected['name']) for selected in selection['skills']))
        # 여러 스킬의 학습 근거가 있을 때만 같은 강좌를 공유할 수 있는 효율을 인정한다.
        effective = duration / coverage if duration is not None else math.inf
        return (*topic_quality(row), certainty, effective, duration if duration is not None else math.inf, -coverage,
                -float(row.get('retrievalScore') or 0), str(row.get('title') or ''), row['id'])

    rows.sort(key=key)
    if limit is None:
        return rows
    return distinct_courses(rows)[:limit]


def shortest_bundle(pools: list[dict], project: dict, selection: dict, cache: dict) -> dict[str, dict]:
    """확인된 실제 커버리지가 있는 스킬을 모두 포함한 고유 강좌 집합을 계산한다."""
    courses, coverage = {}, {}
    names = []
    for pool in pools:
        applicable = []
        for row in pool['courses']:
            if not course_levels.eligible(row, 'A2'):
                continue
            rid = row['id']
            if rid not in cache:
                cache[rid] = facts(row, project, selection)
            if suitable(cache[rid], pool['name']):
                applicable.append(row)
        # 명시한 세부 대상을 가장 많이 확인한 강좌만 남긴다. 더 적게 다루는 짧은 강좌로 시간을 줄이지 않는다.
        fewest = min((len(target_gaps(cache[row['id']], pool['name'])) for row in applicable), default=0)
        applicable = [row for row in applicable if len(target_gaps(cache[row['id']], pool['name'])) == fewest]
        focused = [row for row in applicable if focus_priority(cache[row['id']], pool['name'])]
        applicable = focused or applicable
        if not applicable:
            continue
        bit = 1 << len(names)
        names.append(pool['name'])
        for row in applicable:
            rid = row['id']
            courses.setdefault(rid, row)
            coverage[rid] = coverage.get(rid, 0) | bit

    # 스킬 최대 3개, 상태 최대 32개. 20개 검토 창 전체에서도 강좌마다 한 번만 시간을 합산한다.
    best = {0: (0, 0, 0., 0, ())}
    for rid, row in sorted(courses.items()):
        certainty = time_certainty(row)
        for mask, (unknown, estimated, total, count, ids) in list(best.items()):
            combined = mask | coverage[rid]
            if combined == mask:
                continue
            cost = (unknown + (certainty == 'unknown'), estimated + (certainty == 'estimated'),
                    total + (hours(row) or 0), count + 1, (*ids, rid))
            if combined not in best or cost < best[combined]:
                best[combined] = cost
    ids = best[(1 << len(names)) - 1][-1]
    pools_by_name = {pool['name']: pool for pool in pools}
    return {name: next(row for row in pools_by_name[name]['courses']
                       if row['id'] in ids and coverage[row['id']] & (1 << index))
            for index, name in enumerate(names)}


def align_shared_courses(pools: list[dict], project: dict, selection: dict, cache: dict | None = None) -> list[dict]:
    chosen = shortest_bundle(pools, project, selection, cache if cache is not None else {})
    return [{**pool, 'courses': [chosen[pool['name']]] + [row for row in pool['courses']
                                                        if row['id'] != chosen[pool['name']]['id']]}
            if pool['name'] in chosen else pool for pool in pools]


def share_candidates(pools: list[dict], project: dict, selection: dict, sources: dict, *, cache: dict) -> list[dict]:
    """이미 제공된 강좌를 실제 학습 근거가 맞는 스킬에 공유해 총시간을 비교한다."""
    provided = {row['id']: (pool['name'], row) for pool in pools for row in pool['courses']
                if course_levels.eligible(row, 'A2')}
    for rid, (_, row) in provided.items():
        if rid not in cache:
            cache[rid] = facts(sources.get(rid, row), project, selection)
    result = []
    skill_specs = {skill['name']: skill for skill in selection['skills']}
    for pool in pools:
        local = {row['id']: row for row in pool['courses'] if course_levels.eligible(row, 'A2')}
        shared = list(local.values())
        for rid, (origin, row) in provided.items():
            source = sources.get(rid) or {}
            info = cache[rid]
            if (rid in local or source.get('type') != 'course' or not source.get('usable')
                    or pool['name'] not in (source.get('skills') or []) or not suitable(info, pool['name'])
                    or not course_applicable(info, skill_specs[pool['name']])):
                continue
            card = deepcopy(row)
            card.pop('retrievalScore', None)
            card.update(sharedCandidate=True, sourceSkill=origin)
            shared.append(card)
        result.append({**pool, 'courses': shared})
    aligned = align_shared_courses(result, project, selection, cache)
    shortlist = []
    for pool in aligned:
        rows = pool['courses']
        ordered = rank(rows, project, selection, {'name': pool['name']}, limit=6, cache=cache)
        if (rows and ordered and course_levels.eligible(rows[0], 'A2')
                and (len(pools) > 1 or rows[0]['id'] in {r['id'] for r in ordered})
                and suitable(cache[rows[0]['id']], pool['name'])
                and focus_priority(cache[rows[0]['id']], pool['name']) >= focus_priority(cache[ordered[0]['id']], pool['name'])):
            ordered = distinct_courses([rows[0], *ordered, *rows])
        shortlist.append({**pool, 'courses': ordered[:6]})
    return shortlist


def study_plan(pools: list[dict], project: dict, selection: dict, references: dict, *, cache: dict) -> dict | None:
    """모델에 보여주는 짧은 기본 조합. 최종 추천·저장 선택을 강제로 바꾸지 않는다."""
    if not pools or any(not pool['courses'] for pool in pools):
        return None
    for pool in pools:
        for row in pool['courses']:
            if row['id'] not in cache:
                cache[row['id']] = facts(row, project, selection)
    aligned = align_shared_courses(pools, project, selection, cache)
    picked = [pool['courses'][0] for pool in aligned]
    if any(not course_levels.eligible(row, 'A2') or not suitable(cache[row['id']], pool['name'])
           for pool, row in zip(aligned, picked)):
        return None
    unique = {row['id']: row for row in picked}
    statuses = {time_certainty(row) for row in unique.values()}
    confirmed = statuses == {'confirmed'}
    total = math.fsum(hours(row) for row in unique.values()) if confirmed else None
    skills = []
    for index, (pool, row) in enumerate(zip(aligned, picked)):
        profile = cache[row['id']]['suitability'][pool['name']]
        detail = {'name': pool['name'], 'key': references[row['id']],
                  'evidenceLevel': profile['evidenceLevel'], 'evidenceUnitIndices': profile['unitIndices'],
                  'hasDescriptionEvidence': bool(profile['appliedDescription'])}
        if target_gaps(cache[row['id']], pool['name']):
            detail['unverifiedTargetTopics'] = target_gaps(cache[row['id']], pool['name'])
        if confirmed:
            other = {card['id']: hours(card) for i, card in enumerate(picked) if i != index}
            # 적용 근거가 없거나 기본안이 다루는 세부 대상을 빠뜨리는 짧은 강좌를 시간 절감안으로 보여 주지 않는다.
            gaps = set(target_gaps(cache[row['id']], pool['name']))
            detail['singleSwapExtraHours'] = {
                references[alt['id']]: round(math.fsum({**other, alt['id']: hours(alt)}.values()) - total, 3)
                for alt in pool['courses'] if alt['id'] in references and alt['id'] != row['id']
                and time_certainty(alt) == 'confirmed' and suitable(cache[alt['id']], pool['name'])
                and set(target_gaps(cache[alt['id']], pool['name'])) <= gaps
            }
        skills.append(detail)
    return {'skills': skills,
            'uniqueCourses': len(unique), 'uniqueHours': total,
            'hoursConfirmed': confirmed,
            'timeStatus': 'unknown' if 'unknown' in statuses else 'confirmed' if confirmed else 'estimated',
            'basis': '서버가 계산한 스킬별 짧은 기본안이다. key의 목차·소개로 핵심 학습 근거를 확인한다.'}

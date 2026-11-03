"""Crash 자료의 관련성 범위 안에서 학습시간·선정 스킬 공동 학습 근거를 평가한다."""
from __future__ import annotations

import math
from copy import deepcopy
from itertools import product
from app.services.resource_evidence import facts, hours, suitable, suitability_key

VERSION = 'crash-short-courses/20261104-v5-stage-evidence'
REVIEW_LIMIT = 20
SIMILARITY_WINDOW = .10


def is_crash(course) -> bool:
    return (course.get('id') if isinstance(course, dict) else course) == 'A2'


def quality(info: dict, skill: str) -> tuple:
    return suitability_key(info, skill)


def rank(rows: list[dict], project: dict, selection: dict, skill: dict, *, limit: int | None = None,
         cache: dict | None = None, similarity_gate: bool = True) -> list[dict]:
    """입력 시간을 바꾸지 않고 관련성이 가까운 후보를 시간 효율 순으로 정렬한다."""
    rows = list(rows)
    cache = cache if cache is not None else {}
    for row in rows:
        if row['id'] not in cache:
            cache[row['id']] = facts(row, project, selection)
    # 소개 단원의 높은 유사도가 실제 구현 후보를 검토 창에서 밀어내지 않게 한다.
    best = min((quality(cache[row['id']], skill['name']) for row in rows), default=None)
    scores = [float(row['retrievalScore']) for row in rows if row.get('retrievalScore') is not None
              and quality(cache[row['id']], skill['name']) == best]
    if similarity_gate and scores:
        minimum = max(scores) - SIMILARITY_WINDOW
        rows = [row for row in rows if quality(cache[row['id']], skill['name']) != best
                or (row.get('retrievalScore') is not None and float(row['retrievalScore']) >= minimum)]

    def key(row):
        if row['id'] not in cache:
            cache[row['id']] = facts(row, project, selection)
        info = cache[row['id']]
        duration = hours(row)
        estimated = 'hours' in (row.get('estimated') or []) or row.get('timeStatus') == 'estimated'
        certainty = 2 if duration is None else 1 if estimated else 0
        coverage = max(1, sum(suitable(info, selected['name']) for selected in selection['skills']))
        # 여러 스킬의 학습 근거가 있을 때만 같은 강좌를 공유할 수 있는 효율을 인정한다.
        effective = duration / coverage if duration is not None else math.inf
        return (*quality(info, skill['name']), certainty, effective, duration or math.inf, -coverage,
                -float(row.get('retrievalScore') or 0), str(row.get('title') or ''), row['id'])

    rows.sort(key=key)
    if limit is None or len(rows) <= limit:
        return rows
    # 짧은 자료만으로 여섯 칸을 채워 기존의 의미상 가까운 강좌를 모두 잃지 않게 한다.
    # 같은 학습 근거·기술 조건 안에서 최대 두 칸을 벡터 상위 후보에 남긴다.
    best = quality(cache[rows[0]['id']], skill['name'])
    grounded = [row for row in rows if quality(cache[row['id']], skill['name']) == best
                and row.get('retrievalScore') is not None]
    semantic = sorted(grounded, key=lambda row: (-float(row['retrievalScore']), row['id']))[:min(2, limit)]
    chosen = {row['id']: row for row in semantic}
    for row in rows:
        if len(chosen) >= limit:
            break
        chosen.setdefault(row['id'], row)
    return sorted(chosen.values(), key=key)


def align_shared_courses(pools: list[dict], project: dict, selection: dict, cache: dict | None = None) -> list[dict]:
    """선택 스킬을 유지하며 첫 추천의 고유 강좌 시간 합을 비교한다. 나머지 후보는 보존한다."""
    if not 1 < len(pools) <= 5 or any(not pool['courses'] for pool in pools):
        return pools
    cache = cache if cache is not None else {}
    groups = []
    for pool in pools:
        for row in pool['courses']:
            if row['id'] not in cache:
                cache[row['id']] = facts(row, project, selection)
        best = min(quality(cache[row['id']], pool['name']) for row in pool['courses'])
        if not any(suitable(cache[row['id']], pool['name']) for row in pool['courses']):
            return pools  # 해당 스킬의 적용 단계·기술 근거가 없으면 공동 학습을 확정하지 않는다.
        if (pool.get('courseDiagnostic') or {}).get('reason') == 'longer_for_coverage':
            preferred = pool['courses'][0]
            if not suitable(cache[preferred['id']], pool['name']):
                return pools
            groups.append([preferred])  # 더 긴 강좌가 필요한 학습 내용을 모델이 명시한 선택은 유지한다.
        else:
            groups.append([row for row in pool['courses'] if quality(cache[row['id']], pool['name']) == best][:6])

    def cost(bundle):
        unique = {row['id']: row for row in bundle}
        unknown = sum(hours(row) is None for row in unique.values())
        estimated = sum('hours' in (row.get('estimated') or []) or row.get('timeStatus') == 'estimated' for row in unique.values())
        total = sum(hours(row) or 0 for row in unique.values())
        return (unknown, estimated, total, len(unique), tuple(row['id'] for row in bundle))

    chosen = min(product(*groups), key=cost)  # 사용자 확정 5스킬에서도 최대 6^5=7,776개, 추가 모델·DB 호출 없음.
    return [{**pool, 'courses': [selected] + [row for row in pool['courses'] if row['id'] != selected['id']]}
            for pool, selected in zip(pools, chosen)]


def share_candidates(pools: list[dict], project: dict, selection: dict, sources: dict, *, cache: dict) -> list[dict]:
    """이미 제공된 강좌를 실제 학습 근거가 맞는 스킬에 공유해 총시간을 비교한다."""
    provided = {row['id']: (pool['name'], row) for pool in pools for row in pool['courses']}
    for rid, (_, row) in provided.items():
        if rid not in cache:
            cache[rid] = facts(sources.get(rid, row), project, selection)
    result = []
    for pool in pools:
        local = {row['id']: row for row in pool['courses']}
        best = min((quality(cache[rid], pool['name']) for rid in local), default=None)
        shared = list(local.values())
        for rid, (origin, row) in provided.items():
            source = sources.get(rid) or {}
            info = cache[rid]
            if (rid in local or source.get('type') != 'course' or not source.get('usable')
                    or pool['name'] not in (source.get('skills') or []) or not suitable(info, pool['name'])
                    or (best is not None and quality(info, pool['name']) > best)):
                continue
            card = deepcopy(row)
            card.pop('retrievalScore', None)
            card.update(sharedCandidate=True, sourceSkill=origin)
            shared.append(card)
        ordered = rank(shared, project, selection, {'name': pool['name']}, limit=6, cache=cache, similarity_gate=False)
        result.append({**pool, 'courses': ordered})
    return align_shared_courses(result, project, selection, cache)


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
    if any(not suitable(cache[row['id']], pool['name']) for pool, row in zip(aligned, picked)):
        return None
    unique = {row['id']: row for row in picked}
    confirmed = all(hours(row) is not None and 'hours' not in (row.get('estimated') or [])
                    and row.get('timeStatus') != 'estimated' for row in unique.values())
    return {'skills': [{'name': pool['name'], 'key': references[row['id']]} for pool, row in zip(aligned, picked)],
            'uniqueCourses': len(unique), 'uniqueHours': sum(hours(row) or 0 for row in unique.values()) if confirmed else None,
            'hoursConfirmed': confirmed,
            'basis': '제공 후보의 학습 근거·전체 시간을 비교한 참고 조합이며 세부 학습 목표의 충족은 모델이 확인한다.'}

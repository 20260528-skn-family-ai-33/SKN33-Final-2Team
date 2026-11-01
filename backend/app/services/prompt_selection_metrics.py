"""최종 확정 선택의 집계 계약. DB·모델 호출이나 프롬프트 적용은 하지 않는다.

생성된 안이 아니라 실제 비교 화면에 표시된 안을 받아야 한다. 버전이 없는 과거
기록을 현재 프롬프트에 귀속시키지 않고, 세 코스를 비교한 동일 조건 표본만 집계한다.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime

COURSES = frozenset(('A1', 'A2', 'A3'))
VERSION = 'final-roadmap-selection/v1'


def confirmed_decision(decision_id: str, finalized_at: datetime, selected: str, displayed: list[dict]) -> dict:
    """최종 확정 트랜잭션에서 저장할 최소 기록. 직원·기획서 원문은 포함하지 않는다."""
    if not decision_id or finalized_at.tzinfo is None or finalized_at.utcoffset() is None:
        raise ValueError('확정 식별자와 시간대가 있는 확정 시각이 필요합니다.')
    alternatives = [{key: row.get(key) for key in ('course', 'optionId', 'promptVersionId', 'source')} for row in displayed]
    return {'version': VERSION, 'eventType': 'roadmap_confirmed', 'decisionId': decision_id,
            'finalizedAt': finalized_at.isoformat(), 'selected': selected, 'displayed': alternatives}


def _ineligible(event: dict) -> str | None:
    if event.get('eventType') != 'roadmap_confirmed':
        return 'not_finalized'
    if event.get('version') != VERSION or not event.get('decisionId') or not event.get('finalizedAt'):
        return 'missing_provenance'
    try:
        when = datetime.fromisoformat(event['finalizedAt'])
        if when.tzinfo is None or when.utcoffset() is None:
            return 'missing_provenance'
    except (TypeError, ValueError):
        return 'missing_provenance'
    rows = event.get('displayed')
    if not isinstance(rows, list) or len(rows) != 3 or any(not isinstance(row, dict) for row in rows):
        return 'incomplete_comparison'
    if any(row.get('course') not in COURSES for row in rows) or {row['course'] for row in rows} != COURSES:
        return 'incomplete_comparison'
    if event.get('selected') not in COURSES:
        return 'invalid_selection'
    if any(not isinstance(row.get(key), str) or not row[key].strip() for row in rows for key in ('optionId', 'promptVersionId')):
        return 'missing_provenance'
    if any(row.get('source') not in ('ollama', 'openai') for row in rows):
        return 'non_live_sample'
    return None


def summarize(events: list[dict]) -> dict:
    """최종 확정 1회당 1표. 중간 클릭·불완전 비교·가데이터·버전 미상은 별도 집계."""
    decisions: dict[str, dict] = {}
    conflicts: set[str] = set()
    skipped = Counter()
    duplicates = 0
    for event in events:
        reason = _ineligible(event)
        if reason:
            skipped[reason] += 1
            continue
        key = event['decisionId']
        canonical = deepcopy(event)
        canonical['displayed'] = sorted(canonical['displayed'], key=lambda row: row['course'])
        if key in decisions:
            if decisions[key] == canonical:
                duplicates += 1
            else:
                conflicts.add(key)
        else:
            decisions[key] = canonical
    counts: dict[tuple, Counter] = {}
    for key, event in decisions.items():
        if key in conflicts:
            continue
        for row in event['displayed']:
            bucket = counts.setdefault((row['course'], row['promptVersionId'], row['source']), Counter())
            bucket['displayed'] += 1
            bucket['selected'] += int(row['course'] == event['selected'])
    return {'version': VERSION, 'basis': 'final_confirmation', 'eligibleDecisions': len(decisions) - len(conflicts),
            'duplicateEvents': duplicates, 'conflictingDecisions': len(conflicts), 'skipped': dict(skipped),
            'rates': [{'course': key[0], 'promptVersionId': key[1], 'source': key[2], **dict(value),
                       'selectionRate': value['selected'] / value['displayed']} for key, value in sorted(counts.items())]}

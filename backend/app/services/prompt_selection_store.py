"""기존 초안·로드맵 JSON에 비교 출처를 연결한다. 새 표/스키마를 만들지 않는다."""
from datetime import datetime, timezone
from app import db
from app.services.prompt_selection_metrics import COURSES, confirmed_decision


def comparison_snapshot(generation: dict, displayed: list[dict] | None) -> dict | None:
    """클라이언트가 표시한 세 안을 서버의 현재 옵션과 대조한다. 출처 미상은 통계에서 제외."""
    if not generation.get('key') or not isinstance(displayed, list) or len(displayed) != 3 or any(not isinstance(row, dict) for row in displayed):
        return None
    if any(not isinstance(row.get('course'), str) or row['course'] not in COURSES for row in displayed) or {row['course'] for row in displayed} != COURSES:
        return None
    rows = []
    for visible in displayed:
        course = visible['course']
        option = (generation.get('options') or {}).get(course) or {}
        source = option.get('promptProvenance') or {}
        if (generation.get('regenRun') or {}).get(course) or not option.get('optionId') or not source.get('promptVersionId'):
            return None
        if visible.get('optionId') != option['optionId'] or visible.get('promptVersionId') != source['promptVersionId']:
            return None
        rows.append({'course': course, 'optionId': option['optionId'], 'promptVersionId': source['promptVersionId'], 'source': source.get('source')})
    return {'generationKey': generation.get('key'), 'displayed': rows}


def confirmation_evidence(decision_id: str, draft: dict, finalized_at: datetime | None = None) -> dict | None:
    """확정 시에도 버전을 확인해 표시 후 재생성된 안을 이전 비교로 집계하지 않는다."""
    snapshot = draft.get('selectionComparison')
    generation = draft.get('gen') or {}
    if not snapshot or snapshot.get('generationKey') != generation.get('key') or draft.get('chosen') not in COURSES:
        return None
    checked = comparison_snapshot(generation, snapshot.get('displayed'))
    if not checked:
        return None
    return confirmed_decision(decision_id, finalized_at or datetime.now(timezone.utc), draft['chosen'], checked['displayed'])


def read_decisions() -> list[dict]:
    """실제 최종 확정 저장이 성공한 로드맵의 근거만 조회한다. 과거 기록을 추정하지 않는다."""
    rows = db.all_("SELECT baseline_content -> 'selectionEvidence' AS evidence FROM public.roadmaps WHERE selected_at IS NOT NULL AND baseline_content ? 'selectionEvidence'")
    return [row['evidence'] for row in rows if isinstance(row.get('evidence'), dict)]

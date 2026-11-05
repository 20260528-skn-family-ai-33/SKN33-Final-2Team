"""완료 알림 (#82 · 설계서 v1.7 에 없는 추가). 직원 계정만 쓴다(관리자는 403). 남의 알림은 읽음 처리할 수 없다(404)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import Account, require_employee
from ..services import notifications as NT

r = APIRouter(prefix='/api/v1/notifications')


@r.get('')
def api_inbox(a: Account = Depends(require_employee)):
    return NT.inbox(a.id)


@r.post('/read-all')
def api_read_all(a: Account = Depends(require_employee)):
    return NT.read_all(a.id)


# 부서장이 직원의 로드맵·보고서 화면을 열면 그 대상의 알림을 읽음으로(#96 · body: {kind: roadmap|report, id})
@r.post('/read-target')
def api_read_target(body: dict, a: Account = Depends(require_employee)):
    return NT.read_target(a.id, body.get('kind', ''), body.get('id', ''))


@r.post('/{notification_id}/read')
def api_read(notification_id: str, a: Account = Depends(require_employee)):
    return NT.read(a.id, notification_id)

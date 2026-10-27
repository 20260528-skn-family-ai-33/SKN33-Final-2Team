"""부서장 화면 (API-55~59). 소속 관계는 서버가 확인한다(소속이 아니면 403 · 설계서 6.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import Account, require_employee
from ..errors import forbidden, not_found
from ..services import plans as PL
from ..services import profile

r = APIRouter(prefix='/api/v1/team')


def _head(a: Account) -> int:
    v = profile.view(a.id)
    if not v or not v['supervisor'] or not v['members']:
        raise forbidden('부서장 권한이 있는 계정만 볼 수 있어요')
    return a.id


@r.get('/members')
def api_members(a: Account = Depends(require_employee)):
    return PL.team_members(_head(a))


@r.get('/members/{user_id}/plans')
def api_member_plans(user_id: int, a: Account = Depends(require_employee)):
    return PL.member_state(_head(a), user_id)


def _owner_of(head: int, plan_id: str) -> int:
    for uid in profile.member_ids(head):
        if PL._base_rows(uid, plan_id):
            return uid
    raise not_found('소속 직원의 로드맵')


@r.get('/plans/{plan_id}')
def api_team_plan(plan_id: str, a: Account = Depends(require_employee)):
    head = _head(a)
    uid = _owner_of(head, plan_id)
    rec = PL.record(PL._base_rows(uid, plan_id)[0], for_mgr=True)
    one = {rec['id']: rec}
    return {'userId': str(uid), 'plan': rec, 'reports': [x for x in PL.reports(uid, for_mgr=True) if x['planId'] == plan_id], 'res': PL.resources_of(one), 'reg': PL.reg_of(one)}


@r.post('/plans/{plan_id}/comments')
def api_team_comment(plan_id: str, body: dict, a: Account = Depends(require_employee)):
    head = _head(a)
    uid = _owner_of(head, plan_id)
    return {'commentId': PL.send_comment(head, uid, plan_id, body), 'userId': str(uid)}


# 설계서 v1.7 에 없는 추가(10/23 사용자 요청): 보낸 코멘트 고치기. 삭제 API 는 두지 않는다
@r.patch('/plans/{plan_id}/comments/{comment_id}')
def api_team_comment_edit(plan_id: str, comment_id: str, body: dict, a: Account = Depends(require_employee)):
    head = _head(a)
    uid = _owner_of(head, plan_id)
    return {'commentId': comment_id, 'userId': str(uid), 'changed': PL.edit_comment(head, uid, plan_id, comment_id, body)}


@r.get('/reports/{report_id}')
def api_team_report(report_id: str, a: Account = Depends(require_employee)):
    head = _head(a)
    for uid in profile.member_ids(head):
        x = next((x for x in PL.reports(uid, for_mgr=True) if x['id'] == report_id), None)
        if x:
            return dict(x, userId=str(uid))
    raise not_found('소속 직원의 결과 보고서')

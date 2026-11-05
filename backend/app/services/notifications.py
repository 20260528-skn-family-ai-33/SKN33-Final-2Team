"""완료 알림 (#82): 로드맵 확정·결과 보고서 작성이 끝나면 작성한 직원 본인과 그 직원 부서의 부서장에게 남긴다.

저장: app_ext.notifications. 받는 사람(recipient)·작성한 직원(actor)·종류(roadmap|report)·받는 쪽(self|head)·대상 id 만 두고,
화면 문구와 이동할 주소는 화면이 만든다(로드맵 제목이 바뀌어도 알림이 따라간다).
부서장 범위는 services/profile.members_of 와 같다: 같은 부서의 부서장만 그 부서 직원을 보고, 부서장 본인의 계획은 본인만 본다.
알림을 넣는 함수는 로드맵·보고서를 저장하는 트랜잭션(t) 안에서 부른다. 저장이 실패하면 알림도 남지 않는다.
"""
from __future__ import annotations

import uuid

from .. import db
from ..errors import ApiError, bad

LIMIT = 50

# h = 부서장(받는 사람), w = 작성한 직원. profile.members_of 와 같은 조건(부서장이 아닌 같은 부서 직원)
HEAD_SEES = 'h.is_department_head AND NOT w.is_department_head AND h.department_id = w.department_id'

_INSERT = f"""INSERT INTO app_ext.notifications(recipient_id, actor_id, kind, audience, roadmap_id, report_id)
    SELECT w.employee_id, w.employee_id, CAST(:k AS text), 'self', CAST(:r AS uuid), CAST(:rep AS uuid)
      FROM public.employees w WHERE w.employee_id = :e
    UNION ALL
    SELECT h.employee_id, w.employee_id, CAST(:k AS text), 'head', CAST(:r AS uuid), CAST(:rep AS uuid)
      FROM public.employees w JOIN public.employees h ON {HEAD_SEES} WHERE w.employee_id = :e"""

# 부서장 알림은 그 직원이 지금도 소속일 때만 보인다(부서 이동 뒤 남은 알림으로 다른 부서 직원의 로드맵 제목이 보이지 않게)
_VISIBLE = f"(n.audience = 'self' OR ({HEAD_SEES}))"
_FROM = """FROM app_ext.notifications n
    JOIN public.employees w ON w.employee_id = n.actor_id
    JOIN public.employees h ON h.employee_id = n.recipient_id
    JOIN public.roadmaps r ON r.roadmap_id = n.roadmap_id"""


def roadmap_created(t: db.Tx, employee_id: int, roadmap_id: str) -> None:
    """로드맵 확정(drafts.confirm)과 같은 트랜잭션에서 부른다"""
    t.run(_INSERT, e=employee_id, k='roadmap', r=roadmap_id, rep=None)


def report_created(t: db.Tx, employee_id: int, roadmap_id: str, report_id: str) -> None:
    """결과 보고서 저장(plans.report_start 작업)과 같은 트랜잭션에서 부른다.
    확인 전 보고서를 다시 만들면 이전 보고서가 지워지면서 그 알림도 함께 지워진다(report_id ON DELETE CASCADE)"""
    t.run(_INSERT, e=employee_id, k='report', r=roadmap_id, rep=report_id)


def _item(n: dict) -> dict:
    return {'id': str(n['notification_id']), 'kind': n['kind'], 'audience': n['audience'],
            'employee': {'id': str(n['actor_id']), 'name': n['actor_name']},
            'planId': str(n['roadmap_id']), 'planTitle': n['plan_title'] or '', 'track': n['track'] or '',
            'reportId': str(n['report_id']) if n['report_id'] else None,
            'createdAt': n['created_at'].isoformat(), 'read': n['read_at'] is not None}


def inbox(employee_id: int, limit: int = LIMIT) -> dict:
    """내 알림(최근 limit 건)과 읽지 않은 수. 읽지 않은 수는 목록 길이와 관계없이 전체를 센다"""
    rows = db.all_(f"""SELECT n.notification_id, n.kind, n.audience, n.actor_id, w.name AS actor_name, n.roadmap_id, n.report_id, n.created_at, n.read_at,
                              coalesce(nullif(r.content->>'displayTitle', ''), r.content->>'goal') AS plan_title, r.content->>'opt' AS track
                       {_FROM} WHERE n.recipient_id = :e AND {_VISIBLE}
                       ORDER BY n.created_at DESC, n.notification_id LIMIT :n""", e=employee_id, n=limit)
    unread = db.val(f'SELECT count(*) {_FROM} WHERE n.recipient_id = :e AND n.read_at IS NULL AND {_VISIBLE}', e=employee_id)
    return {'items': [_item(n) for n in rows], 'unread': int(unread or 0)}


def _missing() -> ApiError:
    return ApiError(404, 'NOT_FOUND', '알림을 찾을 수 없어요')


def read(employee_id: int, notification_id: str) -> dict:
    """한 건 읽음. 내 알림이 아니면(다른 직원 것·없는 id) 404"""
    try:
        nid = str(uuid.UUID(str(notification_id)))
    except ValueError:
        raise _missing() from None
    with db.tx() as t:
        n = t.run('UPDATE app_ext.notifications SET read_at = coalesce(read_at, now()) WHERE notification_id = CAST(:i AS uuid) AND recipient_id = :e',
                  i=nid, e=employee_id)
    if not n:
        raise _missing()
    return inbox(employee_id)


def read_all(employee_id: int) -> dict:
    with db.tx() as t:
        t.run('UPDATE app_ext.notifications SET read_at = now() WHERE recipient_id = :e AND read_at IS NULL', e=employee_id)
    return inbox(employee_id)


# ── 부서장의 확인 전 로드맵·보고서 (#96) ──
# '확인 전' = 부서장이 아직 읽지 않은 소속 직원 알림. 알림 창에서 누르거나 그 직원의 로드맵·보고서 화면을 열면(read_target) 읽음이 된다.
# 알림이 없는 예전 로드맵·보고서(#82 이전)는 확인 전으로 세지 않는다.
_TARGET = {'roadmap': 'n.roadmap_id', 'report': 'n.report_id'}


def unseen_counts(head_id: int) -> dict[int, dict]:
    """소속 직원별 확인 전 로드맵·보고서 수(대상 기준). 지금도 같은 부서인 직원만 센다(inbox 와 같은 _VISIBLE)"""
    rows = db.all_(f"""SELECT n.actor_id, count(DISTINCT n.roadmap_id) FILTER (WHERE n.kind = 'roadmap') AS plans,
                              count(DISTINCT n.report_id) FILTER (WHERE n.kind = 'report') AS reports
                       {_FROM} WHERE n.recipient_id = :e AND n.audience = 'head' AND n.read_at IS NULL AND {_VISIBLE}
                       GROUP BY n.actor_id""", e=head_id)
    return {int(r['actor_id']): {'plans': int(r['plans'] or 0), 'reports': int(r['reports'] or 0)} for r in rows}


def unseen_targets(head_id: int, member_id: int) -> dict:
    """한 소속 직원의 확인 전 로드맵 id·보고서 id(부르는 쪽이 소속을 확인한 뒤 부른다)"""
    rows = db.all_("""SELECT DISTINCT n.kind, n.roadmap_id, n.report_id FROM app_ext.notifications n
                       WHERE n.recipient_id = :h AND n.actor_id = :m AND n.audience = 'head' AND n.read_at IS NULL""", h=head_id, m=member_id)
    return {'plans': sorted({str(r['roadmap_id']) for r in rows if r['kind'] == 'roadmap'}),
            'reports': sorted({str(r['report_id']) for r in rows if r['kind'] == 'report' and r['report_id']})}


def read_target(employee_id: int, kind: str, target_id: str) -> dict:
    """그 로드맵(kind=roadmap)·보고서(kind=report)를 열었을 때 그 대상의 내 알림을 모두 읽음으로.
    읽을 알림이 없으면(예전 기록·이미 읽음) 바꾸지 않는다. 바뀐 목록과 바뀐 수(changed)를 돌려준다"""
    col = _TARGET.get(str(kind))
    if not col:
        raise bad('알림 대상 종류는 roadmap 또는 report 예요')
    try:
        tid = str(uuid.UUID(str(target_id)))
    except ValueError:
        raise _missing() from None
    with db.tx() as t:
        n = t.run(f"""UPDATE app_ext.notifications n SET read_at = now()
                      WHERE n.recipient_id = :e AND n.read_at IS NULL AND n.kind = :k AND {col} = CAST(:i AS uuid)""", e=employee_id, k=kind, i=tid)
    return dict(inbox(employee_id), changed=int(n or 0))

"""알림 (#82, #96): 어떤 일이 생기면 누구에게 알릴지를 여기서 정한다.

| 일 | 받는 사람 |
| 로드맵 확정 | 부서장 (본인이 직접 누른 일이라 본인에게는 보내지 않음) |
| 결과 보고서 작성 끝남 | 본인·부서장 |
| 오래 걸리는 작업 끝남·실패(3안·다시 만들기·학습 자료·수정안, 보고서는 실패만) | 본인 |
| 부서장이 코멘트를 보냄 (고칠 때는 보내지 않음) | 그 직원 |
로드맵을 수정해도(수정안 확정) 부서장에게 알리지 않는다.

저장: app_ext.notifications. 받는 사람(recipient)·일으킨 사람(actor)·종류(roadmap|report|job|comment)·받는 쪽(self|head|member)·대상 id 만 두고,
화면 문구와 이동할 주소는 화면이 만든다(로드맵 제목이 바뀌어도 알림이 따라간다).
부서장 범위는 services/profile.members_of 와 같다: 같은 부서의 부서장만 그 부서 직원을 보고, 부서장 본인의 계획은 본인만 본다.
로드맵·보고서·코멘트 알림은 그것을 저장하는 트랜잭션(t) 안에서 넣는다. 저장이 실패하면 알림도 남지 않는다.
작업 알림(job_finished)은 작업 상태를 저장한 뒤 따로 넣는다. 알림을 못 넣어도 작업 결과는 그대로다.
"""
from __future__ import annotations

import uuid

from .. import db
from ..errors import ApiError, bad

LIMIT = 50

# h = 부서장(받는 사람), w = 작성한 직원. profile.members_of 와 같은 조건(부서장이 아닌 같은 부서 직원)
HEAD_SEES = 'h.is_department_head AND NOT w.is_department_head AND h.department_id = w.department_id'

_COLUMNS = 'INSERT INTO app_ext.notifications(recipient_id, actor_id, kind, audience, roadmap_id, report_id)'
_TO_SELF = """SELECT w.employee_id, w.employee_id, CAST(:k AS text), 'self', CAST(:r AS uuid), CAST(:rep AS uuid)
      FROM public.employees w WHERE w.employee_id = :e"""
_TO_HEAD = f"""SELECT h.employee_id, w.employee_id, CAST(:k AS text), 'head', CAST(:r AS uuid), CAST(:rep AS uuid)
      FROM public.employees w JOIN public.employees h ON {HEAD_SEES} WHERE w.employee_id = :e"""

# 부서장 알림은 그 직원이 지금도 소속일 때만 보인다(부서 이동 뒤 남은 알림으로 다른 부서 직원의 로드맵 제목이 보이지 않게).
# 부서장이 보낸 코멘트(member)는 받은 직원 본인의 로드맵 일이라 부서를 옮겨도 보인다
_VISIBLE = f"(n.audience IN ('self', 'member') OR ({HEAD_SEES}))"
_FROM = """FROM app_ext.notifications n
    JOIN public.employees w ON w.employee_id = n.actor_id
    JOIN public.employees h ON h.employee_id = n.recipient_id
    LEFT JOIN public.roadmaps r ON r.roadmap_id = n.roadmap_id
    LEFT JOIN public.projects p ON p.project_id = n.draft_id"""


def roadmap_created(t: db.Tx, employee_id: int, roadmap_id: str) -> None:
    """로드맵 확정(drafts.confirm)과 같은 트랜잭션에서 부른다. 부서장에게만 보낸다"""
    t.run(f'{_COLUMNS}\n    {_TO_HEAD}', e=employee_id, k='roadmap', r=roadmap_id, rep=None)


def report_created(t: db.Tx, employee_id: int, roadmap_id: str, report_id: str) -> None:
    """결과 보고서 저장(plans.report_start 작업)과 같은 트랜잭션에서 부른다.
    확인 전 보고서를 다시 만들면 이전 보고서가 지워지면서 그 알림도 함께 지워진다(report_id ON DELETE CASCADE).
    앞선 실패 알림은 보고서에 매이지 않아 함께 지워지지 않으므로, 다시 만들어 성공하면 읽지 않은 것을 여기서 지운다(PR #139 리뷰)"""
    t.run(f'{_COLUMNS}\n    {_TO_SELF}\n    UNION ALL\n    {_TO_HEAD}', e=employee_id, k='report', r=roadmap_id, rep=report_id)
    t.run("""DELETE FROM app_ext.notifications WHERE recipient_id = :e AND kind = 'job' AND job_kind = 'report'
             AND roadmap_id = CAST(:r AS uuid) AND read_at IS NULL""", e=employee_id, r=roadmap_id)


def draft_confirmed(t: db.Tx, employee_id: int, draft_id: str) -> None:
    """로드맵 확정(drafts.confirm)과 같은 트랜잭션에서 부른다. 확정한 문서의 3안·학습 자료 화면은 더 없으므로 그 알림은 읽음으로 바꾼다(PR #139 리뷰)"""
    t.run("""UPDATE app_ext.notifications SET read_at = now()
             WHERE recipient_id = :e AND kind = 'job' AND draft_id = CAST(:d AS uuid) AND read_at IS NULL""", e=employee_id, d=draft_id)


def comment_sent(t: db.Tx, head_id: int, member_id: int, roadmap_id: str, comment_id: str) -> None:
    """부서장의 새 코멘트(plans.send_comment)와 같은 트랜잭션에서 부른다. 고칠 때는 부르지 않는다"""
    t.run("""INSERT INTO app_ext.notifications(recipient_id, actor_id, kind, audience, roadmap_id, comment_id)
             VALUES(:m, :h, 'comment', 'member', CAST(:r AS uuid), CAST(:c AS uuid))""", m=member_id, h=head_id, r=roadmap_id, c=comment_id)


def _job_target(kind: str, ref: str | None, resume: dict | None) -> tuple[str, str | None, str | None] | None:
    """(알림 묶음, 작성 문서 id, 로드맵 id). 끝나도 알리지 않는 작업이면 None.
    학습 자료 작업은 다른 생성 작업과 kind·ref 형식이 같아 복구 정보(_resume)로 구분한다.
    서버 재시작으로 복구된 화면 요청은 ref 가 recovery:함수이름 이라 문서 id 도 복구 정보에서 읽는다(PR #139 리뷰)"""
    head = (ref or '').split(':', 1)[0]
    if kind in ('option', 'regenerate'):
        group = 'options' if kind == 'option' else 'regenerate'
    elif kind == 'learning_generation':
        spec = resume or {}
        if not (spec.get('operation') == 'materials' or (spec.get('operation') == 'route' and spec.get('function') == 'generate_recommendations')):
            return None
        group = 'materials'
        arguments = spec.get('kwargs') or {}
        head = str(arguments.get('draft_id') or arguments.get('project_id') or head)
    elif kind in ('revision', 'report'):
        group = kind
    else:
        return None
    try:
        target = str(uuid.UUID(head))
    except ValueError:
        return None
    return (group, None, target) if group in ('revision', 'report') else (group, target, None)


# 코스별 학습 자료 작업. 자동 준비(ref 문서:코스:키)와 화면에서 다시 받기(ref 문서, 복구되면 recovery:함수)는 ref 가 달라 복구 정보로 묶는다(PR #139 리뷰)
_MATERIAL_JOBS = """SELECT DISTINCT ON (course) status FROM (
    SELECT status, created_at, progress #>> '{_resume,kwargs,course}' AS course FROM app_ext.jobs
     WHERE employee_id = :e AND kind = 'learning_generation' AND progress #>> '{_resume,kwargs,course}' IS NOT NULL
       AND ((progress #>> '{_resume,operation}' = 'materials' AND progress #>> '{_resume,kwargs,draft_id}' = :d)
         OR (progress #>> '{_resume,operation}' = 'route' AND progress #>> '{_resume,function}' = 'generate_recommendations'
             AND progress #>> '{_resume,kwargs,project_id}' = :d))
  ) jobs ORDER BY course, created_at DESC"""


def _group_status(t: db.Tx, employee_id: int, kind: str, status: str, draft_id: str | None, resume: dict | None) -> str | None:
    """알릴 결과. 3안·학습 자료는 안·코스마다 작업이 나뉘므로 그 묶음이 모두 끝났을 때만 정한다(아직 도는 작업이 있으면 None).
    안·코스마다 가장 최근 작업만 본다. 예전 회차의 실패를 이번 결과로 치지 않고, 다시 받아 성공하면 그 코스의 실패를 대신한다"""
    if kind == 'learning_generation' and draft_id is not None and ((resume or {}).get('kwargs') or {}).get('course'):
        rows = t.all(_MATERIAL_JOBS, e=employee_id, d=draft_id)
    elif kind == 'option' and draft_id is not None:
        rows = t.all("""SELECT DISTINCT ON (split_part(ref, ':', 2)) status FROM app_ext.jobs
                        WHERE employee_id = :e AND kind = :k AND ref LIKE :p ORDER BY split_part(ref, ':', 2), created_at DESC""",
                     e=employee_id, k=kind, p=f'{draft_id}:%')
    else:  # 코스를 지정하지 않은 기본 자료 요청과 묶음이 없는 작업은 그 작업의 결과로 정한다
        return status
    states = {r['status'] for r in rows} | {status}
    if 'running' in states:
        return None
    return 'failed' if 'failed' in states else 'done'


def job_finished(kind: str, employee_id: int, ref: str | None, status: str, resume: dict | None = None) -> None:
    """작업 상태를 저장한 뒤(jobs.start) 부른다. 묶음의 작업들은 각자 자기 상태를 저장한 다음 여기서 남은 작업을 보므로,
    가장 늦게 끝난 작업은 항상 모두 끝난 상태를 본다. 동시에 끝나 둘 다 알리려 해도 잠금과 아래 지우기로 한 건만 남는다"""
    target = _job_target(kind, ref, resume)
    if target is None:
        return
    group, draft_id, roadmap_id = target
    if group == 'report' and status == 'done':  # 성공 알림은 보고서 저장과 함께 report_created 가 남겼다
        return
    with db.tx() as t:
        t.val('SELECT pg_advisory_xact_lock(hashtext(:k))', k=f'notification:{employee_id}:{group}:{draft_id or roadmap_id}')
        # 확정 뒤에 끝난 작업(남아 있던 자료 준비 등)은 볼 화면이 없다. 문서가 지워졌어도 알리지 않는다(PR #139 리뷰)
        if draft_id and t.val('SELECT status FROM public.projects WHERE project_id = CAST(:d AS uuid)', d=draft_id) != 'DRAFTING':
            return
        result = _group_status(t, employee_id, kind, status, draft_id, resume)
        if result is None:
            return
        # 같은 작업을 다시 돌렸을 때 읽지 않은 이전 결과 알림이 쌓이지 않게 새 결과로 바꾼다
        t.run("""DELETE FROM app_ext.notifications WHERE recipient_id = :e AND kind = 'job' AND job_kind = :g AND read_at IS NULL
                 AND draft_id IS NOT DISTINCT FROM CAST(:d AS uuid) AND roadmap_id IS NOT DISTINCT FROM CAST(:r AS uuid)""",
              e=employee_id, g=group, d=draft_id, r=roadmap_id)
        t.run("""INSERT INTO app_ext.notifications(recipient_id, actor_id, kind, audience, roadmap_id, draft_id, job_kind, job_status)
                 VALUES(:e, :e, 'job', 'self', CAST(:r AS uuid), CAST(:d AS uuid), :g, :s)""",
              e=employee_id, r=roadmap_id, d=draft_id, g=group, s=result)


def _item(n: dict) -> dict:
    return {'id': str(n['notification_id']), 'kind': n['kind'], 'audience': n['audience'],
            'employee': {'id': str(n['actor_id']), 'name': n['actor_name']},
            'planId': str(n['roadmap_id']) if n['roadmap_id'] else None, 'planTitle': n['plan_title'] or '', 'track': n['track'] or '',
            'reportId': str(n['report_id']) if n['report_id'] else None,
            'draftId': str(n['draft_id']) if n['draft_id'] else None, 'commentId': str(n['comment_id']) if n['comment_id'] else None,
            'jobKind': n['job_kind'], 'jobStatus': n['job_status'],
            'createdAt': n['created_at'].isoformat(), 'read': n['read_at'] is not None}


def inbox(employee_id: int, limit: int = LIMIT) -> dict:
    """내 읽지 않은 알림(최근 limit 건)과 읽지 않은 수. 읽지 않은 수는 목록 길이와 관계없이 전체를 센다.
    읽은 알림은 목록에서만 뺀다(#96). 기록은 지우지 않고 read_at 으로 남긴다"""
    rows = db.all_(f"""SELECT n.notification_id, n.kind, n.audience, n.actor_id, w.name AS actor_name, n.roadmap_id, n.report_id, n.draft_id, n.comment_id,
                              n.job_kind, n.job_status, n.created_at, n.read_at,
                              coalesce(nullif(r.content->>'displayTitle', ''), r.content->>'goal', p.draft_choices->'draft'->>'goal', p.project_name) AS plan_title,
                              r.content->>'opt' AS track
                       {_FROM} WHERE n.recipient_id = :e AND n.read_at IS NULL AND {_VISIBLE}
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

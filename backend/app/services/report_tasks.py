"""결과 보고서 과제 (#96): 부서장이 직원의 결과 보고서를 보고 과제를 내고, 직원이 글·파일로 결과를 제출한다.

저장: app_ext.report_tasks. 보고서를 다시 만들어도 과제가 남도록 로드맵에 묶는다(보고서 id 는 다시 만들 때마다 바뀐다).
소속 확인은 routers/team.py(부서장), 본인 확인은 여기서 plans._owned 로 한다.
첨부는 활동·사후 점검 첨부와 같은 곳(var/uploads)에 같은 크기 제한으로 둔다. 파일 id 는 서버가 만들고 내려받을 때도 DB 값만 쓴다.
"""
from __future__ import annotations

from pathlib import Path
import uuid

from .. import db
from ..config import S
from ..errors import ApiError, bad, not_found
from . import notifications as NT
from . import plans as PL

BODY_MAX = 2000
ANSWER_MAX = 4000
MAX_FILE = 15_000_000

_COLUMNS = """t.task_id, t.roadmap_id, t.head_id, h.name AS head_name, t.body, t.created_at, t.submitted_at, t.answer, t.attachment"""
_FROM = 'FROM app_ext.report_tasks t JOIN public.employees h ON h.employee_id = t.head_id'


def _view(r: dict) -> dict:
    file = r['attachment'] or None
    return {'id': str(r['task_id']), 'planId': str(r['roadmap_id']), 'body': r['body'], 'createdAt': PL._d(r['created_at']),
            'head': {'id': str(r['head_id']), 'name': r['head_name']}, 'submittedAt': PL._d(r['submitted_at']), 'answer': r['answer'] or '',
            'file': {'name': file['name'], 'size': file['size']} if file else None}


def _task_uuid(task_id: str) -> str:
    try:
        return str(uuid.UUID(str(task_id)))
    except ValueError:
        raise not_found('과제') from None


def of_plan(employee_id: int, roadmap_id: str) -> list[dict]:
    """그 직원의 로드맵에 있는 과제(먼저 낸 것부터). 부르는 쪽이 본인·소속을 확인한 뒤 부른다"""
    rows = db.all_(f'SELECT {_COLUMNS} {_FROM} WHERE t.roadmap_id = CAST(:r AS uuid) AND t.employee_id = :e ORDER BY t.created_at, t.task_id',
                   r=roadmap_id, e=employee_id)
    return [_view(r) for r in rows]


def mine(employee_id: int, roadmap_id: str) -> list[dict]:
    PL._owned(employee_id, roadmap_id)
    return of_plan(employee_id, roadmap_id)


def _report_of(member_id: int, roadmap_id: str) -> dict:
    report = next((x for x in PL.reports(member_id, for_mgr=True) if x['planId'] == roadmap_id), None)
    if not report:
        raise ApiError(409, 'NO_REPORT', '결과 보고서가 있는 로드맵에만 과제를 낼 수 있어요')
    return report


def send(head_id: int, member_id: int, roadmap_id: str, body: object) -> list[dict]:
    """부서장이 과제를 보낸다. 같은 트랜잭션에서 직원에게 알린다. 바뀐 과제 목록을 돌려준다"""
    text = str(body or '').strip()
    if not text:
        raise bad('과제 내용을 적어 주세요', 'TASK_EMPTY')
    if len(text) > BODY_MAX:
        raise bad(f'과제는 {BODY_MAX}자까지 쓸 수 있어요', 'TASK_TOO_LONG')
    _report_of(member_id, roadmap_id)
    with db.tx() as t:
        task_id = str(t.val("""INSERT INTO app_ext.report_tasks(roadmap_id, employee_id, head_id, body)
                               VALUES(CAST(:r AS uuid), :m, :h, :b) RETURNING task_id""", r=roadmap_id, m=member_id, h=head_id, b=text))
        NT.task_sent(t, head_id, member_id, roadmap_id, task_id)
    return of_plan(member_id, roadmap_id)


def submit(employee_id: int, roadmap_id: str, task_id: str, answer: object, name: str | None = None, raw: bytes | None = None) -> list[dict]:
    """직원이 결과를 제출한다(글·파일 중 하나는 있어야 한다). 한 번만 제출할 수 있고, 같은 트랜잭션에서 과제를 낸 부서장에게 알린다"""
    PL._owned(employee_id, roadmap_id)
    tid = _task_uuid(task_id)
    text = str(answer or '').strip()
    if len(text) > ANSWER_MAX:
        raise bad(f'제출 내용은 {ANSWER_MAX}자까지 쓸 수 있어요', 'ANSWER_TOO_LONG')
    if raw is not None and len(raw) > MAX_FILE:
        raise ApiError(413, 'FILE_TOO_BIG', '파일이 너무 커요(15MB까지)')
    has_file = bool(raw)
    if not text and not has_file:
        raise bad('제출할 내용이나 파일을 넣어 주세요', 'SUBMISSION_EMPTY')
    with db.tx() as t:
        row = t.one("""SELECT head_id, submitted_at FROM app_ext.report_tasks
                       WHERE task_id = CAST(:t AS uuid) AND roadmap_id = CAST(:r AS uuid) AND employee_id = :e FOR UPDATE""", t=tid, r=roadmap_id, e=employee_id)
        if not row:
            raise not_found('과제')
        if row['submitted_at']:
            raise ApiError(409, 'ALREADY_SUBMITTED', '이미 제출한 과제예요')
        attachment = None
        if has_file:
            file_id = uuid.uuid4().hex
            folder = S.var_dir / 'uploads'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / file_id).write_bytes(raw)
            attachment = {'fileId': file_id, 'name': name or 'file', 'size': len(raw)}
        t.run("""UPDATE app_ext.report_tasks SET submitted_at = now(), answer = :a, attachment = :f WHERE task_id = CAST(:t AS uuid)""",
              a=text or None, f=db.J(attachment) if attachment else None, t=tid)
        NT.task_submitted(t, employee_id, row['head_id'], roadmap_id, tid)
    return of_plan(employee_id, roadmap_id)


def attachment_of(employee_id: int, roadmap_id: str, task_id: str) -> tuple[Path, str]:
    """제출 파일의 위치와 원래 이름. 부르는 쪽이 본인·소속을 확인한 뒤 부른다"""
    row = db.one("""SELECT attachment FROM app_ext.report_tasks WHERE task_id = CAST(:t AS uuid) AND roadmap_id = CAST(:r AS uuid) AND employee_id = :e""",
                 t=_task_uuid(task_id), r=roadmap_id, e=employee_id)
    file = (row or {}).get('attachment')
    path = S.var_dir / 'uploads' / file['fileId'] if file else None
    if not path or not path.is_file():
        raise not_found('제출 파일')
    return path, file['name']

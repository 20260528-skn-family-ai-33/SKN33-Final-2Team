"""관리자 화면 API (관리자 전용 계정 · 2026-10-21 사용자 결정): 인적·교육 데이터 엑셀·CSV 관리, 규정 원문 PDF 올리기·내려받기, 목표 후보 일괄 다시 만들기.

관리자는 직원 기록(로드맵·점검·보고서)을 보지 않는다. 인적·교육 데이터 변경은 미리보기 → 반영 두 단계로만 한다.
규정은 벡터 DB 를 거친 RAG 에 쓰여서 관리자가 고치지 않는다(2026-10-26 사용자 결정): 원문 PDF 를 올리면 시스템 관리자(서비스 운영팀)가 내려받아 임베딩한다.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from .. import admin_io, db, llm, regfiles
from ..auth import Account, require_admin
from ..errors import ApiError, provider_label, unavailable_reason

r = APIRouter(prefix='/api/v1/admin')
MAX_FILE = 20_000_000


@r.get('/overview')
def api_overview(a: Account = Depends(require_admin)):
    hr = db.one("""SELECT count(*) FILTER (WHERE coalesce(h.employment_status, '재직') <> '퇴직') AS active, count(*) FILTER (WHERE h.employment_status = '퇴직') AS retired,
            count(*) FILTER (WHERE e.is_department_head) AS heads, count(*) FILTER (WHERE e.employee_number IS NULL) AS no_number
        FROM public.employees e LEFT JOIN app_ext.employee_hr h ON h.employee_id = e.employee_id""")
    depts = db.val('SELECT count(*) FROM public.departments')
    evals = db.val('SELECT count(*) FROM app_ext.employee_evaluations')
    transfers = db.all_("""SELECT t.changed_at, e.name, t.from_department_name, t.to_department_name, t.head_before, t.head_after FROM app_ext.employee_transfers t
                           JOIN public.employees e ON e.employee_id = t.employee_id ORDER BY t.changed_at DESC LIMIT 5""")
    goals = {x['status']: x['n'] for x in db.all_('SELECT status, count(*) AS n FROM app_ext.goal_suggestion_runs GROUP BY status')}
    edu =db.all_("""SELECT m.resource_type AS t, count(*) AS n, count(*) FILTER (WHERE jsonb_array_length(m.estimated_fields) > 0) AS est FROM app_ext.resource_meta m GROUP BY 1""")
    return {
        'hr': {'active': hr['active'], 'retired': hr['retired'], 'heads': hr['heads'], 'noNumber': hr['no_number'], 'departments': depts, 'evaluations': evals,
               'transfers': [{'at': x['changed_at'].strftime('%Y-%m-%d %H:%M'), 'name': x['name'], 'from': x['from_department_name'], 'to': x['to_department_name'],
                              'headBefore': x['head_before'], 'headAfter': x['head_after']} for x in transfers]},
        'regulations': regfiles.overview(),
        'providers': {p: {'available': llm.available(p)} for p in ('ollama', 'openai')},
        'education':{x['t']: {'count': x['n'], 'estimated': x['est']} for x in edu},
        'goals': goals,
        'uploads': admin_io.history('', 8),
    }


@r.get('/datasets/{ds}/rows')
def api_rows(ds: str, sheet: str, q: str = '', limit: int = 50, offset: int = 0, a: Account = Depends(require_admin)):
    return admin_io.rows(ds, sheet, q, max(1, min(200, limit)), max(0, offset))


def _file(data: bytes, name: str, mime: str) -> Response:
    # 한글 파일 이름(RFC 5987)
    return Response(data, media_type=mime, headers={'Content-Disposition': f"attachment; filename=\"growpath.{name.rsplit('.', 1)[-1]}\"; filename*=UTF-8''{quote(name)}",
                                                   'Cache-Control': 'no-store'})


@r.get('/datasets/{ds}/export')
def api_export(ds: str, format: str = 'xlsx', sheet: str = '', a: Account = Depends(require_admin)):
    return _file(*admin_io.export(ds, 'csv' if format == 'csv' else 'xlsx', sheet))


@r.get('/datasets/{ds}/template')
def api_template(ds: str, format: str = 'xlsx', sheet: str = '', a: Account = Depends(require_admin)):
    return _file(*admin_io.export(ds, 'csv' if format == 'csv' else 'xlsx', sheet, empty=True))


@r.post('/datasets/{ds}/preview')
async def api_preview(ds: str, file: UploadFile = File(...), sheet: str = Form(''), a: Account = Depends(require_admin)):
    raw = await file.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise ApiError(413, 'FILE_TOO_BIG', '파일이 너무 커요(20MB까지)', '고칠 행만 남긴 파일로 나눠 올려 주세요')
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(admin_io.preview, ds, a.id, file.filename or 'upload.xlsx', raw, sheet or None)


@r.post('/datasets/{ds}/edit')
def api_edit(ds: str, body: dict, a: Account = Depends(require_admin)):
    """화면에서 한 건씩 추가·수정·삭제. save 가 false 면 확인만(바뀌는 칸과 token), true 면 확인 때 받은 token 으로 저장.
    goalMode 'mock' 은 시연용 가데이터, 아니면 그 직원이 고른 AI 모드로 목표 후보를 다시 만든다(인적 데이터)"""
    return admin_io.edit(ds, a.id, body.get('rows'), bool(body.get('save')), body.get('token'), 'mock' if body.get('goalMode') == 'mock' else None)


@r.get('/uploads/{upload_id}')
def api_upload(upload_id: str, a: Account = Depends(require_admin)):
    return admin_io.one(upload_id)


@r.post('/uploads/{upload_id}/apply')
def api_apply(upload_id: str, body: dict | None = None, a: Account = Depends(require_admin)):
    mode = (body or {}).get('goalMode')
    return admin_io.apply(upload_id, a.id, 'mock' if mode == 'mock' else None)


@r.delete('/uploads/{upload_id}', status_code=204)
def api_discard(upload_id: str, a: Account = Depends(require_admin)):
    admin_io.discard(upload_id)


@r.get('/uploads')
def api_uploads(dataset: str = '', a: Account = Depends(require_admin)):
    return admin_io.history(dataset, 50)


_ACTIVE_SQL = """SELECT e.employee_id, e.name, e.employee_number, coalesce(d.name, e.department) AS dept, e.grade,
                         g.status AS goal_status, g.source AS goal_source, g.finished_at
                  FROM public.employees e LEFT JOIN app_ext.employee_hr h ON h.employee_id = e.employee_id
                  LEFT JOIN public.departments d ON d.department_id = e.department_id
                  LEFT JOIN app_ext.goal_suggestion_runs g ON g.employee_id = e.employee_id
                  WHERE coalesce(h.employment_status, '재직') <> '퇴직' ORDER BY e.employee_id"""


@r.get('/goal-suggestions/employees')
def api_goal_employees(a: Account = Depends(require_admin)):
    """목표 후보를 다시 만들 직원 고르기용: 재직 직원과 지금 후보 상태(준비됨·기본·만드는 중·실패 · 만든 모드)"""
    return [{'id': x['employee_id'], 'name': x['name'], 'no': x['employee_number'] or '', 'dept': x['dept'] or '', 'grade': x['grade'] or '',
             'status': x['goal_status'] or '', 'source': x['goal_source'] or '',
             'at': x['finished_at'].strftime('%Y-%m-%d %H:%M') if x['finished_at'] else ''} for x in db.all_(_ACTIVE_SQL)]


@r.post('/goal-suggestions/regenerate-all')
def api_goals_all(body: dict | None = None, a: Account = Depends(require_admin)):
    """재직 직원의 목표 후보를 다시 만든다. employeeIds 가 있으면 그 직원만(재직 중인 직원만 받음), 없으면 모두.
    mode: 'mock' 시연용 가데이터 · 'ollama'·'openai' 관리자가 고른 모델(직원 설정은 그대로) · 없으면 각 직원이 고른 AI 모드(설정 안 됐으면 실패로 남음)"""
    from ..services import goals
    b = body or {}
    mode = b.get('mode') if b.get('mode') in ('mock', 'ollama', 'openai') else None
    if mode in ('ollama', 'openai') and not llm.available(mode):
        raise ApiError(409, 'AI_UNAVAILABLE', f'{provider_label(mode)}를 지금 쓸 수 없어요', unavailable_reason(mode) or '.env 설정을 확인해 주세요', kind='config')
    ids = [x['employee_id'] for x in db.all_(_ACTIVE_SQL)]
    pick = b.get('employeeIds')
    if pick is not None:
        if not isinstance(pick, list):
            raise ApiError(400, 'BAD_EMPLOYEES', 'employeeIds 는 직원 번호 목록이어야 해요')
        want = {int(x) for x in pick if str(x).isdigit()}
        ids = [i for i in ids if i in want]
        if not ids:
            raise ApiError(400, 'NO_EMPLOYEES', '고른 직원 중 재직 중인 직원이 없어요', '목록에서 직원을 다시 골라 주세요')
    started, saved = 0, 0
    for eid in ids:
        if goals.request(eid, 'admin-pick' if pick is not None else 'admin-all', mode=mode):
            started += 1
        else:
            saved += 1
    return {'employees': len(ids), 'started': started, 'defaults': saved, 'mode': mode or 'employee'}


# ── 규정 원문 PDF: 지금 규정 내려받기 · 새 규정 PDF 올리기 (규정 내용은 고치지 않음) ──
@r.get('/regulations')
def api_regulations(a: Account = Depends(require_admin)):
    """지금 규정(도우미가 쓰는 버전)과 원문 PDF 가 서버에 있는지"""
    return regfiles.current()


@r.get('/regulations/uploads')
def api_regulation_uploads(a: Account = Depends(require_admin)):
    return regfiles.uploads()


@r.post('/regulations/uploads', status_code=201)
async def api_regulation_upload(file: UploadFile = File(...), memo: str = Form(''), a: Account = Depends(require_admin)):
    raw = await file.read(regfiles.UPLOAD_MAX + 1)
    if len(raw) > regfiles.UPLOAD_MAX:
        raise ApiError(413, 'FILE_TOO_BIG', '파일이 너무 커요(20MB까지)', 'PDF 용량을 줄이거나 나눠서 올려 주세요')
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(regfiles.save_upload, a.id, file.filename or 'upload.pdf', raw, memo)


@r.delete('/regulations/uploads/{upload_id}', status_code=204)
def api_regulation_upload_delete(upload_id: str, a: Account = Depends(require_admin)):
    """잘못 올린 PDF 지우기(파일과 기록을 함께 · 되돌리지 않음)"""
    regfiles.delete_upload(upload_id)


@r.get('/regulations/uploads/{upload_id}/pdf')
def api_regulation_upload_pdf(upload_id: str, a: Account = Depends(require_admin)):
    data, name = regfiles.upload_pdf(upload_id)
    return _file(data, name, 'application/pdf')


@r.get('/regulations/{regulation_id}/pdf')
def api_regulation_pdf(regulation_id: str, a: Account = Depends(require_admin)):
    data, name = regfiles.current_pdf(regulation_id)
    return _file(data, name, 'application/pdf')

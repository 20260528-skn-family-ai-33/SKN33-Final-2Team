"""관리자 화면 API (관리자 전용 계정 · 2026-10-21 사용자 결정): 인적·교육 데이터 엑셀·CSV 관리, 규정 원문 PDF 올리기·내려받기, 목표 후보 일괄 다시 만들기.

관리자는 직원 기록(로드맵·점검·보고서)을 보지 않는다. 인적·교육 데이터 변경은 미리보기 → 반영 두 단계로만 한다.
규정은 벡터 DB 를 거친 RAG 에 쓰여서 관리자가 고치지 않는다(2026-10-26 사용자 결정): 원문 PDF 를 올리면 시스템 관리자(서비스 운영팀)가 내려받아 임베딩한다.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from .. import admin_io, browser_console, db, llm, provider_keys, provider_policy, regfiles
from ..config import S
from ..auth import Account, require_admin
from ..errors import ApiError, cause, provider_label, unavailable_reason
from . import validated_uuid

r = APIRouter(prefix='/api/v1/admin')
MAX_FILE = 20_000_000


@r.get('/ai-provider')
def api_provider_policy(a: Account = Depends(require_admin)):
    providers = {}
    connection = provider_keys.runpod(S)
    for p in ('openai', 'ollama'):
        credential = provider_keys.read(S, p) if p == 'openai' else connection.key
        providers[p] = {'available': bool(credential.value) if p == 'openai' else bool(connection.url),
                        'model': llm.model_name(p), 'keyConfigured': bool(credential.value),
                        'keySource': credential.source, 'hasDefaultKey': bool(S.openai_key if p == 'openai' else S.ollama_key)}
    policy, level, status = provider_policy.admin_selection()
    providers['openai']['levels'] = list(S.openai_reasoning_levels)
    # 기존 환경 주소에는 사용자 정보나 쿼리가 있을 수 있어 관리 화면에 그대로 노출하지 않는다.
    try:
        public_url = browser_console.runpod_url(connection.url)
    except ValueError:
        public_url = ''
    return {'policy': policy, 'level': level, 'employeeSelectionAllowed': S.employee_ai_selection,
            'policyStatus': status, 'providers': providers, 'runpod': {'url': public_url, 'managed': connection.managed}}


@r.put('/ai-provider')
def api_save_provider(body: dict, a: Account = Depends(require_admin)):
    if 'policy' not in body or set(body) - {'policy', 'level'}:
        raise ApiError(422, 'BAD_PROVIDER', '제공자와 추론 정도를 확인해 주세요')
    level = body.get('level')
    if 'level' not in body:
        current, previous_level, _ = provider_policy.admin_selection()
        level = previous_level if current == body['policy'] else None
    provider_policy.save(body['policy'], level)
    return api_provider_policy(a)


async def _runpod_candidate(request: Request, *, allow_current: bool = False) -> provider_keys.RunpodConnection:
    # 요청 본문의 키가 입력 오류 응답에 포함되지 않도록 직접 검사한다.
    try:
        data = await request.json()
    except ValueError:
        data = None
    if allow_current and data == {}:
        return provider_keys.runpod(S)
    if not isinstance(data, dict) or set(data) != {'url', 'key'} or not isinstance(data['url'], str):
        raise ApiError(422, 'BAD_RUNPOD', 'RunPod 주소와 키를 확인해 주세요')
    try:
        url = browser_console.runpod_url(data['url'].strip())
    except ValueError as exc:
        raise ApiError(422, 'BAD_RUNPOD_URL', str(exc)) from exc
    key = data['key']
    if not isinstance(key, str) or len(key) > 4096 or (key and not (key.isascii() and key.isprintable() and ' ' not in key)):
        raise ApiError(422, 'BAD_PROVIDER_KEY', '키는 공백 없는 ASCII 문자로 입력해 주세요')
    return provider_keys.RunpodConnection(url, provider_keys.Credential(key, 'admin' if key else 'none'), 'runpod', True)


def _check_runpod(connection: provider_keys.RunpodConnection) -> dict:
    if not connection.url:
        raise ApiError(409, 'AI_UNAVAILABLE', '공용 RunPod 주소가 설정되지 않았어요')
    try:
        status = llm.ping('ollama', connection=connection)
    except llm.LlmError as exc:
        info = cause(str(exc), 'ollama')
        raise ApiError(502, info['code'], info['user']) from exc
    missing = [m['name'] for m in status['models'] if not m['installed']]
    if missing:
        raise ApiError(409, 'RUNPOD_MODEL_MISSING', '설치가 필요한 모델 · ' + ', '.join(missing))
    return status


@r.post('/ai-provider/ollama/connection/check')
async def api_check_runpod(request: Request, a: Account = Depends(require_admin)):
    candidate = await _runpod_candidate(request, allow_current=True)
    return await run_in_threadpool(_check_runpod, candidate)


@r.put('/ai-provider/ollama/connection')
async def api_save_runpod(request: Request, a: Account = Depends(require_admin)):
    candidate = await _runpod_candidate(request)
    await run_in_threadpool(_check_runpod, candidate)
    provider_keys.save_runpod(S, candidate)
    return api_provider_policy(a)


@r.delete('/ai-provider/ollama/connection')
def api_reset_runpod(a: Account = Depends(require_admin)):
    provider_keys.reset_runpod(S)
    return api_provider_policy(a)


@r.put('/ai-provider/{provider}/key')
async def api_save_provider_key(provider: provider_keys.Provider, request: Request, a: Account = Depends(require_admin)):
    # 검증 오류 응답에 요청 본문이나 입력한 키가 포함되지 않도록 직접 검사한다.
    try:
        body = await request.json()
    except ValueError:
        body = None
    value = body.get('key') if isinstance(body, dict) and set(body) == {'key'} else None
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or not value.isascii() or not value.isprintable() or ' ' in value:
        raise ApiError(422, 'BAD_PROVIDER_KEY', '공백 없이 올바른 API 키를 입력해 주세요')
    if provider == 'ollama' and provider_keys.runpod(S).managed:
        raise ApiError(409, 'RUNPOD_MANAGED', '공용 RunPod 연결 설정에서 주소와 키를 함께 변경해 주세요')
    provider_keys.save(S, provider, value)
    return api_provider_policy(a)


@r.delete('/ai-provider/{provider}/key')
def api_reset_provider_key(provider: provider_keys.Provider, a: Account = Depends(require_admin)):
    if provider == 'ollama' and provider_keys.runpod(S).managed:
        raise ApiError(409, 'RUNPOD_MANAGED', '공용 RunPod 연결 설정에서 기본 연결을 복원해 주세요')
    provider_keys.reset(S, provider)
    return api_provider_policy(a)


@r.get('/overview')
def api_overview(a: Account = Depends(require_admin)):
    hr = db.one("""SELECT count(*) FILTER (WHERE coalesce(h.employment_status, '재직') <> '퇴직') AS active, count(*) FILTER (WHERE h.employment_status = '퇴직') AS retired,
            count(*) FILTER (WHERE e.is_department_head) AS heads, count(*) FILTER (WHERE e.employee_number IS NULL) AS no_number
        FROM public.employees e LEFT JOIN app_ext.employee_hr h ON h.employee_id = e.employee_id""")
    depts = db.val('SELECT count(*) FROM public.departments')
    transfers = db.all_("""SELECT t.changed_at, e.name, t.from_department_name, t.to_department_name, t.head_before, t.head_after FROM app_ext.employee_transfers t
                           JOIN public.employees e ON e.employee_id = t.employee_id ORDER BY t.changed_at DESC LIMIT 5""")
    goals = {x['status']: x['n'] for x in db.all_('SELECT status, count(*) AS n FROM app_ext.goal_suggestion_runs GROUP BY status')}
    edu =db.all_("""SELECT m.resource_type AS t, count(*) AS n, count(*) FILTER (WHERE jsonb_array_length(m.estimated_fields) > 0) AS est FROM app_ext.resource_meta m GROUP BY 1""")
    return {
        'hr': {'active': hr['active'], 'retired': hr['retired'], 'heads': hr['heads'], 'noNumber': hr['no_number'], 'departments': depts,
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
    upload_id = validated_uuid(upload_id, ApiError(404, 'NO_UPLOAD', '미리보기 기록을 찾을 수 없어요'))
    return admin_io.one(upload_id)


@r.post('/uploads/{upload_id}/apply')
def api_apply(upload_id: str, body: dict | None = None, a: Account = Depends(require_admin)):
    mode = (body or {}).get('goalMode')
    return admin_io.apply(upload_id, a.id, 'mock' if mode == 'mock' else None)


@r.delete('/uploads/{upload_id}', status_code=204)
def api_discard(upload_id: str, a: Account = Depends(require_admin)):
    upload_id = validated_uuid(upload_id, ApiError(404, 'NO_UPLOAD', '미리보기 기록을 찾을 수 없어요'))
    admin_io.discard(upload_id)


@r.get('/uploads')
def api_uploads(dataset: str = '', a: Account = Depends(require_admin)):
    return admin_io.history(dataset, 50)


_ACTIVE_SQL = """SELECT e.employee_id, e.name, e.employee_number, coalesce(d.name, e.department) AS dept, e.grade,
                         g.status AS goal_status, g.source AS goal_source, g.finished_at,
                         s.ai_provider, s.reasoning, s.demo_mock
                  FROM public.employees e LEFT JOIN app_ext.employee_hr h ON h.employee_id = e.employee_id
                  LEFT JOIN public.departments d ON d.department_id = e.department_id
                  LEFT JOIN app_ext.goal_suggestion_runs g ON g.employee_id = e.employee_id
                  LEFT JOIN app_ext.user_settings s ON s.employee_id = e.employee_id
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
    goals.validate_mode(mode)
    policy, level = provider_policy.selection()
    if (('expectedPolicy' in b and b['expectedPolicy'] != policy)
            or ('expectedLevel' in b and b['expectedLevel'] != level)):
        raise ApiError(409, 'PROVIDER_MANAGED', '모델 설정이 바뀌었어요. 현재 설정을 확인한 뒤 다시 시도해 주세요')
    if policy != 'employee':
        if mode and mode != policy:
            raise ApiError(409, 'PROVIDER_MANAGED', '현재 관리자 설정을 확인한 뒤 다시 시도해 주세요')
        mode = policy
    if mode in ('ollama', 'openai') and not llm.available(mode):
        raise ApiError(409, 'AI_UNAVAILABLE', f'{provider_label(mode)}를 지금 쓸 수 없어요', unavailable_reason(mode) or '.env 설정을 확인해 주세요', kind='config')
    employees = db.all_(_ACTIVE_SQL)
    pick = b.get('employeeIds')
    if pick is not None:
        if not isinstance(pick, list):
            raise ApiError(400, 'BAD_EMPLOYEES', 'employeeIds 는 직원 번호 목록이어야 해요')
        want = {int(x) for x in pick if str(x).isdigit()}
        employees = [row for row in employees if row['employee_id'] in want]
        if not employees:
            raise ApiError(400, 'NO_EMPLOYEES', '고른 직원 중 재직 중인 직원이 없어요', '목록에서 직원을 다시 골라 주세요')
    started, saved = 0, 0
    trigger = 'admin-pick' if pick is not None else 'admin-all'
    for row in employees:
        approved = goals.bulk_model(row, mode, level)
        if goals.request(row['employee_id'], trigger, mode=mode, approved_model=approved):
            started += 1
        else:
            saved += 1
    return {'employees': len(employees), 'started': started, 'defaults': saved, 'mode': mode or 'employee'}


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

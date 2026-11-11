"""인증·내 정보·AI 모델·시연 도구 (API-01~08, 10~13)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from .. import db, llm, provider_policy, regulation_embeddings
from ..agents import runtime as rt
from ..auth import COOKIE, Account, end_session, hash_password, login, require_account, require_employee, start_session, verify_password
from ..config import S, level_ok
from ..errors import ApiError, provider_label, unavailable_reason
from ..services import demo, goals, profile
from . import job_response

r = APIRouter(prefix='/api/v1')


def _settings(employee_id: int, selection: tuple[str, str | None] | None = None) -> dict:
    policy, level = selection or provider_policy.selection()
    s = db.one('SELECT ai_provider, demo_mock, fail_sim, reasoning FROM app_ext.user_settings WHERE employee_id = :e', e=employee_id) or {}
    # 시연을 끈 배포에서는 DB에 남아 있는 시연 옵션도 화면에 적용하지 않는다.
    return {'aiProvider': provider_policy.resolve(policy, s.get('ai_provider')), 'demoMock': S.demo_mode and bool(s.get('demo_mock')),
            'failSim': (s.get('fail_sim') or {}) if S.demo_mode else {},
            'reasoning': (s.get('reasoning') or {}) if policy == 'employee' else ({policy: level} if level else {})}


def _me(a: Account) -> dict:
    if a.type == 'admin':
        return {'accountType': 'admin', 'admin': {'id': a.id, 'name': a.name}}
    v = profile.view(a.id)
    return {'accountType': 'employee', 'user': v, **_settings(a.id)}


@r.post('/auth/login')
def api_login(body: dict, response: Response):
    a = login(str(body.get('employeeNo') or ''), str(body.get('password') or ''))
    start_session(response, a.type, a.id, bool(body.get('keepSignedIn')))
    return _me(a)


@r.post('/auth/logout', status_code=204)
def api_logout(request: Request):
    resp = Response(status_code=204)
    end_session(request, resp)
    return resp


def require_demo_mode() -> None:
    if not S.demo_mode:
        raise ApiError(404, 'NOT_FOUND', '요청한 기능을 찾을 수 없어요')


def require_beta_account_picker() -> None:
    if not S.beta_account_picker:
        raise ApiError(404, 'NOT_FOUND', '요청한 기능을 찾을 수 없어요')


@r.get('/demo/accounts', dependencies=[Depends(require_beta_account_picker)])
def api_accounts():
    """베타 로그인 화면의 '직원 고르기'. 시연 도구와 독립적으로 켜며 비밀번호는 보내지 않는다."""
    return {'accounts': profile.accounts(), 'adminLogin': S.admin_login}


@r.get('/me')
def api_me(a: Account = Depends(require_account)):
    return _me(a)


@r.get('/me/profile')
def api_profile(a: Account = Depends(require_employee)):
    v = profile.view(a.id)
    return dict(profile.spec(v), view=v)


@r.put('/me/password', status_code=204)
def api_change_password(body: dict, a: Account = Depends(require_employee)):
    current, new = body.get('currentPassword'), body.get('newPassword')
    if not isinstance(current, str) or not 1 <= len(current) <= 1024:
        raise ApiError(422, 'PASSWORD_INVALID', '현재 비밀번호를 확인해 주세요.')
    if not isinstance(new, str) or not 4 <= len(new) <= 128:
        raise ApiError(422, 'PASSWORD_INVALID', '새 비밀번호는 4~128자로 입력해 주세요.')
    if new == current:
        raise ApiError(422, 'PASSWORD_INVALID', '현재 비밀번호와 다른 새 비밀번호를 입력해 주세요.')
    row = db.one('SELECT password_hash FROM public.employees WHERE employee_id = :e', e=a.id)
    stored = (row or {}).get('password_hash')
    if not verify_password(stored, current):
        raise ApiError(400, 'PASSWORD_INCORRECT', '현재 비밀번호가 맞지 않아요.')
    replacement = hash_password(new)
    with db.tx() as t:
        if not t.run('UPDATE public.employees SET password_hash = :new WHERE employee_id = :e AND password_hash = :old',
                     e=a.id, old=stored, new=replacement):
            raise ApiError(409, 'PASSWORD_CHANGED', '비밀번호가 이미 변경됐어요. 현재 비밀번호를 다시 확인해 주세요.')
        t.run("DELETE FROM app_ext.sessions WHERE account_type = 'employee' AND account_id = :e", e=a.id)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path='/')
    return response


@r.put('/me/profile/self')
def api_self(body: dict, a: Account = Depends(require_employee)):
    profile.save_self(a.id, body)
    goals.request(a.id, 'self-input', only_if_stale=True)
    v = profile.view(a.id)
    return dict(profile.spec(v), view=v)


@r.delete('/me/profile/self')
def api_self_revert(a: Account = Depends(require_employee)):
    profile.revert_self(a.id)
    goals.request(a.id, 'self-input-revert', only_if_stale=True)
    v = profile.view(a.id)
    return dict(profile.spec(v), view=v)


@r.get('/me/goal-suggestions')
def api_goals(a: Account = Depends(require_employee)):
    return goals.get(a.id)


@r.post('/me/goal-suggestions/regenerate')
def api_goals_regen(request: Request, a: Account = Depends(require_employee)):
    jid = goals.regenerate(a.id)
    if not jid:
        return goals.get(a.id)
    return JSONResponse({'jobId': jid, 'status': 'running'}, status_code=202)


@r.post('/me/goal-suggestions/ensure')
def api_goals_ensure(a: Account = Depends(require_employee)):
    state = goals.get(a.id)
    # 정보 변경은 저장 성공 뒤 갱신한다. 목표 화면은 신규/미준비 계정만 보완한다.
    if state['status'] == 'none':
        goals.request(a.id, 'goal-missing', only_if_stale=True)
        return goals.get(a.id)
    return state


# ── AI 모델 (API-10~12) ──
@r.get('/ai/providers')
def api_providers(a: Account = Depends(require_account)):
    policy, level = provider_policy.selection()
    settings = _settings(a.id, (policy, level)) if a.type == 'employee' else {}
    return {'current': settings.get('aiProvider') or provider_policy.resolve(policy, None),
            'policy': policy, 'employeeReasoning': settings.get('reasoning', {}), 'demoMode': S.demo_mode, 'providers': [
        {'id': 'ollama', 'label': 'RunPod-Ollama', 'available': llm.available('ollama'), 'reason': unavailable_reason('ollama'), 'target': S.ollama_target if S.ollama_url else '',
         'models': dict({r: llm.model_name('ollama', r) for r in ('default', 'roadmap', 'regulation', 'vision')}, embed=regulation_embeddings.model()),
         'timeout': S.ollama_timeout,
         # 추론 정도(진단·로드맵 모델 · 규정 모델은 늘 끔): default 는 .env 기본값(비면 null = 모델 기본값).
         # Ollama 단계는 모델마다 달라 연결 확인(/ai/status)의 진단·로드맵 모델 models[].think 로 준다
         'reasoning': {'levels': None, 'default': S.ollama_think}},
        {'id': 'openai', 'label': 'OpenAI API', 'available': llm.available('openai'), 'reason': unavailable_reason('openai'),
         'models': {'default': S.openai_model, 'roadmap': S.openai_model, 'regulation': S.openai_model, 'embed': regulation_embeddings.model(), 'vision': S.openai_vision},
         # modelDefault: 보내지 않을 때 모델이 쓰는 값(기본 모델 gpt-6-luna 만 코드에 있음 · 화면 '기본값 · 보통' 표시용)
         'reasoning': {'levels': list(S.openai_reasoning_levels), 'default': S.openai_reasoning, 'modelDefault': S.openai_model_reasoning}}],
        'docLibs': {'pdf': _has('pypdf'), 'hwp': _has('olefile')}}


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


@r.put('/me/ai-provider')
def api_set_provider(body: dict, a: Account = Depends(require_employee)):
    provider_policy.require_employee_selection()
    p = body.get('provider')
    if p not in ('ollama', 'openai'):
        raise ApiError(400, 'BAD_PROVIDER', 'RunPod-Ollama 또는 OpenAI API 중에서 골라 주세요')
    with db.tx() as t:
        t.run("""INSERT INTO app_ext.user_settings(employee_id, ai_provider) VALUES(:e, :p)
                 ON CONFLICT (employee_id) DO UPDATE SET ai_provider = EXCLUDED.ai_provider, updated_at = now()""", e=a.id, p=p)
    return {'provider': p}


@r.put('/me/reasoning')
def api_set_reasoning(body: dict, a: Account = Depends(require_employee)):
    """모드별 추론 정도. level 이 null 이면 .env 기본값을 따른다. RunPod-Ollama 는 진단·로드맵 모델에만 쓰고
    규정 에이전트 모델은 늘 끈다(생각을 끄고 학습 · 고를 수 없음). OpenAI 는 .env 의 OPENAI_REASONING_LEVELS 안에서만 받는다.
    RunPod-Ollama 단계는 모델마다 달라 이름 모양만 본다(모델이 모르는 이름이면 Ollama 가 모델 기본값을 쓴다)"""
    provider_policy.require_employee_selection()
    p, level = body.get('provider'), body.get('level')
    if p not in ('ollama', 'openai'):
        raise ApiError(400, 'BAD_PROVIDER', 'RunPod-Ollama 또는 OpenAI API 중에서 골라 주세요')
    if 'level' not in body or not (level is None or (isinstance(level, str) and level_ok(level))):
        raise ApiError(422, 'BAD_REASONING', '추론 정도는 단계 이름 또는 null(서버 기본값)로 보내 주세요')
    if p == 'openai' and level is not None and level not in S.openai_reasoning_levels:
        raise ApiError(422, 'BAD_REASONING', 'OpenAI 모델이 받는 추론 정도가 아니에요', '.env 의 OPENAI_REASONING_LEVELS 에 있는 단계만 고를 수 있어요')
    # 그 모드의 키만 한 문장으로 바꾼다: 읽고 고쳐 통째로 쓰면 두 모드를 동시에 저장할 때 한쪽이 사라진다(PR #40 리뷰)
    mine = {} if level is None else {p: level}
    with db.tx() as t:
        row = t.one("""INSERT INTO app_ext.user_settings(employee_id, reasoning) VALUES(:e, :m)
                       ON CONFLICT (employee_id) DO UPDATE
                         SET reasoning = (app_ext.user_settings.reasoning - CAST(:p AS text)) || EXCLUDED.reasoning, updated_at = now()
                       RETURNING reasoning""", e=a.id, p=p, m=db.J(mine))
    return {'reasoning': row['reasoning'] or {}}


@r.get('/ai/status')
def api_status(provider: str = 'ollama', a: Account = Depends(require_account)):
    """연결 확인(API-12 · 토큰을 쓰지 않음). 화면은 쉬운 말만, 원인·조치·원문은 운영자용"""
    if provider not in ('ollama', 'openai'):
        raise ApiError(400, 'BAD_PROVIDER', '사용할 AI 제공자를 선택해 주세요')
    if a.type == 'employee' and provider_policy.current() not in ('employee', provider):
        raise ApiError(409, 'PROVIDER_MANAGED', '관리자가 지정한 모델의 연결만 확인할 수 있어요')
    try:
        return llm.ping(provider)
    except llm.LlmError as e:
        from ..errors import cause
        c = cause(str(e), provider)
        return JSONResponse({'error': {'code': c['code'], 'message': c['user'], 'kind': c['kind'], 'cause': c['text'], 'hint': c['hint'], 'raw': c['raw'], 'retryable': c['retryable']}}, status_code=502)


def _named_logs(L: list[dict]) -> list[dict]:
    """기록에 누구의 일이었는지(employee) 이름을 붙인다. 정렬용 시각 t 는 뺀다"""
    ids = sorted({e['employeeId'] for e in L if e.get('employeeId')})
    names = {x['employee_id']: x['name'] for x in db.all_('SELECT employee_id, name FROM public.employees WHERE employee_id = ANY(:i)', i=ids)} if ids else {}
    return [{k: v for k, v in dict(e, employee=names.get(e.get('employeeId'), '')).items() if k != 't'} for e in L]


@r.get('/ai/log', dependencies=[Depends(require_demo_mode)])
def api_log(a: Account = Depends(require_account)):
    """에이전트 동작 보기(시연·디버그 도구 · 운영에서는 아무도 쓰지 않음): 누가 호출했든 모든 계정의 최근 호출, 서버 메모리에만 있다.
    employee 는 그 호출이 누구의 일이었는지, by 는 관리자 화면에서 시작했는지.
    입력·출력·모델 호출 전문은 길어서 목록에는 넣지 않고 펼칠 때 /ai/log/{id} 로 받는다(callCount 는 모델 호출 수)"""
    return {'log': [dict({k: v for k, v in e.items() if k not in ('input', 'output', 'calls')}, callCount=len(e.get('calls') or []))
                    for e in _named_logs(rt.all_logs())]}


@r.get('/ai/log/{entry_id}', dependencies=[Depends(require_demo_mode)])
def api_log_entry(entry_id: int, a: Account = Depends(require_account)):
    """기록 한 건의 전문: 에이전트 입력·출력과 그 안의 모델 호출마다 보낸 메시지·받은 원문(자르지 않음)"""
    e = rt.log_entry(entry_id)
    if e is None:
        raise ApiError(404, 'LOG_NOT_FOUND', '오래된 기록이라 지워졌어요. 목록을 다시 열어 주세요')
    return _named_logs([e])[0]


# ── 시연 도구 ──
@r.put('/me/demo-settings', dependencies=[Depends(require_demo_mode)])
def api_demo_settings(body: dict, a: Account = Depends(require_employee)):
    cur = _settings(a.id)
    demo_mock = bool(body['demoMock']) if 'demoMock' in body else cur['demoMock']
    fs = dict(cur['failSim'])
    if isinstance(body.get('failSim'), dict):
        fs.update({k: bool(v) for k, v in body['failSim'].items() if k in rt.SIM_KINDS})
        rt.reset_tries(a.id)  # 켜고 끌 때 처음부터 센다
    with db.tx() as t:
        t.run("""INSERT INTO app_ext.user_settings(employee_id, demo_mock, fail_sim) VALUES(:e, :d, :f)
                 ON CONFLICT (employee_id) DO UPDATE SET demo_mock = EXCLUDED.demo_mock, fail_sim = EXCLUDED.fail_sim, updated_at = now()""",
              e=a.id, d=demo_mock, f=db.J(fs))
    return _settings(a.id)


@r.post('/demo/reset', dependencies=[Depends(require_demo_mode)])
def api_reset(a: Account = Depends(require_employee)):
    demo.reset(a.id)
    return {'ok': True}


@r.post('/demo/jump', dependencies=[Depends(require_demo_mode)])
def api_jump(body: dict, a: Account = Depends(require_employee)):
    return demo.jump(a.id, str(body.get('stage') or ''))

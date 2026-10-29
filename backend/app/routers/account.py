"""인증·내 정보·AI 모델·시연 도구 (API-01~08, 10~13)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from .. import db, llm
from ..agents import runtime as rt
from ..auth import Account, end_session, login, require_account, require_employee, start_session
from ..config import S, level_ok
from ..errors import ApiError, provider_label, unavailable_reason
from ..services import demo, goals, profile
from . import job_response

r = APIRouter(prefix='/api/v1')


def _settings(employee_id: int) -> dict:
    s = db.one('SELECT ai_provider, demo_mock, fail_sim, reasoning FROM app_ext.user_settings WHERE employee_id = :e', e=employee_id) or {}
    return {'aiProvider': s.get('ai_provider') or 'ollama', 'demoMock': bool(s.get('demo_mock')), 'failSim': s.get('fail_sim') or {},
            'reasoning': s.get('reasoning') or {}}


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


@r.get('/auth/sso/start')
def api_sso():
    raise ApiError(501, 'SSO_NOT_CONNECTED', '시연에서는 기관 통합인증을 연결하지 않았어요. 사번과 비밀번호로 로그인해 주세요')


@r.post('/auth/logout', status_code=204)
def api_logout(request: Request):
    resp = Response(status_code=204)
    end_session(request, resp)
    return resp


@r.get('/demo/accounts')
def api_accounts():
    """로그인 화면의 '직원 고르기'(시연 전용 · 설계서 부록 A). 비밀번호는 보내지 않는다"""
    return {'accounts': profile.accounts(), 'demoPassword': S.demo_password, 'adminLogin': S.admin_login}


@r.get('/me')
def api_me(a: Account = Depends(require_account)):
    return _me(a)


@r.get('/me/profile')
def api_profile(a: Account = Depends(require_employee)):
    v = profile.view(a.id)
    return dict(profile.spec(v), view=v)


@r.put('/me/profile/self')
def api_self(body: dict, a: Account = Depends(require_employee)):
    profile.save_self(a.id, body)
    goals.request(a.id, 'self-input')   # 목표 후보를 새 값으로 다시 만든다(API-06)
    v = profile.view(a.id)
    return dict(profile.spec(v), view=v)


@r.delete('/me/profile/self')
def api_self_revert(a: Account = Depends(require_employee)):
    profile.revert_self(a.id)
    goals.request(a.id, 'self-input-revert')
    v = profile.view(a.id)
    return dict(profile.spec(v), view=v)


@r.put('/me/evaluations/{period}/consent')
def api_consent(period: str, body: dict, a: Account = Depends(require_employee)):
    consent = body.get('consent')
    if type(consent) is not bool:
        raise ApiError(422, 'CONSENT_REQUIRED', '평정 활용 동의 여부를 true 또는 false로 보내 주세요')
    profile.set_consent(a.id, period, consent)
    goals.request(a.id, 'consent')
    return {'period': period, 'consent': consent}


@r.get('/me/goal-suggestions')
def api_goals(a: Account = Depends(require_employee)):
    return goals.get(a.id)


@r.post('/me/goal-suggestions/regenerate')
def api_goals_regen(request: Request, a: Account = Depends(require_employee)):
    jid = goals.regenerate(a.id)
    if not jid:
        return goals.get(a.id)
    return JSONResponse({'jobId': jid, 'status': 'running'}, status_code=202)


# ── AI 모델 (API-10~12) ──
@r.get('/ai/providers')
def api_providers(a: Account = Depends(require_account)):
    cur = _settings(a.id)['aiProvider'] if a.type == 'employee' else 'ollama'
    return {'current': cur, 'providers': [
        {'id': 'ollama', 'label': 'RunPod-Ollama', 'available': llm.available('ollama'), 'reason': unavailable_reason('ollama'), 'target': S.ollama_target if S.ollama_url else '',
         'models': dict({r: llm.model_name('ollama', r) for r in ('default', 'roadmap', 'regulation', 'vision')}, embed=llm.embed_model()),
         'timeout': S.ollama_timeout,
         # 추론 정도(진단·로드맵 모델 · 규정 모델은 늘 끔): default 는 .env 기본값(비면 null = 모델 기본값).
         # Ollama 단계는 모델마다 달라 연결 확인(/ai/status)의 진단·로드맵 모델 models[].think 로 준다
         'reasoning': {'levels': None, 'default': S.ollama_think}},
        {'id': 'openai', 'label': 'OpenAI API', 'available': llm.available('openai'), 'reason': unavailable_reason('openai'),
         'models': {'default': S.openai_model, 'roadmap': S.openai_model, 'regulation': S.openai_model, 'embed': S.openai_embed, 'vision': S.openai_vision},
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
    try:
        return llm.ping(provider)
    except llm.LlmError as e:
        from ..errors import cause
        c = cause(str(e), provider)
        return JSONResponse({'error': {'code': c['code'], 'message': c['user'], 'kind': c['kind'], 'cause': c['text'], 'hint': c['hint'], 'raw': c['raw'], 'retryable': c['retryable']}}, status_code=502)


@r.get('/ai/log')
def api_log(a: Account = Depends(require_account)):
    """에이전트 동작 보기(시연·디버그 도구 · 운영에서는 아무도 쓰지 않음): 누가 호출했든 모든 계정의 최근 호출, 서버 메모리에만 있다.
    employee 는 그 호출이 누구의 일이었는지, by 는 관리자 화면에서 시작했는지"""
    L = rt.all_logs()
    ids = sorted({e['employeeId'] for e in L if e.get('employeeId')})
    names = {x['employee_id']: x['name'] for x in db.all_('SELECT employee_id, name FROM public.employees WHERE employee_id = ANY(:i)', i=ids)} if ids else {}
    return {'log': [{k: v for k, v in dict(e, employee=names.get(e.get('employeeId'), '')).items() if k != 't'} for e in L]}


# ── 시연 도구 ──
@r.put('/me/demo-settings')
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


@r.post('/demo/reset')
def api_reset(a: Account = Depends(require_employee)):
    demo.reset(a.id)
    return {'ok': True}


@r.post('/demo/jump')
def api_jump(body: dict, a: Account = Depends(require_employee)):
    return demo.jump(a.id, str(body.get('stage') or ''))

"""에이전트 한 번의 호출: 모드 결정 → (실패 시연) → 가데이터 또는 실제 모델 → 기록 (4차 AI.run).

모드: 사용자가 고른 'ollama'(RunPod-Ollama) / 'openai'(OpenAI API). 시연 도구 '가데이터로 보기'를 켜면 'mock'.
고른 모드가 설정되지 않았으면 'off' — 가데이터나 다른 모드로 자동 대체하지 않고 실패로 알린다(설계서 v1.7 그림 12).
기록: 화면의 '에이전트 동작 보기'용 입력·출력 요약은 서버 메모리에만, DB(app_ext.agent_calls)에는 메타데이터만(NFR-06).
  '에이전트 동작 보기'는 시연·디버그 전용(운영에서는 직원·부서장·관리자 모두 쓰지 않음)이라 누가 호출했든 모든 계정의 호출을 보여 준다
  (2026-10-26 사용자 결정 · 운영 빌드는 VITE_DEMO_TOOLS=off). 관리자가 시작한 호출(목표 후보 다시 만들기 등)은 by 로 표시한다.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import db, llm
from ..config import S
from ..errors import AgentError

SIM_KINDS = ['goal', 'doc', 'quiz', 'diag', 'gen', 'sup', 'report', 'reg', 'rev']
# 실패 시연 문구: 고른 모드의 실제 오류 문구를 흉내 낸다 (4차 AI.simError)
SIM_ERR = {
    'openai': {'goal': 'OpenAI 시간 초과: 90초 안에 응답 없음 (시연용 실패)', 'quiz': 'OpenAI 연결 실패: 응답 없음 (시연용 실패)', 'diag': 'OpenAI 429: Rate limit reached (시연용 실패)',
               'A2': 'OpenAI 시간 초과: 90초 안에 응답 없음 (시연용 실패)', 'A3': '모델 응답이 JSON 형식이 아니에요 (시연용 실패)', 'report': 'OpenAI 시간 초과: 90초 안에 응답 없음 (시연용 실패)',
               'reg': 'OpenAI 연결 실패: 응답 없음 (시연용 실패)', 'rev': 'OpenAI 시간 초과: 90초 안에 응답 없음 (시연용 실패)', 'doc': 'OpenAI 429: Rate limit reached (시연용 실패)',
               'sup': 'OpenAI 연결 실패: 응답 없음 (시연용 실패)'},
    'ollama': {'goal': 'RunPod 프록시 HTTP 502: Ollama 응답이 아니에요 (시연용 실패)', 'quiz': 'RunPod 프록시 HTTP 502: Ollama 응답이 아니에요 (시연용 실패)',
               'diag': 'Ollama 시간 초과: 180초 안에 응답 없음 (시연용 실패)', 'A2': 'Ollama 시간 초과: 180초 안에 응답 없음 (시연용 실패)',
               'A3': 'Ollama 500: CUDA error: out of memory (시연용 실패)', 'report': 'Ollama 500: CUDA error: out of memory (시연용 실패)',
               'reg': 'RunPod 프록시 HTTP 502: Ollama 응답이 아니에요 (시연용 실패)', 'rev': 'Ollama 시간 초과: 180초 안에 응답 없음 (시연용 실패)',
               'doc': 'Ollama 시간 초과: 180초 안에 응답 없음 (시연용 실패)', 'sup': 'Ollama 500: CUDA error: out of memory (시연용 실패)'},
}
_tries: dict[tuple, int] = {}
_tries_lock = threading.Lock()
_logs: dict[int, deque] = {}


@dataclass
class Ctx:
    employee_id: int
    provider: str = 'ollama'
    demo: bool = False
    fail_sim: dict = field(default_factory=dict)
    me: dict = field(default_factory=dict)  # 화면 모양의 내 프로필(직원 구분·직급·부서 등)
    meta: dict = field(default_factory=dict)  # 마지막 호출의 모드·모델·시간
    by: str = ''  # 호출을 시작한 쪽: 비면 직원 본인, '관리자'면 관리자 화면에서 시작(에이전트 동작 보기 표시용)

    @property
    def mode(self) -> str:
        return 'mock' if self.demo else self.provider if llm.available(self.provider) else 'off'

    @property
    def live(self) -> bool:
        return self.mode in ('ollama', 'openai')


def context(employee_id: int, me: dict | None = None) -> Ctx:
    s = db.one('SELECT ai_provider, demo_mock, fail_sim FROM app_ext.user_settings WHERE employee_id = :e', e=employee_id) or {}
    if me is None:
        from ..services import profile
        me = profile.view(employee_id)
    return Ctx(employee_id, s.get('ai_provider') or 'ollama', bool(s.get('demo_mock')), s.get('fail_sim') or {}, me or {})


def reset_tries(employee_id: int) -> None:
    with _tries_lock:
        for k in [k for k in _tries if k[0] == employee_id]:
            del _tries[k]


def sim_once(ctx: Ctx, kind: str, subject: str, err_key: str | None = None) -> str | None:
    """켜 두면 같은 대상의 첫 시도만 실패한다. 다시 시도하면 성공 (4차 AI.simOnce)"""
    if not ctx.fail_sim.get(kind):
        return None
    k = (ctx.employee_id, kind, subject)
    with _tries_lock:
        _tries[k] = _tries.get(k, 0) + 1
        first = _tries[k] == 1
    if not first:
        return None
    return SIM_ERR['openai' if ctx.provider == 'openai' else 'ollama'][err_key or kind]


def _clip(v, n: int = 1600) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1, default=str)
    return s[:n] + ' …' if len(s) > n else s


def _log(ctx: Ctx, entry: dict) -> None:
    q = _logs.setdefault(ctx.employee_id, deque(maxlen=80))
    q.appendleft(entry)
    try:
        with db.tx() as t:
            t.run("""INSERT INTO app_ext.agent_calls(employee_id, agent, task, mode, model, ms, status, error_kind)
                     VALUES(:e, :a, :t, :m, :mo, :ms, :s, :k)""", e=ctx.employee_id, a=entry['agent'], t=entry['task'], m=entry['mode'], mo=entry.get('model') or None,
                  ms=entry['ms'], s='error' if entry.get('error') else 'ok', k=entry.get('kind'))
    except Exception:  # noqa: BLE001 - 기록 실패가 사용자 요청을 막지 않게(화면 기록은 메모리에 남음)
        pass


def logs(employee_id: int) -> list[dict]:
    return list(_logs.get(employee_id, []))


def all_logs(limit: int = 200) -> list[dict]:
    """모든 계정의 최근 호출(최근 것이 위) · 시연·디버그용 '에이전트 동작 보기'"""
    rows = [e for q in list(_logs.values()) for e in list(q)]
    return sorted(rows, key=lambda e: e.get('t', 0), reverse=True)[:limit]


def run(ctx: Ctx, agent: str, task: str, inp, mock_fn, live_fn, role: str = 'default', sim: str | None = None, mock_delay: float = 0.6,
        log_input=None):
    """한 번의 에이전트 호출. 오류는 AgentError 로 던진다(가데이터로 대신하지 않음)"""
    mode = ctx.mode
    # 컨테이너 시계는 UTC 라 기록 시각은 설정의 시간대(GP5_DB_TIMEZONE · 기본 Asia/Seoul)로 적는다
    e = {'at': datetime.now(ZoneInfo(S.db_timezone)).strftime('%H:%M:%S'), 't': time.time(), 'employeeId': ctx.employee_id, 'by': ctx.by,
         'agent': agent, 'task': task, 'mode': {'openai': 'api'}.get(mode, mode),
         'model': llm.model_name(mode, role) if mode in ('ollama', 'openai') else '', 'input': _clip(log_input if log_input is not None else inp)}
    t0 = time.perf_counter()
    try:
        if mode == 'off':
            e['mode'] = 'off'
            from ..errors import provider_label, unavailable_reason
            raise AgentError(f'모드 사용 불가: {provider_label(ctx.provider)} · {unavailable_reason(ctx.provider)}', ctx.provider)
        if sim:
            e['mode'] = 'sim'
            time.sleep(min(1.2, mock_delay + 0.4))
            raise AgentError(sim, ctx.provider)
        if mode == 'mock':
            time.sleep(mock_delay)
            out = mock_fn(inp)
        else:
            out = live_fn(inp)
        ctx.meta = {'mode': mode, 'model': e['model'], 'ms': round((time.perf_counter() - t0) * 1000), 'loadMs': ctx.meta.get('loadMs', 0) if mode != 'mock' else 0}
    except AgentError as err:
        if e['mode'] not in ('sim', 'off'):
            e['mode'] = 'error'
        e.update(error=str(err), kind=err.info['kind'], output='(결과 없음)', ms=round((time.perf_counter() - t0) * 1000))
        _log(ctx, e)
        raise
    except llm.LlmError as err:
        e.update(mode='error', error=str(err), output='(결과 없음)', ms=round((time.perf_counter() - t0) * 1000))
        ae = AgentError(str(err), ctx.provider)
        e['kind'] = ae.info['kind']
        _log(ctx, e)
        raise ae from err
    e.update(output=_clip(out), ms=round((time.perf_counter() - t0) * 1000))
    _log(ctx, e)
    return out


def parse_json(t: str) -> dict:
    try:
        return json.loads(t)
    except (ValueError, TypeError):
        m = re.search(r'\{[\s\S]*\}', str(t or ''))
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
        raise llm.LlmError('모델 응답이 JSON 형식이 아니에요')


def llm_json(ctx: Ctx, system: str, inp, role: str = 'default', images: list | None = None, history: list | None = None) -> dict:
    """실제 모델에 JSON 응답을 요청한다. ctx.mode 가 ollama/openai 일 때만 부른다"""
    user = {'role': 'user', 'content': json.dumps(inp, ensure_ascii=False, default=str)}
    if images:
        user['images'] = images
    messages = [{'role': 'system', 'content': system}] + list(history or []) + [user]
    res = llm.chat(ctx.mode, messages, role=role, json_mode=True)
    ctx.meta = {'loadMs': res.get('loadMs', 0)}
    return parse_json(res['content'])


def uniq(a):
    out = []
    for x in a:
        if x not in out:
            out.append(x)
    return out


def arr(v, n: int = 6) -> list[str]:
    return [str(x) for x in v if str(x).strip()][:n] if isinstance(v, list) else []

"""모델 호출 (4차 server.py 의 OpenAI·RunPod-Ollama 호출을 옮김 · 표준 라이브러리 urllib).

오류 문구 앞머리(Ollama 연결 실패 / Ollama 시간 초과 / RunPod 프록시 / Ollama 404 / OpenAI 401 …)는 errors.cause() 가
원인·할 일을 고를 때 쓰므로 바꾸면 errors.CAUSES 도 같이 고친다. 키·주소는 화면으로 보내지 않는다.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from .config import OLLAMA_REGULATION_THINK, S


class LlmError(Exception):
    pass


def available(provider: str) -> bool:
    # RunPod-Ollama 모델은 비워 두면 팀 모델(config.OLLAMA_TEAM_*)이라 주소만 있으면 쓸 수 있다
    return bool(S.ollama_url) if provider == 'ollama' else bool(S.openai_key) if provider == 'openai' else False


def _http(url: str, payload: dict | None, headers: dict, timeout: int):
    req = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode('utf-8'),
                                 method='GET' if payload is None else 'POST', headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def openai(path: str, payload: dict | None, timeout: int = 90) -> dict:
    if not S.openai_key:
        raise LlmError('.env 에 OPENAI_API_KEY 가 없어요')
    headers = {'Authorization': f'Bearer {S.openai_key}'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with _http(f'{S.openai_base}/{path}', payload, headers, timeout) as res:
            return json.loads(res.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode('utf-8')).get('error', {}).get('message', '')
        except Exception:  # noqa: BLE001 - 응답 본문이 JSON이 아닐 수 있음
            msg = ''
        raise LlmError(f'OpenAI {e.code}: {msg or e.reason}') from e
    except (socket.timeout, TimeoutError) as e:
        raise LlmError(f'OpenAI 시간 초과: {timeout}초 안에 응답 없음') from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise LlmError(f'OpenAI 시간 초과: {timeout}초 안에 응답 없음') from e
        raise LlmError(f'OpenAI 연결 실패: {e.reason}') from e


def ollama(path: str, payload: dict | None, timeout: int | None = None) -> dict:
    if not S.ollama_url:
        raise LlmError('Ollama 설정이 없어요 (.env 의 OLLAMA_BASE_URL)')
    timeout = timeout or S.ollama_timeout
    headers = {}
    if S.ollama_key:
        headers['Authorization'] = f'Bearer {S.ollama_key}'
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with _http(f'{S.ollama_url}/{path}', payload, headers, timeout) as res:
            body = res.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            msg = json.loads(raw).get('error', '')
        except Exception:  # noqa: BLE001 - RunPod 프록시는 HTML 을 돌려줄 수 있음
            msg = ''
        if not msg:
            if e.code == 524:
                raise LlmError('RunPod 프록시 524: 응답 시간 제한(약 100초)을 넘었어요') from e
            raise LlmError(f'RunPod 프록시 HTTP {e.code}: Ollama 응답이 아니에요 (Pod 꺼짐·시작 중 또는 Ollama 미실행)') from e
        raise LlmError(f'Ollama {e.code}: {msg}') from e
    except (socket.timeout, TimeoutError) as e:
        raise LlmError(f'Ollama 시간 초과: {timeout}초 안에 응답 없음') from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise LlmError(f'Ollama 시간 초과: {timeout}초 안에 응답 없음') from e
        raise LlmError(f'Ollama 연결 실패: {e.reason}') from e
    try:
        return json.loads(body)
    except ValueError as e:
        raise LlmError('RunPod 프록시: Ollama 응답이 아니에요 (Pod 꺼짐·시작 중 또는 Ollama 미실행)') from e


def model_name(provider: str, role: str = 'default') -> str:
    if provider == 'ollama':
        # 로드맵은 진단과 같은 모델을 쓴다
        return {'vision': S.ollama_vision, 'regulation': S.ollama_model_regulation}.get(role, S.ollama_model)
    if provider == 'openai':
        return S.openai_vision if role == 'vision' else S.openai_model
    return ''


def embed_model() -> str:
    """규정 검색 임베딩 모델. AI 모드와 관계없이 OpenAI 모델 하나를 쓴다(팀 합의 2026-10-26 · 팀 DB 벡터가 text-embedding-3-small)"""
    return S.openai_embed


def embed_ready() -> bool:
    return bool(S.openai_key and S.openai_embed)


def _with_images(messages: list, provider: str) -> list:
    out = []
    for m in messages:
        imgs = m.get('images') or []
        if not imgs:
            out.append({k: v for k, v in m.items() if k != 'images'})
        elif provider == 'ollama':
            out.append({'role': m['role'], 'content': m.get('content') or '', 'images': [i['b64'] for i in imgs]})
        else:
            parts = [{'type': 'text', 'text': m.get('content') or ''}]
            parts += [{'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (i.get('mime', 'image/png'), i['b64'])}} for i in imgs]
            out.append({'role': m['role'], 'content': parts})
    return out


def _think(level: str) -> bool | str:
    """단계 이름 → Ollama think 값. on/off 는 켜고 끄기만 되는 모델(qwen 등)의 true/false, 나머지는 모델이 정한 단계 이름 그대로"""
    return {'on': True, 'off': False}.get(level, level)


def _level_name(v) -> str:
    return 'on' if v is True else 'off' if v is False else str(v)


# 모델 이름 → /api/show 로 확인한 추론 정도 단계(연결 확인·호출 때 채움). 화면에 보인 단계와 같은 기준으로 직원 값을 거른다
_think_cache: dict[str, list[str]] = {}


def _ollama_takes(model: str, level: str) -> bool:
    """그 모델이 이 단계를 받는지. 화면은 모델이 받는 단계만 보여 주므로, 모델을 바꾼 뒤 남은 옛 선택(예: high)은
    서버 기본값으로 돌린다(PR #40 리뷰). 단계를 확인하지 못하면(연결 확인 실패) 고른 값을 그대로 보낸다"""
    if model not in _think_cache:
        think_levels(model)
    levels = _think_cache.get(model)
    return levels is None or level in levels


def chat(provider: str, messages: list, role: str = 'default', json_mode: bool = True, reasoning: str | None = None) -> dict:
    """한 번의 대화 호출 → {content, model, provider, loadMs, totalMs}.
    reasoning: 직원이 화면에서 고른 추론 정도(단계 이름). 없으면 .env 기본값(OLLAMA_THINK / OPENAI_REASONING_EFFORT),
    그것도 비면 보내지 않아 모델 기본값을 따른다. 이미지 읽기 모델은 화면에서 고르지 않아 직원 값을 쓰지 않는다.
    RunPod-Ollama 규정 에이전트는 생각을 끄고 학습한 모델이라 직원 값·.env 와 관계없이 늘 끈다(OLLAMA_REGULATION_THINK)"""
    mine = None if role == 'vision' else reasoning
    if provider == 'ollama':
        if role == 'vision' and not S.ollama_vision:
            raise LlmError('Ollama 비전 모델 설정이 없어요 (RunPod-Ollama 팀 모델은 이미지를 읽지 않음)')
        model = model_name('ollama', role)
        payload = {'model': model, 'messages': _with_images(messages, 'ollama'), 'stream': False}
        if json_mode:
            payload['format'] = 'json'
        if S.ollama_num_ctx:
            payload['options'] = {'num_ctx': S.ollama_num_ctx}
        if S.ollama_keep_alive:
            payload['keep_alive'] = S.ollama_keep_alive
        if role == 'regulation':
            level = OLLAMA_REGULATION_THINK
        else:
            level = (mine if mine and _ollama_takes(model, mine) else None) or S.ollama_think
        if level:
            payload['think'] = _think(level)
        res = ollama('api/chat', payload)
        ms = lambda ns: round((ns or 0) / 1e6)  # noqa: E731 - Ollama 시간 값은 나노초
        return {'content': (res.get('message') or {}).get('content') or '', 'model': res.get('model', model), 'provider': 'ollama',
                'loadMs': ms(res.get('load_duration')), 'totalMs': ms(res.get('total_duration'))}
    if role == 'vision' and not S.openai_vision:
        raise LlmError('OpenAI 비전 모델 설정이 없어요 (.env 의 OPENAI_VISION_MODEL)')
    model = model_name('openai', role)
    payload = {'model': model, 'messages': _with_images(messages, 'openai')}
    if json_mode and S.openai_json:
        payload['response_format'] = {'type': 'json_object'}
    # .env 의 단계 목록은 OPENAI_MODEL 의 것이라 다른 비전 모델에는 보내지 않는다.
    # 목록에서 빠진 값(목록을 바꾼 뒤 남은 옛 선택)은 400 이 나므로 기본값으로 돌린다
    level = (mine if mine in S.openai_reasoning_levels else S.openai_reasoning) if model == S.openai_model else None
    if level:
        payload['reasoning_effort'] = level
    # 상세 계획을 쓰는 로드맵만 더 기다린다. 사용자 추론 선택과 다른 기능의 제한은 유지한다.
    timeout = S.openai_roadmap_timeout if role == 'roadmap' else 90
    res = openai('chat/completions', payload, timeout=timeout)
    return {'content': res['choices'][0]['message'].get('content') or '', 'model': res.get('model', model), 'provider': 'openai', 'loadMs': 0, 'totalMs': 0}


def embed(texts: list[str]) -> list[list[float]]:
    """RunPod-Ollama 모드에서도 OpenAI 로 임베딩한다. 키가 없으면 키워드 검색으로 몰래 바꾸지 않고 오류로 알린다(사용자 결정)"""
    if not embed_ready():
        raise LlmError('규정 검색 임베딩에 필요한 OpenAI 키가 없어요 (.env 의 OPENAI_API_KEY)')
    res = openai('embeddings', {'model': S.openai_embed, 'input': texts})
    return [d['embedding'] for d in sorted(res['data'], key=lambda d: d['index'])]


def think_levels(name: str) -> dict | None:
    """Ollama 모델이 고를 수 있는 추론 정도 {levels, default} (/api/show 의 thinking.values · 토큰을 쓰지 않음).
    thinking 이 없는 옛 Ollama 는 capabilities 의 'thinking' 만 보고 켜고 끄기로 본다. 고를 단계가 없으면 levels 가 빈 목록,
    확인하지 못하면 None(화면은 '연결을 확인하면 고를 수 있어요')"""
    try:
        res = ollama('api/show', {'model': name}, timeout=15)
    except LlmError:
        return None
    t = res.get('thinking') or {}
    if t.get('values'):
        levels = [_level_name(v) for v in t['values']]
        default = None if t.get('default') is None else _level_name(t['default'])
    else:
        levels, default = (['off', 'on'] if 'thinking' in (res.get('capabilities') or []) else []), None
    _think_cache[name] = levels = levels if len(levels) > 1 else []
    return {'levels': levels, 'default': default}


def ping(provider: str) -> dict:
    """연결 확인 (토큰을 쓰지 않음). Ollama: 버전 → 설치 모델 → GPU에 올라간 모델 → 모델별 추론 정도 단계"""
    t0 = time.perf_counter()
    if provider == 'openai':
        res = openai(f"models/{quote(S.openai_model, safe='')}", None, timeout=15)
        return {'ok': True, 'provider': 'openai', 'model': res.get('id', S.openai_model), 'ms': round((time.perf_counter() - t0) * 1000)}
    version = ollama('api/version', None, timeout=15).get('version', '')
    tags = ollama('api/tags', None, timeout=15).get('models') or []
    try:
        ps = ollama('api/ps', None, timeout=15).get('models') or []
    except LlmError:
        ps = []
    names = lambda ms: {n for m in ms for n in (m.get('name'), m.get('model')) if n}  # noqa: E731
    have, loaded = names(tags), names(ps)
    hit = lambda n, pool: n in pool or (':' not in n and f'{n}:latest' in pool)  # noqa: E731
    # 진단 모델과 이름이 다른 역할만 더한다: 같은 이름이면 Ollama 에 한 번만 올라가므로 따로 확인할 필요가 없다
    roles = [('default', S.ollama_model)]
    if S.ollama_model_regulation != S.ollama_model:
        roles.append(('regulation', S.ollama_model_regulation))
    return {'ok': True, 'provider': 'ollama', 'target': S.ollama_target, 'version': version,
            # 추론 정도는 진단·로드맵 모델만 고른다(규정 모델은 늘 끔) → 그 모델의 단계만 묻는다
            'models': [{'role': r, 'name': n, 'installed': hit(n, have), 'loaded': hit(n, loaded),
                        'think': think_levels(n) if r == 'default' and hit(n, have) else None} for r, n in roles],
            'ms': round((time.perf_counter() - t0) * 1000)}

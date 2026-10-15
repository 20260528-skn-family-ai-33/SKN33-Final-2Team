"""GrowPath 4차 목업 (Claude) 로컬 서버

- 목업 파일(index.html, assets/)을 제공한다.
- 사용자가 고르는 AI 모델 두 가지를 대신 호출한다. 키·주소는 브라우저로 보내지 않는다.
  · RunPod-Ollama : .env 의 OLLAMA_BASE_URL (RunPod Pod 프록시 주소 또는 로컬 Ollama) 로 로컬 LLM·sLLM 호출
  · OpenAI API    : .env 의 OPENAI_API_KEY 로 OpenAI 호출
  POST /api/chat        에이전트 대화·생성 (JSON 응답) · provider: ollama / openai
  POST /api/reg-search  규정 RAG 검색 (임베딩 코사인 유사도, 결과는 .cache 에 보관) · provider: ollama / openai
                        group: 일반직 / 실무직 (그 직원 구분의 규정 묶음 안에서만 · 국외근무 규정은 overseas 일 때만)
  GET  /api/status      설정 여부와 모델 이름 (주소·키는 보내지 않음)
  GET  /api/ping        연결 확인 · ?provider=ollama 면 Ollama 버전·설치 모델·GPU에 올라간 모델 조회,
                        아니면 OpenAI 모델 조회 (둘 다 토큰을 쓰지 않음)
  POST /api/doc-read    기획서 파일에서 글자·이미지 꺼내기 (docread.py · 4차 묶음 3)
                        이미지를 볼 수 있는 모델(OLLAMA_VISION_MODEL / OPENAI_VISION_MODEL)이 있으면 /api/chat 의 role=vision 으로 이미지를 보낸다
표준 라이브러리만 사용한다(기획서 PDF·HWP 읽기는 pypdf·olefile 이 설치돼 있을 때만). 실행: python server.py [--port 8780] [--open-browser] [--env 설정파일]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import mimetypes
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import docread

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.cache'
STATIC_EXT = {'.html', '.css', '.js', '.png', '.jpg', '.svg', '.ico', '.txt', '.json', '.woff2'}
MAX_BODY = 400_000
# 기획서 파일(base64 · 원본 15MB까지)과 이미지를 함께 보내는 호출은 더 크게 받는다
MAX_BODY_BY_PATH = {'/api/doc-read': 21_000_000, '/api/chat': 10_000_000}
MAX_DOC = 15_000_000
ENV_KEYS = ('OPENAI_API_KEY', 'OPENAI_MODEL', 'OPENAI_EMBED_MODEL', 'OPENAI_BASE_URL', 'OPENAI_JSON_MODE', 'OPENAI_VISION_MODEL',
            'OLLAMA_BASE_URL', 'OLLAMA_MODEL', 'OLLAMA_MODEL_ROADMAP', 'OLLAMA_EMBED_MODEL', 'OLLAMA_VISION_MODEL', 'OLLAMA_API_KEY',
            'OLLAMA_TIMEOUT', 'OLLAMA_NUM_CTX', 'OLLAMA_KEEP_ALIVE')


def env_path() -> Path:
    """--env 로 다른 설정 파일을 줄 수 있다 (모의 Ollama 시험용 등). 기본은 이 폴더의 .env"""
    if '--env' in sys.argv[:-1]:
        return Path(sys.argv[sys.argv.index('--env') + 1]).resolve()
    return ROOT / '.env'


def load_env() -> dict:
    env = {}
    path = env_path()
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ENV_KEYS:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


ENV = load_env()


def install_id() -> str:
    """폴더마다 처음 실행할 때 만드는 설치 표식(.cache/install-id). .cache 는 공유 zip 에 넣지 않으므로
    새로 압축을 푼 폴더는 새 표식을 갖고, 브라우저는 표식이 바뀌면 남아 있던 목업 기록을 지운다"""
    path = CACHE / 'install-id'
    try:
        v = path.read_text(encoding='utf-8').strip()
        if v:
            return v
    except OSError:
        pass
    v = uuid.uuid4().hex
    try:
        CACHE.mkdir(exist_ok=True)
        path.write_text(v, encoding='utf-8')
    except OSError:
        pass  # 쓸 수 없는 폴더면 실행할 때마다 새 표식(= 실행마다 초기화)
    return v


INSTALL_ID = install_id()
# OpenAI
KEY = ENV.get('OPENAI_API_KEY', '')
MODEL = ENV.get('OPENAI_MODEL', '') or 'gpt-6-luna'
EMBED = ENV.get('OPENAI_EMBED_MODEL', '') or 'text-embedding-3-small'
BASE = (ENV.get('OPENAI_BASE_URL', '') or 'https://api.openai.com/v1').rstrip('/')
JSON_MODE = ENV.get('OPENAI_JSON_MODE', 'on').lower() != 'off'
# 기획서 이미지를 볼 모델 (비우면 이미지는 읽지 않고 개수만 알림)
OPENAI_VISION = ENV.get('OPENAI_VISION_MODEL', '')
# RunPod-Ollama (모델 배정이 확정되지 않아 기본 모델 하나 + 로드맵 하위 에이전트용 모델을 따로 둘 수 있게 함)
OLLAMA_URL = ENV.get('OLLAMA_BASE_URL', '').rstrip('/')
OLLAMA_MODEL = ENV.get('OLLAMA_MODEL', '') or 'qwen3.5:9b'
OLLAMA_MODEL_ROADMAP = ENV.get('OLLAMA_MODEL_ROADMAP', '') or OLLAMA_MODEL
OLLAMA_EMBED = ENV.get('OLLAMA_EMBED_MODEL', '')
OLLAMA_VISION = ENV.get('OLLAMA_VISION_MODEL', '')
OLLAMA_KEY = ENV.get('OLLAMA_API_KEY', '')
OLLAMA_TIMEOUT = int(ENV.get('OLLAMA_TIMEOUT', '') or 180)
OLLAMA_NUM_CTX = int(ENV.get('OLLAMA_NUM_CTX', '') or 0)
OLLAMA_KEEP_ALIVE = ENV.get('OLLAMA_KEEP_ALIVE', '')


def ollama_target() -> str:
    host = urlparse(OLLAMA_URL).hostname or ''
    return 'runpod' if host.endswith('runpod.net') else 'local' if host in ('127.0.0.1', 'localhost', '::1') else 'remote'


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def openai(path: str, payload: dict | None, timeout: int = 90) -> dict:
    """payload 가 None 이면 GET (연결 확인용 모델 조회), 아니면 POST"""
    if not KEY:
        raise ApiError(400, '.env 에 OPENAI_API_KEY 가 없어요')
    headers = {'Authorization': f'Bearer {KEY}'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(
        f'{BASE}/{path}', data=None if payload is None else json.dumps(payload).encode('utf-8'),
        method='GET' if payload is None else 'POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode('utf-8')).get('error', {}).get('message', '')
        except Exception:  # noqa: BLE001 - 응답 본문이 JSON이 아닐 수 있음
            msg = ''
        raise ApiError(502, f'OpenAI {e.code}: {msg or e.reason}') from e
    except (socket.timeout, TimeoutError) as e:
        raise ApiError(504, f'OpenAI 시간 초과: {timeout}초 안에 응답 없음') from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise ApiError(504, f'OpenAI 시간 초과: {timeout}초 안에 응답 없음') from e
        raise ApiError(502, f'OpenAI 연결 실패: {e.reason}') from e


def ollama(path: str, payload: dict | None, timeout: int | None = None) -> dict:
    """Ollama HTTP API 호출. 오류 문구 앞머리(Ollama 연결 실패 / Ollama 시간 초과 / RunPod 프록시 / Ollama 404 …)는
    화면에서 원인을 고를 때 쓰므로 바꾸면 assets/gp-ai.js 의 AI.cause 도 같이 고친다"""
    if not OLLAMA_URL:
        raise ApiError(400, 'Ollama 설정이 없어요 (.env 의 OLLAMA_BASE_URL)')
    timeout = timeout or OLLAMA_TIMEOUT
    headers = {}
    if OLLAMA_KEY:
        headers['Authorization'] = f'Bearer {OLLAMA_KEY}'
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(
        f'{OLLAMA_URL}/{path}', data=None if payload is None else json.dumps(payload).encode('utf-8'),
        method='GET' if payload is None else 'POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            msg = json.loads(raw).get('error', '')
        except Exception:  # noqa: BLE001 - RunPod 프록시는 HTML 을 돌려줄 수 있음
            msg = ''
        if not msg:
            if e.code == 524:
                raise ApiError(504, 'RunPod 프록시 524: 응답 시간 제한(약 100초)을 넘었어요') from e
            raise ApiError(502, f'RunPod 프록시 HTTP {e.code}: Ollama 응답이 아니에요 (Pod 꺼짐·시작 중 또는 Ollama 미실행)') from e
        raise ApiError(502, f'Ollama {e.code}: {msg}') from e
    except (socket.timeout, TimeoutError) as e:
        raise ApiError(504, f'Ollama 시간 초과: {timeout}초 안에 응답 없음') from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise ApiError(504, f'Ollama 시간 초과: {timeout}초 안에 응답 없음') from e
        raise ApiError(502, f'Ollama 연결 실패: {e.reason}') from e
    try:
        return json.loads(body)
    except ValueError as e:
        raise ApiError(502, 'RunPod 프록시: Ollama 응답이 아니에요 (Pod 꺼짐·시작 중 또는 Ollama 미실행)') from e


def ollama_model(role: str | None) -> str:
    if role == 'vision':
        if not OLLAMA_VISION:
            raise ApiError(400, 'Ollama 비전 모델 설정이 없어요 (.env 의 OLLAMA_VISION_MODEL)')
        return OLLAMA_VISION
    return OLLAMA_MODEL_ROADMAP if role == 'roadmap' else OLLAMA_MODEL


def with_images(messages: list, provider: str) -> list:
    """메시지의 images([{mime, b64}])를 모델 형식으로 바꾼다. Ollama: images=[base64] · OpenAI: 글+이미지 content 조각"""
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


def ollama_chat(messages: list, role: str | None, json_mode: bool) -> dict:
    model = ollama_model(role)
    payload = {'model': model, 'messages': with_images(messages, 'ollama'), 'stream': False}
    if json_mode:
        payload['format'] = 'json'
    if OLLAMA_NUM_CTX:
        payload['options'] = {'num_ctx': OLLAMA_NUM_CTX}
    if OLLAMA_KEEP_ALIVE:
        payload['keep_alive'] = OLLAMA_KEEP_ALIVE
    res = ollama('api/chat', payload)
    ms = lambda ns: round((ns or 0) / 1e6)  # noqa: E731 - Ollama 시간 값은 나노초
    return {'content': (res.get('message') or {}).get('content') or '', 'model': res.get('model', model), 'provider': 'ollama',
            'loadMs': ms(res.get('load_duration')), 'totalMs': ms(res.get('total_duration')),
            'usage': {'prompt_tokens': res.get('prompt_eval_count'), 'completion_tokens': res.get('eval_count')}}


def ollama_ping() -> dict:
    """서버 응답(버전) → 설치된 모델(tags) → GPU에 올라간 모델(ps) 순서로 확인한다"""
    t0 = time.perf_counter()
    version = ollama('api/version', None, timeout=15).get('version', '')
    tags = ollama('api/tags', None, timeout=15).get('models') or []
    try:
        ps = ollama('api/ps', None, timeout=15).get('models') or []
    except ApiError:
        ps = []
    names = lambda ms: {n for m in ms for n in (m.get('name'), m.get('model')) if n}  # noqa: E731
    have, loaded = names(tags), names(ps)
    hit = lambda n, pool: n in pool or (':' not in n and f'{n}:latest' in pool)  # noqa: E731
    roles = [('default', OLLAMA_MODEL)]
    if OLLAMA_MODEL_ROADMAP != OLLAMA_MODEL:
        roles.append(('roadmap', OLLAMA_MODEL_ROADMAP))
    if OLLAMA_EMBED:
        roles.append(('embed', OLLAMA_EMBED))
    return {'ok': True, 'provider': 'ollama', 'target': ollama_target(), 'version': version,
            'models': [{'role': r, 'name': n, 'installed': hit(n, have), 'loaded': hit(n, loaded)} for r, n in roles],
            'ms': round((time.perf_counter() - t0) * 1000)}


# ── 규정 RAG ──
# 등록 규정 (10/15): 직원 구분마다 규정 묶음을 따로 둔다. 일반직 = assets/regulation-general.js(일반직 규정 16건),
# 실무직 = assets/regulation.js(「실무직 관리규정」). 검색은 요청한 직원 구분의 묶음 안에서만 하고,
# 국외근무 규정은 국외근무 질문(overseas)일 때만 넣는다. 임베딩 결과는 묶음마다 .cache 에 보관한다.
def load_js_object(name: str) -> dict:
    text = (ROOT / 'assets' / name).read_text(encoding='utf-8')
    return json.loads(text[text.index('{'):text.rindex('}') + 1])


def load_regulations() -> dict:
    prac = load_js_object('regulation.js')
    sets = {'실무직': {'regs': {'prac': {'name': prac['name'], 'overseas': False}}, 'articles': [dict(a, reg='prac') for a in prac['articles']]}}
    path = ROOT / 'assets' / 'regulation-general.js'
    if path.exists():
        gen = load_js_object('regulation-general.js')
        sets[gen.get('group') or '일반직'] = {'regs': {r['key']: r for r in gen['regs']}, 'articles': gen['articles']}
    return sets


REG_SETS = load_regulations()
_emb_lock = threading.Lock()
_emb: dict = {}
EMBED_TEXT_MAX = 6000  # 임베딩에 넣는 조항 글자 수 상한(아주 긴 조항은 앞부분만)


def article_text(group: str, a: dict) -> str:
    # 실무직은 예전 캐시를 그대로 쓰도록 10/14 형식 그대로, 일반직은 규정 이름을 앞에 붙인다
    if group == '실무직':
        return f"{a['no']}({a['title']}) {a['chapter']}\n{a['text']}"
    reg = REG_SETS[group]['regs'].get(a['reg'], {})
    return f"「{reg.get('name', '')}」 {a['no']}({a['title']}) {a['chapter']}\n{a['text'][:EMBED_TEXT_MAX]}"


def embed(provider: str, texts: list[str]) -> list[list[float]]:
    if provider == 'ollama':
        if not OLLAMA_EMBED:
            raise ApiError(400, 'Ollama 임베딩 모델 설정이 없어요 (.env 의 OLLAMA_EMBED_MODEL)')
        return ollama('api/embed', {'model': OLLAMA_EMBED, 'input': texts}).get('embeddings') or []
    res = openai('embeddings', {'model': EMBED, 'input': texts})
    return [d['embedding'] for d in sorted(res['data'], key=lambda d: d['index'])]


def embed_many(provider: str, texts: list[str], batch: int = 64) -> list[list[float]]:
    # 조항이 수백 개라 한 번에 보내지 않고 나눠 보낸다(요청 크기 제한)
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        out.extend(embed(provider, texts[i:i + batch]))
    return out


def corpus_vectors(provider: str, group: str) -> dict:
    with _emb_lock:
        key = (provider, group)
        if key in _emb:
            return _emb[key]
        arts = REG_SETS[group]['articles']
        # OpenAI 는 기존 캐시 파일 이름을 그대로 쓰도록 모델 이름만 넣는다
        model = f'ollama:{OLLAMA_EMBED}' if provider == 'ollama' else EMBED
        digest = hashlib.sha256((model + ''.join(article_text(group, a) for a in arts)).encode('utf-8')).hexdigest()[:16]
        CACHE.mkdir(exist_ok=True)
        path = CACHE / f'reg-emb-{digest}.json'
        if path.exists():
            _emb[key] = json.loads(path.read_text(encoding='utf-8'))
            return _emb[key]
        vecs = embed_many(provider, [article_text(group, a) for a in arts])
        _emb[key] = {a['id']: v for a, v in zip(arts, vecs)}
        path.write_text(json.dumps(_emb[key]), encoding='utf-8')
        return _emb[key]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def reg_search(query: str, k: int, provider: str, group: str, overseas: bool) -> list[dict]:
    if group not in REG_SETS:
        return []
    regs = REG_SETS[group]['regs']
    vecs = corpus_vectors(provider, group)
    q = embed(provider, [query])[0]
    arts = [a for a in REG_SETS[group]['articles'] if overseas or not regs.get(a['reg'], {}).get('overseas')]
    scored = sorted(((cosine(q, vecs[a['id']]), a) for a in arts if a['id'] in vecs), key=lambda x: -x[0])
    return [{'id': a['id'], 'score': round(s, 4)} for s, a in scored[:k]]


# ── HTTP ──
class Handler(BaseHTTPRequestHandler):
    server_version = 'GrowPathMock/2'

    def log_message(self, fmt, *args):  # 요청 로그는 경로만 짧게
        print('  ' + (fmt % args))

    def send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # 사내 생활 도우미에서 '멈추기'를 누르면 브라우저가 먼저 연결을 끊는다. 모델 쪽 요청은 이미 끝까지 처리된 뒤다
            print(f'  {self.path} · 브라우저가 응답을 기다리지 않고 연결을 끊었어요 (멈추기 등)')

    def read_json(self, path: str = '') -> dict:
        n = int(self.headers.get('Content-Length') or 0)
        if n > MAX_BODY_BY_PATH.get(path, MAX_BODY):
            raise ApiError(413, '요청이 너무 커요' + (' (기획서 파일은 15MB까지)' if path == '/api/doc-read' else ''))
        return json.loads(self.rfile.read(n).decode('utf-8') or '{}')

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        if path == '/api/status':
            return self.send_json(200, {
                'ok': True, 'installId': INSTALL_ID, 'key': bool(KEY), 'model': MODEL, 'embedModel': EMBED,
                'ollama': {'configured': bool(OLLAMA_URL), 'target': ollama_target() if OLLAMA_URL else '', 'model': OLLAMA_MODEL,
                           'roadmapModel': OLLAMA_MODEL_ROADMAP, 'embedModel': OLLAMA_EMBED, 'timeout': OLLAMA_TIMEOUT},
                'vision': {'ollama': OLLAMA_VISION, 'openai': OPENAI_VISION},
                'docLibs': {'pdf': docread.has_pdf(), 'hwp': docread.has_hwp()}})
        if path == '/api/ping':
            provider = (parse_qs(url.query).get('provider') or ['openai'])[0]
            try:
                if provider == 'ollama':
                    return self.send_json(200, ollama_ping())
                t0 = time.perf_counter()
                res = openai(f"models/{quote(MODEL, safe='')}", None, timeout=15)
                return self.send_json(200, {'ok': True, 'provider': 'openai', 'model': res.get('id', MODEL), 'ms': round((time.perf_counter() - t0) * 1000)})
            except ApiError as e:
                return self.send_json(e.status, {'error': str(e)})
        if path in ('', '/'):
            path = '/index.html'
        target = (ROOT / path.lstrip('/')).resolve()
        rel = target.relative_to(ROOT) if target.is_relative_to(ROOT) else None
        if rel is None or any(p.startswith('.') for p in rel.parts) or target.suffix.lower() not in STATIC_EXT or not target.is_file():
            return self.send_json(404, {'error': 'not found'})
        body = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json'):
            ctype += '; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_json(path)
            provider = data.get('provider') or 'openai'
            if path == '/api/doc-read':
                try:
                    raw = base64.b64decode(str(data.get('data') or ''), validate=True)
                except ValueError as e:
                    raise ApiError(400, '기획서 읽기 실패: 파일 내용을 받지 못했어요') from e
                if len(raw) > MAX_DOC:
                    raise ApiError(413, '요청이 너무 커요 (기획서 파일은 15MB까지)')
                try:
                    return self.send_json(200, docread.read(str(data.get('name') or ''), raw))
                except docread.DocError as e:
                    raise ApiError(422, str(e)) from e
            if path == '/api/chat':
                messages = data.get('messages')
                if not isinstance(messages, list) or not messages:
                    raise ApiError(400, 'messages 가 비어 있어요')
                if provider == 'ollama':
                    return self.send_json(200, ollama_chat(messages, data.get('role'), data.get('json', True)))
                model = MODEL
                if data.get('role') == 'vision':
                    if not OPENAI_VISION:
                        raise ApiError(400, 'OpenAI 비전 모델 설정이 없어요 (.env 의 OPENAI_VISION_MODEL)')
                    model = OPENAI_VISION
                payload = {'model': model, 'messages': with_images(messages, 'openai')}
                if data.get('json', True) and JSON_MODE:
                    payload['response_format'] = {'type': 'json_object'}
                res = openai('chat/completions', payload)
                return self.send_json(200, {'content': res['choices'][0]['message'].get('content') or '', 'model': res.get('model', model), 'provider': 'openai', 'usage': res.get('usage')})
            if path == '/api/reg-search':
                q = str(data.get('query') or '').strip()
                if not q:
                    raise ApiError(400, 'query 가 비어 있어요')
                group = str(data.get('group') or '일반직')
                return self.send_json(200, {'hits': reg_search(q, max(1, min(8, int(data.get('k') or 4))), 'ollama' if provider == 'ollama' else 'openai', group, bool(data.get('overseas')))})
            raise ApiError(404, 'not found')
        except ApiError as e:
            return self.send_json(e.status, {'error': str(e)})
        except (ValueError, KeyError) as e:
            return self.send_json(400, {'error': f'잘못된 요청: {e}'})


class Server(ThreadingHTTPServer):
    # Windows 에서 SO_REUSEADDR 를 켜면 같은 포트에 서버가 겹쳐 뜰 수 있어 끈다
    allow_reuse_address = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8780)
    ap.add_argument('--open-browser', action='store_true')
    ap.add_argument('--env', help='설정 파일 경로 (기본: 이 폴더의 .env)')
    args = ap.parse_args()
    url = f'http://127.0.0.1:{args.port}/'
    try:
        srv = Server(('127.0.0.1', args.port), Handler)
    except OSError:
        print(f'포트 {args.port} 를 이미 다른 프로그램이 쓰고 있어요.')
        print(f'  이미 켜 둔 목업 서버 창을 닫은 뒤 다시 실행하거나, 다른 포트로 실행하세요: python server.py --port {args.port + 1} --open-browser')
        raise SystemExit(1)
    print(f'GrowPath 4차 목업 (Claude) · {url}')
    if OLLAMA_URL:
        roadmap = f' · 로드맵 {OLLAMA_MODEL_ROADMAP}' if OLLAMA_MODEL_ROADMAP != OLLAMA_MODEL else ''
        print(f'  RunPod-Ollama: 설정됨 ({ollama_target()}) · 모델 {OLLAMA_MODEL}{roadmap} · 임베딩 {OLLAMA_EMBED or "없음(키워드 검색)"} · 시간 제한 {OLLAMA_TIMEOUT}초')
    else:
        print('  RunPod-Ollama: 없음 (.env 의 OLLAMA_BASE_URL)')
    print(f'  OpenAI 키: {"설정됨" if KEY else "없음 (.env 의 OPENAI_API_KEY)"} · 모델 {MODEL} · 임베딩 {EMBED}')
    vis = ', '.join(x for x in (OLLAMA_VISION and f'Ollama {OLLAMA_VISION}', OPENAI_VISION and f'OpenAI {OPENAI_VISION}') if x)
    print(f'  기획서 이미지 보기: {vis or "없음 (.env 의 OLLAMA_VISION_MODEL / OPENAI_VISION_MODEL)"}'
          f' · PDF 읽기 {"가능" if docread.has_pdf() else "불가(pypdf 없음)"} · HWP 읽기 {"가능" if docread.has_hwp() else "불가(olefile 없음)"}')
    print('  규정 조항 ' + ' · '.join(f"{g} {len(v['articles'])}개" for g, v in REG_SETS.items()) + ' · 종료: Ctrl+C')
    if args.open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

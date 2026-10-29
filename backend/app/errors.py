"""오류 형식 (설계서 v1.7 6.2): {code, message, hint?, retryable}.

화면은 message(사용자용)와 할 일을 보여 주고, 원인(cause)·조치(hint)·원문(raw)은 '자세히 보기(운영자용)'에 접는다.
에이전트 오류는 4차 화면이 쓰던 종류 이름(kind)도 함께 보낸다(화면의 안내 문구·할 일 선택에 씀).
"""
from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import S


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, hint: str = '', retryable: bool = False, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.hint, self.retryable, self.extra = status, code, message, hint, retryable, extra

    def body(self) -> dict:
        return {'error': dict({'code': self.code, 'message': self.message, 'hint': self.hint, 'retryable': self.retryable}, **self.extra)}


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.body(), status_code=exc.status)


def not_found(what: str = '자료') -> ApiError:
    return ApiError(404, 'NOT_FOUND', f'{what}를 찾을 수 없어요')


def forbidden(message: str = '볼 수 있는 권한이 없어요') -> ApiError:
    return ApiError(403, 'FORBIDDEN', message)


def bad(message: str, code: str = 'BAD_REQUEST') -> ApiError:
    return ApiError(400, code, message)


# ── 에이전트(모델) 오류 → 원인·종류·할 일 (4차 gp-ai.js 의 AI.cause 를 서버로 옮김) ──
# 앞머리 문구(Ollama 연결 실패 / RunPod 프록시 / OpenAI 401 …)는 llm.py 가 만드는 오류 문구와 맞춘다
CAUSES = [
    (r'^모드 사용 불가', 'off', '고른 AI 모델 모드가 설정되지 않아 쓸 수 없어요'),
    (r'작업을 찾을 수 없어요|서버가 다시 시작', 'lost', '서버를 다시 켜서 진행 중이던 작업이 없어졌어요'),
    (r'기획서 형식', 'docfmt', '읽을 수 없는 파일 형식이에요'),
    (r'pypdf 없음|olefile 없음', 'doclib', '서버에 그 형식을 읽는 도구(pypdf·olefile)가 설치되지 않았어요'),
    (r'기획서 읽기 실패', 'docread', '기획서 파일을 읽지 못했어요'),
    (r'요청이 너무 커요', 'docbig', '파일이 너무 커요 (15MB까지)'),
    (r'비전 모델 설정이 없', 'visioncfg', '이미지를 읽는 비전 모델이 없어요(RunPod-Ollama 팀 모델은 이미지를 읽지 않음 · OpenAI는 .env의 OPENAI_VISION_MODEL)'),
    (r'Ollama 설정이 없|OLLAMA_BASE_URL', 'config', '.env에 Ollama 주소(OLLAMA_BASE_URL)가 없어요'),
    (r'규정 검색 임베딩', 'config', '규정 검색 임베딩(text-embedding-3-small)에 쓰는 OpenAI 키(OPENAI_API_KEY)가 .env에 없어요 · RunPod-Ollama 모드도 필요해요'),
    (r'OPENAI_API_KEY', 'config', '.env에 OpenAI 키(OPENAI_API_KEY)가 없어요'),
    (r'RunPod 프록시 524', 'timeout', 'RunPod 프록시의 응답 시간 제한(약 100초)을 넘었어요'),
    # Pod 앞의 nginx 가 키를 확인하는 구성(RunPod Pod 연결 절차) · 401 = 키 없음·틀림
    (r'Ollama 40[13]|RunPod 프록시 HTTP 40[13]', 'auth', 'Ollama 키(OLLAMA_API_KEY)가 없거나 Pod의 키와 달라요'),
    (r'RunPod 프록시', 'conn', 'RunPod Pod가 꺼져 있거나 아직 시작 중이에요 (Ollama가 응답하지 않음)'),
    (r'Ollama 연결 실패', 'conn', 'Ollama 서버에 연결하지 못했어요. RunPod Pod가 꺼져 있거나 주소가 맞지 않아요'),
    (r'Ollama 시간 초과', 'timeout', '응답 시간이 초과됐어요 (Ollama)'),
    (r'out of memory|more system memory|CUDA error', 'memory', 'GPU 메모리가 부족해 모델을 실행하지 못했어요'),
    (r'Ollama 404|not found, try pulling', 'model', 'Ollama에 지정한 모델이 없어요'),
    (r'Ollama 5\d\d', 'other', 'Ollama 서버에서 오류가 났어요'),
    (r'Ollama 4\d\d', 'other', 'Ollama가 요청을 처리하지 못했어요'),
    (r'OpenAI 40[13]', 'auth', 'API 키가 올바르지 않거나 권한이 없어요'),
    (r'OpenAI 404', 'model', '.env에 설정한 모델을 찾을 수 없어요'),
    (r'OpenAI 429', 'limit', '요청이 많거나 사용 한도를 넘어 잠시 제한됐어요'),
    (r'OpenAI 5\d\d', 'other', 'OpenAI 서버에 일시적인 문제가 있어요'),
    (r'OpenAI 시간 초과', 'timeout', 'OpenAI 응답 시간이 초과됐어요'),
    (r'OpenAI 연결 실패', 'conn', 'OpenAI 서버에 연결하지 못했어요'),
    (r'timed? ?out|시간 초과', 'timeout', '응답 시간이 초과됐어요'),
    (r'JSON|형식', 'format', '모델 응답 형식(JSON)이 맞지 않았어요'),
    (r'너무 적|비어 있', 'format', '에이전트가 쓸 수 있는 결과를 충분히 만들지 못했어요'),
]
CODE_OF = {'off': 'AI_UNAVAILABLE', 'lost': 'JOB_LOST', 'conn': 'AI_UNREACHABLE', 'model': 'AI_MODEL_NOT_FOUND', 'timeout': 'AI_TIMEOUT',
           'memory': 'AI_OUT_OF_MEMORY', 'format': 'AI_BAD_OUTPUT', 'auth': 'AI_AUTH', 'limit': 'AI_RATE_LIMIT', 'visioncfg': 'VISION_NOT_SET',
           'docfmt': 'DOC_FORMAT', 'doclib': 'DOC_LIB', 'docread': 'DOC_READ', 'docbig': 'DOC_TOO_BIG', 'config': 'AI_CONFIG', 'server': 'SERVER',
           'other': 'AI_ERROR'}
HINT = {
    'off': {'ollama': '.env에 OLLAMA_BASE_URL을 넣고 서버를 다시 실행해 주세요. 가데이터로 보려면 시연 도구에서 직접 켜야 해요(자동 대체 없음)',
            'any': '.env에 OPENAI_API_KEY를 넣고 서버를 다시 실행해 주세요. 가데이터로 보려면 시연 도구에서 직접 켜야 해요(자동 대체 없음)'},
    'lost': {'any': '다시 시도하면 새 작업으로 만들어요'},
    'server': {'any': '서버(목업_실행.cmd)가 켜져 있는지 확인해 주세요'},
    'config': {'any': '.env를 고친 뒤 서버를 다시 실행해 주세요'},
    'conn': {'ollama': 'RunPod에서 Pod를 켠 뒤 다시 시도하거나, 좌측 ‘AI 모델’에서 다른 모드를 골라 주세요', 'any': '네트워크 상태를 확인한 뒤 다시 시도해 주세요'},
    'timeout': {'ollama': '모델을 GPU에 올리는 중이거나 여러 요청이 몰려 차례를 기다렸을 수 있어요. 잠시 뒤 다시 시도해 주세요', 'any': '잠시 뒤 다시 시도해 주세요'},
    'model': {'ollama': 'Pod에서 팀 모델을 받아 growpath-27b·growpath-regulation-4b 이름으로 만든 뒤(RunPod 연결 절차 2-4) 다시 시도해 주세요. '
                        '.env에 원본 모델 이름을 넣었다면 Pod의 ollama list 이름과 같은지 확인해 주세요',
              'any': '.env의 OPENAI_MODEL을 확인해 주세요'},
    'memory': {'any': '더 큰 GPU의 Pod나 더 작게 양자화한 모델이 필요해요. 동시에 처리하는 요청이 줄면 될 수도 있어요'},
    'auth': {'ollama': '.env의 OLLAMA_API_KEY에 Pod의 키(/workspace/ollama_key.txt)를 그대로 넣고 백엔드를 다시 만들어 주세요(docker compose up -d --no-deps --force-recreate backend)',
             'any': '.env의 OPENAI_API_KEY를 확인해 주세요'},
    'limit': {'any': '잠시 뒤 다시 시도해 주세요'},
    'format': {'any': '다시 시도하면 대부분 해결돼요'},
    'docfmt': {'any': 'DOCX·PPTX·HWPX·PDF·TXT·MD 중 하나로 저장해 다시 고르면 돼요'},
    'doclib': {'any': 'PDF는 pip install pypdf, HWP는 pip install olefile 뒤 서버를 다시 실행해 주세요'},
    'docread': {'any': '파일이 손상됐거나 암호가 걸렸는지 확인해 주세요'},
    'docbig': {'any': '15MB 이하로 줄이거나 필요한 부분만 따로 저장해 주세요'},
    'visioncfg': {'ollama': 'RunPod-Ollama 팀 모델은 이미지를 읽지 않아요. 이미지도 읽으려면 좌측 ‘AI 모델’에서 OpenAI API를 골라 주세요',
                  'any': '.env에 OPENAI_VISION_MODEL을 넣고 서버를 다시 실행해 주세요'},
    'other': {'any': '잠시 뒤 다시 시도해 주세요'},
}
USER_TEXT = {
    'off': '고른 AI 모델을 지금 쓸 수 없어요', 'lost': '진행 중이던 작업을 찾지 못했어요',
    'server': 'AI 서버에 연결하지 못했어요', 'config': 'AI 모델 설정이 아직 준비되지 않았어요', 'conn': 'AI 모델이 지금 응답하지 않아요',
    'model': 'AI 모델을 아직 쓸 수 없어요', 'auth': 'AI 모델을 쓸 권한을 확인하지 못했어요', 'timeout': 'AI 모델의 응답이 너무 오래 걸려 멈췄어요',
    'memory': 'AI 모델이 지금 요청을 처리하지 못했어요', 'limit': '요청이 몰려 AI 모델을 잠시 쓸 수 없어요', 'format': 'AI가 만든 결과를 화면에 쓸 수 없었어요',
    'other': 'AI 모델에서 문제가 생겼어요', 'docfmt': '이 형식의 파일은 읽을 수 없어요', 'doclib': '이 형식을 읽는 도구가 아직 준비되지 않았어요',
    'docread': '기획서 파일을 읽지 못했어요', 'docbig': '파일이 너무 커요(15MB까지)', 'visioncfg': '이미지를 볼 수 있는 AI 모델이 준비되지 않았어요',
}
RETRYABLE = {'lost', 'conn', 'timeout', 'memory', 'format', 'limit', 'other', 'server'}


def cause(message: str, provider: str = '') -> dict:
    """오류 문구 → {kind, text(원인), hint(조치), raw(원문), user(사용자용), code, retryable}"""
    m = str(message or '')
    hit = next(((k, t) for pat, k, t in CAUSES if re.search(pat, m, re.I)), ('other', '알 수 없는 오류가 났어요'))
    kind, text = hit
    ollama = bool(re.search('Ollama|RunPod', m)) or (provider == 'ollama' and 'OpenAI' not in m)
    h = HINT.get(kind, HINT['other'])
    missing = re.search(r'model "([^"]+)" not found', m)
    return {'kind': kind, 'text': f'‘{missing.group(1)}’ 모델이 Ollama에 없어요' if missing else text, 'raw': m,
            'hint': (ollama and h.get('ollama')) or h['any'], 'user': USER_TEXT.get(kind, USER_TEXT['other']),
            'code': CODE_OF.get(kind, 'AI_ERROR'), 'retryable': kind in RETRYABLE}


class AgentError(Exception):
    """에이전트 호출 실패. cause() 결과를 담는다. 가데이터로 대신하지 않는다"""

    def __init__(self, message: str, provider: str = '', stopped: bool = False):
        super().__init__(message)
        self.info = cause(message, provider)
        self.stopped = stopped

    def api(self, status: int = 502) -> ApiError:
        c = self.info
        return ApiError(status, c['code'], c['user'], c['hint'], c['retryable'], kind=c['kind'], cause=c['text'], raw=c['raw'])


def provider_label(p: str) -> str:
    return {'ollama': 'RunPod-Ollama', 'openai': 'OpenAI API', 'mock': '가데이터'}.get(p, p)


def unavailable_reason(p: str) -> str:
    if p == 'ollama':
        return '.env에 OLLAMA_BASE_URL이 없어요' if not S.ollama_url else ''
    return '.env에 OPENAI_API_KEY가 없어요' if p == 'openai' and not S.openai_key else ''

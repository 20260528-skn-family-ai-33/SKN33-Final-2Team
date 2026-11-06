"""사내 도우미 공용 BGE-M3 연결. CLS pooling·정규화 dense 1024차원 서버를 사용한다."""
from __future__ import annotations

import json
import math
import socket
import urllib.error
from urllib.parse import urlparse

from . import llm
from .config import env

BGE_MODEL = 'BAAI/bge-m3'
BGE_DIMENSIONS = 1024


def search_provider() -> str:
    provider = env('REGULATION_EMBED_PROVIDER', 'openai').strip().lower()
    if provider not in ('openai', 'bge-m3'):
        raise llm.LlmError('BGE-M3 설정: REGULATION_EMBED_PROVIDER는 openai 또는 bge-m3여야 해요')
    return provider


def model() -> str:
    return BGE_MODEL


def validate(vectors: list, count: int, dimensions: int) -> list[list[float]]:
    """개수·차원·유한값을 확인하고 불완전한 응답은 저장하지 않는다."""
    if not isinstance(vectors, list) or len(vectors) != count:
        raise llm.LlmError('BGE-M3 응답 형식: 벡터 개수가 입력과 달라요')
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != dimensions:
            raise llm.LlmError('BGE-M3 응답 형식: 벡터 차원이 설정과 달라요')
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in vector):
            raise llm.LlmError('BGE-M3 응답 형식: 유한한 숫자 벡터가 필요해요')
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm == 0:
            raise llm.LlmError('BGE-M3 응답 형식: 영벡터 또는 잘못된 크기예요')
    return vectors


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise llm.LlmError('BGE-M3 응답 형식: 빈 문서는 임베딩할 수 없어요')
    vectors, batch, byte_size = [], [], 0
    for text in texts:
        size = len(text.encode('utf-8'))
        # llama.cpp의 비인과 임베딩 배치가 문맥 8192를 넘지 않도록 묶음을 제한한다.
        if batch and (len(batch) >= 4 or byte_size + size > 17000):
            vectors.extend(_bge_request(batch))
            batch, byte_size = [], 0
        batch.append(text)
        byte_size += size
    if batch:
        vectors.extend(_bge_request(batch))
    return vectors


def _bge_request(texts: list[str]) -> list[list[float]]:
    base = env('BGE_M3_BASE_URL', 'http://127.0.0.1:18671/v1').strip().rstrip('/')
    try:
        parsed = urlparse(base)
        timeout = int(env('BGE_M3_TIMEOUT', '90'))
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not 1 <= timeout <= 600:
            raise ValueError
    except ValueError:
        raise llm.LlmError('BGE-M3 설정: BGE_M3_BASE_URL은 인증정보 없는 http(s) 주소, BGE_M3_TIMEOUT은 1~600초여야 해요') from None
    payload = {'model': BGE_MODEL, 'input': texts, 'encoding_format': 'float'}
    try:
        with llm._http(base + '/embeddings', payload,
                       {'Content-Type': 'application/json'}, timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        # 서버 원문에는 문서나 내부 주소가 들어갈 수 있으므로 상태 코드만 전달한다.
        raise llm.LlmError(f'BGE-M3 HTTP {exc.code}: 임베딩 요청에 실패했어요') from None
    except (socket.timeout, TimeoutError):
        raise llm.LlmError('BGE-M3 시간 초과: 임베딩 응답을 기다리다 멈췄어요') from None
    except urllib.error.URLError as exc:
        reason = '시간 초과' if isinstance(exc.reason, (socket.timeout, TimeoutError)) else '연결 실패'
        raise llm.LlmError(f'BGE-M3 {reason}: 임베딩 서버를 확인해 주세요') from None
    except OSError:
        raise llm.LlmError('BGE-M3 연결 실패: 임베딩 서버 응답이 끊겼어요') from None
    except (ValueError, UnicodeError):
        raise llm.LlmError('BGE-M3 응답 형식: 올바른 JSON이 아니에요') from None
    try:
        if result['model'] != BGE_MODEL:
            raise ValueError
        rows = result['data']
        if len(rows) != len(texts) or any(type(row['index']) is not int for row in rows):
            raise ValueError
        if sorted(row['index'] for row in rows) != list(range(len(texts))):
            raise ValueError
        vectors = [row['embedding'] for row in sorted(rows, key=lambda row: row['index'])]
    except (KeyError, TypeError, ValueError):
        raise llm.LlmError('BGE-M3 응답 형식: 모델 이름·입력 순서·벡터 개수를 확인해 주세요') from None
    return validate(vectors, len(texts), BGE_DIMENSIONS)

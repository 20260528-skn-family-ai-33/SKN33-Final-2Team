"""규정·회사·생활·학습 자료 공용 BGE-M3 연결. 고정 revision·CLS·L2·1024차원을 검사한다."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import json
import math
import socket
import urllib.error
from urllib.parse import urlparse

from . import llm
from .config import env
from .bge_model import MODEL as BGE_MODEL, DIMENSIONS as BGE_DIMENSIONS, INDEX_PROTOCOLS, MAX_TOKENS, PROVENANCE


@dataclass(frozen=True)
class IndexedEmbedding:
    """색인에 저장할 벡터와 서버가 보고한 실제 추론 정보."""
    vector: list[float]
    protocol: str
    token_count: int


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


def _require_text(texts: list[str]) -> None:
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise llm.LlmError('BGE-M3 응답 형식: 빈 문서는 임베딩할 수 없어요')


def _batches(texts: list[str]) -> Iterator[list[str]]:
    batch, byte_size = [], 0
    for text in texts:
        size = len(text.encode('utf-8'))
        # CPU 서버의 요청당 입력 수와 긴 문서 배치의 메모리 사용을 제한한다.
        if batch and (len(batch) >= 4 or byte_size + size > 17000):
            yield batch
            batch, byte_size = [], 0
        batch.append(text)
        byte_size += size
    if batch:
        yield batch


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    _require_text(texts)
    return [vector for batch in _batches(texts) for vector in _bge_request(batch)]


def embed_for_index(texts: list[str]) -> list[IndexedEmbedding]:
    """색인 저장용 임베딩. 서버가 실제 정밀도·토큰 수를 주지 않으면 추정값을 기록하지 않고 멈춘다."""
    if not texts:
        return []
    _require_text(texts)
    result = []
    for batch in _batches(texts):
        response = _bge_response(batch)
        result.extend(_indexed(response, _vectors(response, batch)))
    return result


def _bge_request(texts: list[str]) -> list[list[float]]:
    return _vectors(_bge_response(texts), texts)


def _bge_response(texts: list[str]) -> dict:
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
            return json.loads(response.read().decode('utf-8'))
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


def _vectors(result: dict, texts: list[str]) -> list[list[float]]:
    try:
        if result['model'] != BGE_MODEL or any(result.get(key) != value for key, value in PROVENANCE.items()):
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


def _indexed(result: dict, vectors: list[list[float]]) -> list[IndexedEmbedding]:
    try:
        protocol = INDEX_PROTOCOLS[result['precision']]
        counts = [row['token_count'] for row in sorted(result['data'], key=lambda row: row['index'])]
        if any(type(count) is not int or not 1 <= count <= MAX_TOKENS for count in counts):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise llm.LlmError('BGE-M3 응답 형식: 추론 정밀도·토큰 수가 없어요. bge-m3 서버를 최신 코드로 다시 빌드해 주세요') from None
    return [IndexedEmbedding(vector, protocol, count) for vector, count in zip(vectors, counts, strict=True)]

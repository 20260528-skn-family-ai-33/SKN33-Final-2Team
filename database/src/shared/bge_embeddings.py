"""공식 BGE-M3 서버만 사용하는 DB 도구용 임베딩 연결."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import urllib.request
from urllib.parse import urlparse

_contract = json.loads(Path(__file__).with_name('bge_model.json').read_text(encoding='utf-8'))
MODEL = _contract['model']
DIMENSIONS = _contract['dimensions']
PROVENANCE = {key: _contract[key] for key in ('model_revision', 'weights_sha256', 'pooling', 'normalization')}
# 서버가 보고한 추론 정밀도 → 검증 기록의 프로토콜. 공유 백업의 기존 행은 GPU FP16 값을 유지한다.
INDEX_PROTOCOLS = _contract['index_protocols']
ACCEPTED_PROTOCOLS = tuple(INDEX_PROTOCOLS.values())
MAX_TOKENS = 8192


@dataclass(frozen=True)
class IndexedEmbedding:
    """색인에 저장할 벡터와 서버가 보고한 실제 추론 정보."""
    vector: list[float]
    protocol: str
    token_count: int


def vector_values(value) -> list[float]:
    values = json.loads(value) if isinstance(value, str) else value
    if (not isinstance(values, list) or len(values) != DIMENSIONS
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in values)
            or not math.isfinite(math.hypot(*values)) or not any(values)):
        raise ValueError('Invalid regulation vector: expected 1024 finite values and nonzero norm')
    return values


def request(payload: dict) -> dict:
    base = os.environ.get('BGE_M3_BASE_URL', 'http://127.0.0.1:18671/v1').rstrip('/')
    try:
        parsed = urlparse(base)
        timeout = int(os.environ.get('BGE_M3_TIMEOUT', '90'))
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or not 1 <= timeout <= 600):
            raise ValueError
    except ValueError:
        raise ValueError('BGE_M3_BASE_URL 또는 BGE_M3_TIMEOUT 설정을 확인하세요.') from None
    req = urllib.request.Request(base + '/embeddings', json.dumps(payload).encode('utf-8'),
                                 {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError):
        raise ValueError('BGE-M3 서버 연결 또는 응답 오류입니다. 입력·설정·서버 상태를 확인하세요.') from None


def _checked_batches(texts: list[str], client):
    """4건씩 요청해 모델 계약·입력 순서를 확인한 (응답, 정렬된 행, 벡터)를 낸다."""
    if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError('Empty BGE-M3 input')
    send = request if client is None else client
    for start in range(0, len(texts), 4):
        batch = texts[start:start + 4]
        response = send({'model': MODEL, 'input': batch, 'encoding_format': 'float'})
        try:
            if response['model'] != MODEL or any(response.get(key) != value for key, value in PROVENANCE.items()):
                raise ValueError
            rows = response['data']
            if (len(rows) != len(batch) or any(type(row['index']) is not int for row in rows)
                    or sorted(row['index'] for row in rows) != list(range(len(batch)))):
                raise ValueError
            rows = sorted(rows, key=lambda row: row['index'])
            vectors = [vector_values(row['embedding']) for row in rows]
        except (KeyError, TypeError, ValueError):
            raise ValueError('BGE-M3 모델 계약·입력 순서·벡터 응답이 올바르지 않습니다.') from None
        yield response, rows, vectors


def embed_texts(texts: list[str], client=None) -> list[list[float]]:
    """원문을 자르지 않고 전달한다. client는 테스트용 JSON 요청 함수다."""
    return [vector for _, _, vectors in _checked_batches(texts, client) for vector in vectors]


def embed_for_index(texts: list[str], client=None) -> list[IndexedEmbedding]:
    """색인 저장용 임베딩. 서버가 실제 정밀도·토큰 수를 주지 않으면 추정값을 기록하지 않고 멈춘다."""
    result = []
    for response, rows, vectors in _checked_batches(texts, client):
        try:
            protocol = INDEX_PROTOCOLS[response['precision']]
            counts = [row['token_count'] for row in rows]
            if any(type(count) is not int or not 1 <= count <= MAX_TOKENS for count in counts):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError('BGE-M3 서버가 추론 정밀도·토큰 수를 보내지 않았습니다. bge-m3 서버를 최신 코드로 다시 빌드하세요.') from None
        result.extend(IndexedEmbedding(vector, protocol, count) for vector, count in zip(vectors, counts, strict=True))
    return result

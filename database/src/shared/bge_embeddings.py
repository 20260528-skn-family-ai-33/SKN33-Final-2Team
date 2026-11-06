"""공식 BGE-M3 서버만 사용하는 DB 도구용 임베딩 연결."""
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


def embed_texts(texts: list[str], client=None) -> list[list[float]]:
    """원문을 자르지 않고 전달한다. client는 테스트용 JSON 요청 함수다."""
    if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError('Empty BGE-M3 input')
    result = []
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
            result.extend(vector_values(row['embedding']) for row in sorted(rows, key=lambda row: row['index']))
        except (KeyError, TypeError, ValueError):
            raise ValueError('BGE-M3 모델 계약·입력 순서·벡터 응답이 올바르지 않습니다.') from None
    return result

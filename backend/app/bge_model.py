"""#124 공유 DB와 질문 임베딩이 함께 지켜야 하는 모델 계약."""
import json
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parents[2] / 'database/src/shared/bge_model.json'
_contract = json.loads(CONTRACT_PATH.read_text(encoding='utf-8'))
MODEL = _contract['model']
DIMENSIONS = _contract['dimensions']
REVISION = _contract['model_revision']
WEIGHTS_SHA256 = _contract['weights_sha256']
PROVENANCE = {key: _contract[key] for key in ('model_revision', 'weights_sha256', 'pooling', 'normalization')}
# 서버가 보고한 추론 정밀도 → 검증 기록의 프로토콜. 공유 백업의 기존 행은 GPU FP16 값을 유지한다.
INDEX_PROTOCOLS = _contract['index_protocols']
ACCEPTED_PROTOCOLS = tuple(INDEX_PROTOCOLS.values())
MAX_TOKENS = 8192

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

"""#124 공식 가중치의 dense CLS+L2 CPU 임베딩 API. 생성 LLM을 로드하지 않는다."""
from contextlib import asynccontextmanager
import hashlib
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import torch
from transformers import AutoModel, AutoTokenizer
from app.bge_model import MODEL, DIMENSIONS, PROVENANCE, WEIGHTS_SHA256

state = {}
lock = threading.Lock()


def inference_dtype(value: str):
    if value not in ('float16', 'float32'):
        raise ValueError('BGE_M3_DTYPE는 float16 또는 float32여야 합니다.')
    return torch.float16 if value == 'float16' else torch.float32


@asynccontextmanager
async def lifespan(app):
    root = Path(os.environ.get('BGE_M3_MODEL_DIR', '/models'))
    digest = hashlib.file_digest((root / 'pytorch_model.bin').open('rb'), 'sha256').hexdigest()
    if digest != WEIGHTS_SHA256:
        raise RuntimeError('BGE-M3 가중치 SHA-256이 공유 DB의 계약과 다릅니다.')
    torch.set_num_threads(int(os.environ.get('BGE_M3_THREADS', '4')))
    state['precision'] = os.environ.get('BGE_M3_DTYPE', 'float32')
    state['tokenizer'] = AutoTokenizer.from_pretrained(root, local_files_only=True)
    state['model'] = AutoModel.from_pretrained(root, local_files_only=True, use_safetensors=False,
                                               dtype=inference_dtype(state['precision']), low_cpu_mem_usage=True).eval()
    yield
    state.clear()


app = FastAPI(lifespan=lifespan)


class EmbeddingRequest(BaseModel):
    model: str
    input: list[str] = Field(min_length=1, max_length=4)
    encoding_format: str = 'float'


@app.get('/health')
def health():
    if not state.get('model'):
        raise HTTPException(503, 'BGE model loading')
    return {'model': MODEL, 'dimensions': DIMENSIONS, **PROVENANCE, 'device': 'cpu',
            'precision': state['precision'], 'normalization_dtype': 'float32'}


@app.post('/v1/embeddings')
def embeddings(request: EmbeddingRequest):
    if request.model != MODEL or request.encoding_format != 'float' or any(not text.strip() for text in request.input):
        raise HTTPException(400, 'Invalid model, encoding format or empty input')
    with lock, torch.inference_mode():
        tokens = state['tokenizer'](request.input, padding=True, truncation=False, return_tensors='pt')
        if tokens['input_ids'].shape[1] > 8192:
            raise HTTPException(400, 'BGE input exceeds 8192 tokens; input was not truncated')
        output = state['model'](**tokens).last_hidden_state[:, 0].float()
        vectors = torch.nn.functional.normalize(output, p=2, dim=1)
        if vectors.shape[1] != DIMENSIONS or not torch.isfinite(vectors).all():
            raise HTTPException(500, 'Invalid BGE dense vectors')
        return {'model': MODEL, **PROVENANCE, 'data': [
            {'index': index, 'embedding': vector.tolist()} for index, vector in enumerate(vectors)]}

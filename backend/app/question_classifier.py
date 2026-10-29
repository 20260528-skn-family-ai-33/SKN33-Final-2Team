"""팀 RoBERTa 질문 분류기. 로컬 manifest로 확인한 파일만 CPU에서 읽는다."""
from __future__ import annotations

import hashlib
import json
import pickle
import threading
import time
from pathlib import Path
from typing import Any

from .config import ROOT, env
from .llm import LlmError

LABELS = ('범위 밖', '사내 규정', '사내 생활안내', '수자원공사 정보')
_lock = threading.RLock()
_loaded: tuple[Any, Any, Any, dict] | None = None


def _load() -> tuple[Any, Any, Any, dict]:
    global _loaded
    if _loaded is not None:
        return _loaded
    directory = Path(env('GP5_CLASSIFIER_DIR', str(ROOT / 'models')))
    try:
        manifest = json.loads((directory / 'classifier-manifest.json').read_text(encoding='utf-8'))
        if tuple(manifest['labels']) != LABELS or manifest['max_length'] != 128:
            raise ValueError('학습 라벨 또는 입력 길이가 맞지 않아요')
        # 전체 객체 .pt는 pickle을 사용한다. 사용자가 제공한 파일의 고정 해시부터 확인한다.
        required = ('klue_roberta_full_model.pt', 'tokenizer.json', 'tokenizer_config.json', 'config.json')
        for name in required:
            path = directory / name
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != manifest['sha256'][name]:
                raise ValueError(f'{name} 해시가 manifest와 달라요')
        import torch
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        model = torch.load(directory / required[0], map_location='cpu', weights_only=False)
        if tuple(model.config.id2label.get(i) for i in range(model.config.num_labels)) != LABELS:
            raise ValueError('모델의 라벨 순서가 학습 기록과 달라요')
        model.to('cpu').eval()
        _loaded = torch, tokenizer, model, manifest
        return _loaded
    except (OSError, ValueError, KeyError, TypeError, ImportError, AttributeError, RuntimeError,
            pickle.UnpicklingError, EOFError) as exc:
        raise LlmError('질문 분류 모델 준비 실패: 모델·토크나이저·manifest와 추론 패키지를 확인해 주세요') from exc


def classify(question: str) -> dict:
    """질문 → 학습 때와 같은 128토큰 입력 → 4개 라벨의 확률과 선택 결과."""
    if not isinstance(question, str) or not question.strip():
        raise LlmError('질문 분류 입력이 비어 있어요')
    started = time.perf_counter()
    with _lock:
        torch, tokenizer, model, manifest = _load()
        try:
            inputs = tokenizer(question.strip(), return_tensors='pt', padding='max_length',
                               truncation=True, max_length=manifest['max_length'])
            with torch.inference_mode():
                logits = model(**inputs).logits
                probabilities = torch.softmax(logits, dim=-1)[0]
            if probabilities.shape[0] != len(LABELS) or not torch.isfinite(probabilities).all():
                raise ValueError('분류 확률이 유효하지 않아요')
            index = int(probabilities.argmax().item())
            return {'model': 'klue_roberta_full_model.pt', 'label': LABELS[index],
                    'confidence': round(float(probabilities[index].item()), 6),
                    'ms': round((time.perf_counter() - started) * 1000)}
        except (ValueError, TypeError, RuntimeError, AttributeError) as exc:
            raise LlmError('질문 분류 모델 추론 실패: 입력과 모델 실행 환경을 확인해 주세요') from exc

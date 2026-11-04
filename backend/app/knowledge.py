"""회사 정보·사내 생활 자료의 범주별 읽기 전용 벡터 검색."""
from __future__ import annotations

import json
import math

from . import db, llm

CATEGORY = '수자원공사 정보'
LIFE_CATEGORY = '사내 생활안내'
MODEL = 'text-embedding-3-small'
DIMENSIONS = 1536


def search_company(question: str) -> list[dict]:
    """질문 1개 임베딩 → 같은 모델·범주의 검증된 실제 자료 최대 5개."""
    return _search(question, CATEGORY)


def search_life(question: str) -> list[dict]:
    """DB에 등록한 생활 자료만 검색하고 가상 여부·자료 제약을 함께 돌려준다."""
    return _search(question, LIFE_CATEGORY)


def _search(question: str, category: str) -> list[dict]:
    if category not in (CATEGORY, LIFE_CATEGORY):
        raise llm.LlmError('검색 자료의 범주가 올바르지 않아요')
    title = '회사 정보' if category == CATEGORY else '사내 생활'
    real_only = category == CATEGORY
    if not question.strip():
        raise llm.LlmError(f'{title} 검색 질문이 비어 있어요')
    if llm.embed_model() != MODEL:
        raise llm.LlmError(f'{title} 검색 임베딩은 text-embedding-3-small이어야 해요')
    counts = db.one("""SELECT count(*) AS total,
        count(*) FILTER (WHERE c.embedding IS NOT NULL AND c.embedding_model=:model
            AND c.dimensions=:dims AND c.input_sha256=c.chunk_text_sha256) AS indexed
        FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        WHERE d.category=:category AND (NOT :real_only OR NOT c.is_virtual)""",
        category=category, real_only=real_only, model=MODEL, dims=DIMENSIONS) or {}
    if not counts.get('total'):
        return []
    if not counts.get('indexed'):
        raise llm.LlmError(f'{title} 검색 임베딩이 준비되지 않았어요')
    if not llm.embed_ready():
        raise llm.LlmError(f'{title} 검색 임베딩에 필요한 OpenAI 키가 없어요')
    vectors = llm.embed([question])
    if (len(vectors) != 1 or len(vectors[0]) != DIMENSIONS
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                       and math.isfinite(value) for value in vectors[0])
            or not any(vectors[0])):
        raise llm.LlmError(f'{title} 검색 임베딩 형식이 올바르지 않아요')
    vector = json.dumps(vectors[0], allow_nan=False)
    return db.all_("""WITH candidates AS MATERIALIZED (
        SELECT c.chunk_id,c.chunk_text,c.chunk_text_sha256,c.is_virtual,c.metadata,
               d.document_id,d.category,d.title AS document_title,
               1-(c.embedding <=> CAST(:query AS vector)) AS similarity
        FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        WHERE d.category=:category AND (NOT :real_only OR NOT c.is_virtual)
          AND c.embedding_model=:model AND c.dimensions=:dims
          AND c.input_sha256=c.chunk_text_sha256 AND c.embedding IS NOT NULL)
        SELECT * FROM candidates WHERE similarity>=:threshold
        ORDER BY similarity DESC,chunk_id LIMIT 5""",
        query=vector, category=category, real_only=real_only, model=MODEL, dims=DIMENSIONS, threshold=0.25)

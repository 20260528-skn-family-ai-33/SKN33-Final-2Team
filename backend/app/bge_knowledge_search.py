"""회사·생활 원문 → BGE-M3 1024차원·BM25 → RRF로 합친 범주별 RAG 근거."""
from __future__ import annotations

import hashlib
import json

from . import bge_provenance as provenance, db, hybrid_search, llm, regulation_embeddings as embeddings

TABLE = 'knowledge.chunks'
META_TABLE = provenance.META_TABLE
CATEGORIES = ('수자원공사 정보', '사내 생활안내')


def install_schema() -> None:
    """공유 DB를 사용한다. OpenAI 스키마를 BGE DB에 적용하거나 새 sidecar를 만들지 않는다."""
    if not db.val('SELECT to_regclass(:table)', table=TABLE):
        raise llm.LlmError('BGE-M3 색인: #124 공유 BGE DB를 먼저 복원해 주세요')


def source_chunks(category: str | None = None) -> list[dict]:
    if category is not None and category not in CATEGORIES:
        raise ValueError('등록되지 않은 자료 범주예요')
    return db.all_('''SELECT c.chunk_id,c.chunk_text,c.chunk_text_sha256,d.category
        FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        WHERE d.category=ANY(:categories) ORDER BY c.chunk_id''',
        categories=[category] if category else list(CATEGORIES))


def _is_current(row: dict | None, sha: str) -> bool:
    return (row is not None and row['input_sha256'] == sha
            and row['dimensions'] == embeddings.BGE_DIMENSIONS
            and provenance.is_current(row, sha, sha))


def ensure_vectors(chunks: list[dict]) -> int:
    """원문 전체를 입력하고 입력 해시가 같은 행은 재사용한다. 배치별 저장으로 재개한다."""
    if not chunks:
        return 0
    for chunk in chunks:
        if hashlib.sha256(chunk['chunk_text'].encode('utf-8')).hexdigest() != chunk['chunk_text_sha256']:
            raise llm.LlmError('BGE-M3 색인: 자료 원문 해시가 달라요')
    stored = {row['chunk_id']: row for row in db.all_(f'''
        SELECT c.chunk_id,c.input_sha256,c.dimensions,
               p.source_sha256 AS meta_sha256, p.actual_input_sha256, p.model_revision, p.protocol, p.token_count
        FROM {TABLE} c
        LEFT JOIN {META_TABLE} p ON p.kind='knowledge' AND p.source_id=c.chunk_id
        WHERE c.embedding_model=:model AND c.chunk_id=ANY(:ids)''',
        model=embeddings.BGE_MODEL, ids=[chunk['chunk_id'] for chunk in chunks])}
    missing = [chunk for chunk in chunks if not _is_current(stored.get(chunk['chunk_id']), chunk['chunk_text_sha256'])]
    for offset in range(0, len(missing), 4):
        part = missing[offset:offset + 4]
        indexed = embeddings.embed_for_index([chunk['chunk_text'] for chunk in part])
        vectors = embeddings.validate([item.vector for item in indexed], len(part), embeddings.BGE_DIMENSIONS)
        with db.tx() as transaction:
            for chunk, vector, item in zip(part, vectors, indexed, strict=True):
                provenance.save_input(transaction, 'knowledge', chunk['chunk_id'],
                                      chunk['chunk_text_sha256'], chunk['chunk_text_sha256'], item)
                changed = transaction.run(f'''UPDATE {TABLE} SET embedding_model=:model,dimensions=:dims,
                    input_sha256=:sha,embedding=CAST(:vector AS vector),embedded_at=now()
                    WHERE chunk_id=:id AND chunk_text_sha256=:sha''',
                    id=chunk['chunk_id'], model=embeddings.BGE_MODEL, dims=embeddings.BGE_DIMENSIONS,
                    sha=chunk['chunk_text_sha256'], vector=json.dumps(vector, allow_nan=False))
                if changed != 1:
                    raise llm.LlmError('BGE-M3 색인: 색인 중 자료 원문이 바뀌었어요. 다시 확인해 주세요')
    return len(missing)


def search(question: str, category: str) -> list[dict]:
    """검색은 DB에 쓰지 않는다. 누락·변경 색인을 성공이나 다른 모델로 대체하지 않는다."""
    if category not in CATEGORIES:
        raise llm.LlmError('검색 자료의 범주가 올바르지 않아요')
    title = '회사 정보' if category == CATEGORIES[0] else '사내 생활'
    if not question.strip():
        raise llm.LlmError(f'{title} 검색 질문이 비어 있어요')
    hybrid = hybrid_search.enabled()
    if not db.val('SELECT to_regclass(:table)', table=TABLE):
        raise llm.LlmError('BGE-M3 색인: index_knowledge.py --apply로 자료 색인을 먼저 준비해 주세요')
    params = dict(category=category, real_only=category == CATEGORIES[0],
                  model=embeddings.BGE_MODEL, dims=embeddings.BGE_DIMENSIONS,
                  revision=embeddings.PROVENANCE['model_revision'])
    counts = db.one(f'''SELECT count(*) AS total,
        count(CASE WHEN v.chunk_id IS NOT NULL AND p.source_id IS NOT NULL THEN 1 END) AS indexed
        FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        LEFT JOIN {TABLE} v ON v.chunk_id=c.chunk_id AND v.embedding_model=:model
            AND v.dimensions=:dims AND v.input_sha256=c.chunk_text_sha256
        LEFT JOIN {META_TABLE} p ON p.kind='knowledge' AND p.source_id=c.chunk_id
            AND p.source_sha256=c.chunk_text_sha256 AND p.model_revision=:revision
        WHERE d.category=:category AND (NOT :real_only OR NOT c.is_virtual)''', **params) or {}
    if not counts.get('total'):
        return []
    if counts.get('indexed') != counts['total']:
        raise llm.LlmError(f'BGE-M3 색인: {title} 벡터가 없거나 원문과 달라요. index_knowledge.py --apply를 실행해 주세요')
    vector = embeddings.validate(embeddings.embed([question]), 1, embeddings.BGE_DIMENSIONS)[0]
    fields = '''c.chunk_id,c.chunk_text,c.chunk_text_sha256,c.is_virtual,c.metadata,
                d.document_id,d.category,d.title AS document_title'''
    source = f'''FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        JOIN {TABLE} v ON v.chunk_id=c.chunk_id
        JOIN {META_TABLE} p ON p.kind='knowledge' AND p.source_id=c.chunk_id
            AND p.source_sha256=c.chunk_text_sha256 AND p.model_revision=:revision
        WHERE d.category=:category AND (NOT :real_only OR NOT c.is_virtual)
          AND v.embedding_model=:model AND v.dimensions=:dims
          AND v.input_sha256=c.chunk_text_sha256'''
    dense = db.all_(f'''WITH candidates AS MATERIALIZED (
        SELECT {fields},1-(v.embedding <=> CAST(:query AS vector)) AS similarity {source})
        SELECT * FROM candidates WHERE similarity>=:threshold
        ORDER BY similarity DESC,chunk_id LIMIT :limit''',
        limit=hybrid_search.CANDIDATES if hybrid else 5,
        **params, query=json.dumps(vector, allow_nan=False), threshold=0.25)
    if not hybrid:
        return dense
    # BM25는 벡터 상위 후보 밖의 정확한 키워드도 찾도록 허용된 원문 전체에서 독립 검색한다.
    corpus = db.all_(f'SELECT {fields} {source} ORDER BY c.chunk_id', **params)
    keywords = hybrid_search.bm25(question, [(row['chunk_id'], row['document_title'] + '\n' + row['chunk_text']) for row in corpus])
    ranked = hybrid_search.fuse([{'id': row['chunk_id'], 'score': float(row['similarity'])} for row in dense], keywords, 5)
    by_id = {row['chunk_id']: dict(row, similarity=None) for row in corpus}
    by_id.update({row['chunk_id']: row for row in dense})
    return [dict(by_id[hit['id']], retrieval=hit) for hit in ranked]

"""회사·생활 원문 → BGE-M3 1024차원·BM25 → RRF로 합친 범주별 RAG 근거."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import db, hybrid_search, llm, regulation_embeddings as embeddings

TABLE = 'app_ext.knowledge_chunk_vectors'
CATEGORIES = ('수자원공사 정보', '사내 생활안내')


def install_schema() -> None:
    """명시적인 사전 색인 작업에서만 스키마를 적용한다. 검색은 DDL을 실행하지 않는다."""
    sql = (Path(__file__).resolve().parents[1] / 'db/03_knowledge_bge.sql').read_text(encoding='utf-8')
    raw = db.engine.raw_connection()
    try:
        raw.cursor().execute(sql)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def source_chunks(category: str | None = None) -> list[dict]:
    if category is not None and category not in CATEGORIES:
        raise ValueError('등록되지 않은 자료 범주예요')
    return db.all_('''SELECT c.chunk_id,c.chunk_text,c.chunk_text_sha256,d.category
        FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        WHERE d.category=ANY(:categories) ORDER BY c.chunk_id''',
        categories=[category] if category else list(CATEGORIES))


def ensure_vectors(chunks: list[dict]) -> int:
    """원문 전체를 입력하고 입력 해시가 같은 행은 재사용한다. 배치별 저장으로 재개한다."""
    if not chunks:
        return 0
    for chunk in chunks:
        if hashlib.sha256(chunk['chunk_text'].encode('utf-8')).hexdigest() != chunk['chunk_text_sha256']:
            raise llm.LlmError('BGE-M3 색인: 자료 원문 해시가 달라요')
    stored = {row['chunk_id']: row for row in db.all_(f'''
        SELECT chunk_id,input_sha256,dimensions FROM {TABLE}
        WHERE embedding_model=:model AND chunk_id=ANY(:ids)''',
        model=embeddings.BGE_MODEL, ids=[chunk['chunk_id'] for chunk in chunks])}
    missing = [chunk for chunk in chunks if chunk['chunk_id'] not in stored
               or stored[chunk['chunk_id']]['input_sha256'] != chunk['chunk_text_sha256']
               or stored[chunk['chunk_id']]['dimensions'] != embeddings.BGE_DIMENSIONS]
    for offset in range(0, len(missing), 4):
        part = missing[offset:offset + 4]
        vectors = embeddings.validate(embeddings.embed([chunk['chunk_text'] for chunk in part]),
                                      len(part), embeddings.BGE_DIMENSIONS)
        with db.tx() as transaction:
            for chunk, vector in zip(part, vectors, strict=True):
                transaction.run(f'''INSERT INTO {TABLE}
                    (chunk_id,embedding_model,dimensions,input_sha256,embedding)
                    VALUES (:id,:model,:dims,:sha,CAST(:vector AS vector))
                    ON CONFLICT (chunk_id,embedding_model) DO UPDATE SET
                    dimensions=EXCLUDED.dimensions,input_sha256=EXCLUDED.input_sha256,
                    embedding=EXCLUDED.embedding,updated_at=now()''',
                    id=chunk['chunk_id'], model=embeddings.BGE_MODEL, dims=embeddings.BGE_DIMENSIONS,
                    sha=chunk['chunk_text_sha256'], vector=json.dumps(vector, allow_nan=False))
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
                  model=embeddings.BGE_MODEL, dims=embeddings.BGE_DIMENSIONS)
    counts = db.one(f'''SELECT count(*) AS total,count(v.chunk_id) AS indexed
        FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        LEFT JOIN {TABLE} v ON v.chunk_id=c.chunk_id AND v.embedding_model=:model
            AND v.dimensions=:dims AND v.input_sha256=c.chunk_text_sha256
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

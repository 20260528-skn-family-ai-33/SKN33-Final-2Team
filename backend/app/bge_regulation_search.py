"""별도 BGE-M3 규정 색인과 BM25·RRF 검색. 기존 OpenAI 벡터는 보존한다."""
from __future__ import annotations

import hashlib

from . import db, hybrid_search, llm, regulation_embeddings as embeddings, regstore

TABLE = 'regulations.rag_chunk_embeddings'
META_TABLE = 'growpath_bge_meta.inputs'
INPUT_VERSION = 'context_path+blank_line+chunk_text/v1'
PROTOCOL = 'bge-m3/cls-l2-fp16/v1'


def input_text(article: dict) -> str:
    """기존 조·항 청크의 문맥과 본문 전체를 넣는다. 6,000자 절단은 적용하지 않는다."""
    return (article['path'] + '\n\n' + article['chunkText']).replace('\x00', '')


def _inputs(ids: list[str]) -> dict[str, tuple[str, str]]:
    texts = {i: input_text(regstore.article(i)) for i in ids}
    return {i: (text, hashlib.sha256(text.encode('utf-8')).hexdigest()) for i, text in texts.items()}


def _stored(ids: list[str]) -> dict[str, dict]:
    rows = db.all_(f'''SELECT e.rag_chunk_id,e.dimensions,e.input_sha256,e.input_version,
            p.source_sha256 AS meta_sha256, p.actual_input_sha256, p.model_revision
        FROM {TABLE} e
        LEFT JOIN {META_TABLE} p ON p.kind='regulations' AND p.source_id=e.rag_chunk_id
        WHERE e.embedding_model=:m AND e.rag_chunk_id=ANY(:i)''', m=embeddings.BGE_MODEL, i=ids)
    return {row['rag_chunk_id']: row for row in rows}


def _missing(inputs: dict, stored: dict) -> list[str]:
    from .bge_model import REVISION
    missing = []
    for i, (_, sha) in inputs.items():
        if i not in stored:
            missing.append(i)
            continue
        row = stored[i]
        if (row['dimensions'] != embeddings.BGE_DIMENSIONS
                or row['input_sha256'] != sha
                or row.get('input_version') != INPUT_VERSION):
            missing.append(i)
            continue
        if ('meta_sha256' in row and (row['meta_sha256'] != sha
                or row.get('actual_input_sha256') != sha
                or row.get('model_revision') != REVISION)):
            missing.append(i)
            continue
    return missing


def ensure_vectors(ids: list[str]) -> int:
    """규정 원문 → 새 BGE dense 벡터 → 별도 모델 행. 같은 입력은 재사용하고 변경 입력만 갱신한다."""
    inputs = _inputs(ids)
    missing = _missing(inputs, _stored(ids))
    for offset in range(0, len(missing), 4):
        part = missing[offset:offset + 4]
        vectors = embeddings.validate(embeddings.embed([inputs[i][0] for i in part]), len(part), embeddings.BGE_DIMENSIONS)
        with db.tx() as transaction:
            current_rows = transaction.all('''
                SELECT rag_chunk_id, encode(sha256(convert_to(context_path || chr(10) || chr(10) || chunk_text, 'UTF8')), 'hex') AS current_sha
                FROM regulations.rag_chunks WHERE rag_chunk_id = ANY(:ids)''', ids=part)
            current_shas = {r['rag_chunk_id']: r['current_sha'] for r in current_rows}
            if current_shas and any(current_shas.get(aid) != inputs[aid][1] for aid in part if aid in current_shas):
                raise llm.LlmError('BGE-M3 색인: 색인 중 규정 원문이 바뀌었어요. 다시 확인해 주세요')
            for aid, vector in zip(part, vectors, strict=True):
                transaction.run(f'''INSERT INTO {META_TABLE}
                    (kind,source_id,source_sha256,actual_input_sha256,protocol,model_revision,token_count,created_at)
                    VALUES ('regulations',:i,:s,:s,:proto,:rev,:tokens,now())
                    ON CONFLICT (kind,source_id) DO UPDATE SET
                    source_sha256=EXCLUDED.source_sha256,
                    actual_input_sha256=EXCLUDED.actual_input_sha256,
                    protocol=EXCLUDED.protocol,
                    model_revision=EXCLUDED.model_revision,
                    token_count=EXCLUDED.token_count,
                    created_at=EXCLUDED.created_at''',
                    i=aid, s=inputs[aid][1], proto=PROTOCOL,
                    rev=embeddings.PROVENANCE['model_revision'],
                    tokens=max(1, min(len(inputs[aid][0].split()), 8192)))
                transaction.run(f'''INSERT INTO {TABLE}
                    (rag_chunk_id,embedding_model,dimensions,embedding,input_sha256,input_version)
                    VALUES (:i,:m,:d,CAST(:v AS vector),:s,:iv)
                    ON CONFLICT (rag_chunk_id,embedding_model) DO UPDATE SET
                    dimensions=EXCLUDED.dimensions,embedding=EXCLUDED.embedding,
                    input_sha256=EXCLUDED.input_sha256,input_version=EXCLUDED.input_version,updated_at=now()''',
                    i=aid, m=embeddings.BGE_MODEL, d=embeddings.BGE_DIMENSIONS,
                    v=regstore._vec(vector), s=inputs[aid][1], iv=INPUT_VERSION)
    return len(missing)


def search(query: str, k: int, group: str | None, *, all_groups: bool = False) -> list[dict]:
    """직원 구분·국외 필터 안의 BGE+BM25 검색. 검색 중에는 DB를 쓰지 않는다."""
    if k < 1:
        raise ValueError('검색 개수는 1 이상이어야 해요')
    hybrid = hybrid_search.enabled()
    ids = [article['id'] for article in regstore.pool(group, query, all_groups=all_groups)]
    if not ids:
        return []
    inputs = _inputs(ids)
    if _missing(inputs, _stored(ids)):
        raise llm.LlmError('BGE-M3 색인이 없거나 원문과 달라요. index_regulations.py --apply를 먼저 실행해 주세요')
    vector = embeddings.validate(embeddings.embed([query]), 1, embeddings.BGE_DIMENSIONS)[0]
    rows = db.all_(f'''SELECT rag_chunk_id,1-(embedding <=> CAST(:q AS vector)) AS score FROM {TABLE}
        WHERE embedding_model=:m AND dimensions=:d AND input_version=:iv AND rag_chunk_id=ANY(:i)
        ORDER BY embedding <=> CAST(:q AS vector),rag_chunk_id LIMIT :k''',
        q=regstore._vec(vector), m=embeddings.BGE_MODEL, d=embeddings.BGE_DIMENSIONS, iv=INPUT_VERSION, i=ids,
        k=max(k, hybrid_search.CANDIDATES) if hybrid else k)
    dense = [{'id': row['rag_chunk_id'], 'score': float(row['score'])} for row in rows]
    if not hybrid:
        return [{'id': hit['id'], 'score': round(hit['score'], 4)} for hit in dense]
    keywords = hybrid_search.bm25(query, [(identifier, text) for identifier, (text, _) in inputs.items()], max(k, hybrid_search.CANDIDATES))
    fused = hybrid_search.fuse(dense, keywords, len(dense) + len(keywords) or k)
    # 조 번호는 의미 순위와 별개인 구조화 조회다. 본문에서 같은 번호를 인용한 다른 조보다 우선한다.
    reference = regstore.explicit_ref(query, group, all_groups=all_groups) if regstore.REF_ART.search(query) else None
    exact = [identifier for identifier in (reference or {}).get('ids', []) if identifier in inputs]
    if exact:
        by_id = {hit['id']: hit for hit in fused}
        pinned = [dict(by_id.get(identifier) or {'id': identifier, 'rrfScore': 0.0,
            'vectorRank': None, 'bm25Rank': None, 'vectorScore': None, 'bm25Score': None}, exactReference=True)
            for identifier in exact]
        fused = pinned + [hit for hit in fused if hit['id'] not in exact]
    # 긴 조가 항 수만큼 상위 결과를 차지하지 않도록 같은 부모의 가장 높은 순위를 대표로 쓴다.
    seen, result = set(), []
    for hit in fused:
        article = regstore.article(hit['id'])
        parent = article.get('parent') or article.get('node') or article['id']
        key = (article['reg'], parent)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(hit, score=hit['rrfScore'], parentId=parent))
        if len(result) == k:
            break
    return result

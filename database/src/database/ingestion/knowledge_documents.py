"""Verbatim non-regulation evidence with mandatory category-scoped retrieval."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from psycopg.types.json import Jsonb
from src.database.vectors.regulation_vectors import MODEL, DIMENSIONS, embed_texts, vector_values

CATEGORIES = ('수자원공사 정보', '사내 생활안내')
FILES = {'company_info_chunks.jsonl': (137, CATEGORIES[0]),
         'workplace_guide_chunks.jsonl': (305, CATEGORIES[1])}
CORE = {'chunk_id', 'category', 'document_id', 'document_title', 'document_kind',
        'display_order', 'chunk_text', 'chunk_text_sha256', 'is_virtual'}


def load_files(paths: list[Path]) -> tuple[list[dict], list[dict]]:
    if not 1 <= len(paths) <= 2 or len({p.name for p in paths}) != len(paths):
        raise ValueError('회사 정보·생활안내 파일을 각각 한 번만 지정하세요.')
    rows, manifests = [], []
    for path in paths:
        if path.name not in FILES:
            raise ValueError('지원하는 투입 파일 이름이 아닙니다.')
        data = path.read_bytes()
        items = [json.loads(line) for line in data.decode('utf-8').splitlines() if line.strip()]
        count, category = FILES[path.name]
        if len(items) != count or any(row.get('category') != category for row in items):
            raise ValueError('투입 파일의 예상 조각 수·범주가 일치하지 않습니다.')
        manifests.append({'file': path.name, 'sha256': hashlib.sha256(data).hexdigest(), 'rows': len(items)})
        rows.extend(items)
    validate_rows(rows)
    return rows, manifests


def validate_rows(rows: list[dict]) -> None:
    if not rows or len(rows) > 442:
        raise ValueError('이번 투입은 최대 442조각입니다.')
    ids, orders, documents = set(), set(), {}
    for row in rows:
        if not isinstance(row, dict) or not CORE <= row.keys():
            raise ValueError('필수 조각 항목이 없습니다.')
        if any(not isinstance(row[k], str) or not row[k].strip() for k in CORE - {'display_order', 'is_virtual'}):
            raise ValueError('필수 문자열이 비어 있습니다.')
        if row['category'] not in CATEGORIES or row['document_kind'] not in ('report', 'plan', 'web_page', 'guide'):
            raise ValueError('지원하지 않는 문서 범주·종류입니다.')
        if type(row['is_virtual']) is not bool or type(row['display_order']) is not int or row['display_order'] < 1:
            raise ValueError('가상 여부·문서 내 순서가 올바르지 않습니다.')
        if hashlib.sha256(row['chunk_text'].encode('utf-8')).hexdigest() != row['chunk_text_sha256']:
            raise ValueError('원문 SHA-256이 일치하지 않습니다.')
        if len(row['chunk_text'].encode('utf-8')) > 8000:
            raise ValueError('본문이 임베딩 입력 상한을 넘었습니다. 자르지 않고 중단합니다.')
        rid, order = row['chunk_id'], (row['document_id'], row['display_order'])
        if rid in ids or order in orders:
            raise ValueError('조각 ID·문서 내 순서가 중복됩니다.')
        ids.add(rid)
        orders.add(order)
        info = (row['category'], row['document_title'], row['document_kind'])
        if row['document_id'] in documents and documents[row['document_id']] != info:
            raise ValueError('같은 문서의 범주·제목·종류가 다릅니다.')
        documents[row['document_id']] = info
        json.dumps(row, ensure_ascii=False, allow_nan=False)


def reconstruct(row: dict) -> dict:
    return {**row['metadata'], **{key: row[key] for key in CORE}}


SOURCE_SQL = '''SELECT c.*,d.category,d.title AS document_title,d.document_kind
    FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)'''


def prepare(conn, rows: list[dict]) -> list[dict]:
    """Idempotent identical inputs; reject changed IDs before any paid call/write."""
    validate_rows(rows)
    if not conn.execute("SELECT to_regclass('knowledge.chunks') AS id").fetchone()['id']:
        return rows
    old = {row['chunk_id']: row for row in conn.execute(SOURCE_SQL).fetchall()}
    docs = {r['document_id']: (r['category'], r['title'], r['document_kind'])
            for r in conn.execute('SELECT * FROM knowledge.documents').fetchall()}
    pending = []
    for row in rows:
        info = (row['category'], row['document_title'], row['document_kind'])
        if row['document_id'] in docs and docs[row['document_id']] != info:
            raise ValueError('기존 문서 정의와 다릅니다. 덮어쓰지 않습니다.')
        previous = old.get(row['chunk_id'])
        if previous is not None and reconstruct(previous) != row:
            raise ValueError('기존 조각과 본문·출처가 다릅니다. 덮어쓰지 않습니다.')
        if previous is None or previous['embedding'] is None:
            pending.append(row)
        elif previous['embedding_model'] != MODEL or previous['input_sha256'] != row['chunk_text_sha256']:
            raise ValueError('기존 벡터의 모델·본문 해시가 다릅니다.')
    return pending


def insert(conn, rows: list[dict], *, client=None) -> dict:
    """Outer transaction owns all writes; failures roll back the whole batch."""
    conn.execute('SELECT pg_advisory_xact_lock(763250132)')
    conn.execute('LOCK TABLE knowledge.documents,knowledge.chunks IN SHARE ROW EXCLUSIVE MODE')
    pending = prepare(conn, rows)
    saved = 0
    for start in range(0, len(pending), 16):
        batch = pending[start:start + 16]
        # Exact supplied chunk_text only. No title prefix, truncation or rechunking.
        vectors = embed_texts([row['chunk_text'] for row in batch], client=client)
        for row, vector in zip(batch, vectors):
            conn.execute('''INSERT INTO knowledge.documents(document_id,category,title,document_kind)
                VALUES (%s,%s,%s,%s) ON CONFLICT(document_id) DO NOTHING''',
                         (row['document_id'], row['category'], row['document_title'], row['document_kind']))
            conn.execute('''INSERT INTO knowledge.chunks
                (chunk_id,document_id,display_order,chunk_text,chunk_text_sha256,is_virtual,metadata,
                 embedding_model,dimensions,input_sha256,embedding,embedded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,now())
                ON CONFLICT(chunk_id) DO UPDATE SET embedding_model=EXCLUDED.embedding_model,
                    dimensions=EXCLUDED.dimensions,input_sha256=EXCLUDED.input_sha256,
                    embedding=EXCLUDED.embedding,embedded_at=EXCLUDED.embedded_at''',
                         (row['chunk_id'], row['document_id'], row['display_order'], row['chunk_text'],
                          row['chunk_text_sha256'], row['is_virtual'], Jsonb({k: v for k, v in row.items() if k not in CORE}),
                          MODEL, DIMENSIONS, row['chunk_text_sha256'], json.dumps(vector)))
            saved += 1
        print(f'Embedded document chunks {saved}/{len(pending)}', flush=True)
    expected = {row['chunk_id']: row for row in rows}
    actual = conn.execute(SOURCE_SQL + ' WHERE c.chunk_id=ANY(%s)', (list(expected),)).fetchall()
    if len(actual) != len(rows) or any(reconstruct(row) != expected[row['chunk_id']] for row in actual):
        raise ValueError('적재 후 원문·출처 대조 실패: 전체 롤백합니다.')
    return {'verified_chunks': len(actual), 'embedded_chunks': saved, 'unchanged_chunks': len(rows) - saved,
            'categories': dict(Counter(r['category'] for r in rows)), 'embedding_model': MODEL, 'dimensions': DIMENSIONS}


def search_vector(conn, query_vector: list[float], *, category: str, limit: int = 5, threshold: float = 0.25) -> list[dict]:
    """Category is mandatory; virtual/source/training metadata always accompanies text."""
    if category not in CATEGORIES or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('검색 범주·결과 수를 확인하세요.')
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError('유사도 임계값이 올바르지 않습니다.')
    vector = json.dumps(vector_values(query_vector), allow_nan=False)
    conn.execute('SET LOCAL search_path TO public, extensions')
    return conn.execute('''WITH candidates AS MATERIALIZED (
        SELECT c.chunk_id,c.chunk_text,c.is_virtual,c.metadata,c.display_order,d.document_id,
            d.category,d.title AS document_title,1-(c.embedding <=> %s::vector) AS similarity
        FROM knowledge.chunks c JOIN knowledge.documents d USING(document_id)
        WHERE d.category=%s AND c.embedding_model=%s AND c.dimensions=%s
            AND c.input_sha256=c.chunk_text_sha256 AND c.embedding IS NOT NULL)
        SELECT * FROM candidates WHERE similarity >= %s ORDER BY similarity DESC,chunk_id LIMIT %s''',
                        (vector, category, MODEL, DIMENSIONS, threshold, limit)).fetchall()


def search(conn, query: str, *, category: str, limit: int = 5, threshold: float = 0.25, client=None) -> list[dict]:
    # Validate query/category/bounds before a paid request.
    if category not in CATEGORIES or type(limit) is not int or not 1 <= limit <= 50 or not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError('검색 범주·결과 수·유사도를 확인하세요.')
    from .knowledge_search import hybrid_search_vector
    return hybrid_search_vector(conn, embed_texts([query], client=client)[0], query=query,
                                category=category, limit=limit, threshold=threshold)

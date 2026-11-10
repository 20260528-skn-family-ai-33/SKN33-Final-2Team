"""BGE 입력 검증 기록(growpath_bge_meta.inputs)의 저장과 판정. 저장은 벡터와 같은 트랜잭션에서만 한다."""
from src.shared.bge_embeddings import ACCEPTED_PROTOCOLS, MAX_TOKENS, PROVENANCE

META_TABLE = 'growpath_bge_meta.inputs'
_UPSERT = f'''INSERT INTO {META_TABLE}
    (kind,source_id,source_sha256,actual_input_sha256,protocol,model_revision,token_count,created_at)
    VALUES (%s,%s,%s,%s,%s,%s,%s,now())
    ON CONFLICT (kind,source_id) DO UPDATE SET
    source_sha256=EXCLUDED.source_sha256,
    actual_input_sha256=EXCLUDED.actual_input_sha256,
    protocol=EXCLUDED.protocol,
    model_revision=EXCLUDED.model_revision,
    token_count=EXCLUDED.token_count,
    created_at=EXCLUDED.created_at'''


def require_table(conn) -> None:
    """검증 기록이 없는 DB는 미복원·손상 상태다. 빈 표를 만들어 가리지 않고 쓰기 전에 거절한다."""
    if not conn.execute('SELECT to_regclass(%s) AS id', (META_TABLE,)).fetchone()['id']:
        raise ValueError('Restore the shared BGE-M3 database with growpath_bge_meta.inputs first.')


def save(conn, kind: str, source_id: str, source_sha256: str, actual_input_sha256: str,
         protocol: str, token_count: int) -> None:
    conn.execute(_UPSERT, (kind, str(source_id), source_sha256, actual_input_sha256, protocol,
                           PROVENANCE['model_revision'], token_count))


def is_current(row, source_sha256: str, actual_input_sha256: str) -> bool:
    """공유 백업의 FP16 기록과 새 FP32 기록을 모두 인정해 기존 벡터를 일괄 재생성하지 않는다."""
    return (bool(row) and row.get('meta_sha256') == source_sha256
            and row.get('actual_input_sha256') == actual_input_sha256
            and row.get('model_revision') == PROVENANCE['model_revision']
            and row.get('protocol') in ACCEPTED_PROTOCOLS
            and 1 <= (row.get('token_count') or 0) <= MAX_TOKENS)

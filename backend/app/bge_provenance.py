"""BGE 입력 검증 기록(growpath_bge_meta.inputs)의 저장과 판정. 저장은 벡터와 같은 트랜잭션에서만 한다."""
from __future__ import annotations

from .bge_model import ACCEPTED_PROTOCOLS, MAX_TOKENS, REVISION

META_TABLE = 'growpath_bge_meta.inputs'
_UPSERT = f'''INSERT INTO {META_TABLE}
    (kind,source_id,source_sha256,actual_input_sha256,protocol,model_revision,token_count,created_at)
    VALUES (:kind,:source_id,:source_sha256,:actual_input_sha256,:protocol,:model_revision,:token_count,now())
    ON CONFLICT (kind,source_id) DO UPDATE SET
    source_sha256=EXCLUDED.source_sha256,
    actual_input_sha256=EXCLUDED.actual_input_sha256,
    protocol=EXCLUDED.protocol,
    model_revision=EXCLUDED.model_revision,
    token_count=EXCLUDED.token_count,
    created_at=EXCLUDED.created_at'''


def save_input(transaction, kind: str, source_id: str, source_sha256: str, actual_input_sha256: str, embedded) -> None:
    """embedded는 서버가 보고한 protocol·token_count를 가진 IndexedEmbedding이다."""
    transaction.run(_UPSERT, kind=kind, source_id=str(source_id), source_sha256=source_sha256,
                    actual_input_sha256=actual_input_sha256, protocol=embedded.protocol,
                    model_revision=REVISION, token_count=embedded.token_count)


def is_current(row: dict | None, source_sha256: str, actual_input_sha256: str) -> bool:
    """공유 백업의 FP16 기록과 새 FP32 기록을 모두 인정해 기존 벡터를 일괄 재생성하지 않는다."""
    return (row is not None and row.get('meta_sha256') == source_sha256
            and row.get('actual_input_sha256') == actual_input_sha256
            and row.get('model_revision') == REVISION
            and row.get('protocol') in ACCEPTED_PROTOCOLS
            and 1 <= (row.get('token_count') or 0) <= MAX_TOKENS)

"""Default is read-only preparation. --apply requires finite embedding authorization."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.database.deployment import connect, migrate
from src.database.ingestion.knowledge_documents import load_files, prepare, insert
from src.database.local_runtime import DATA, server_data_directory
from src.database.portable import backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, nargs='+', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    rows, files = load_files(args.input)
    with connect('SUPABASE_DB_URL') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if (conn.info.host, conn.info.port, conn.info.dbname) != ('127.0.0.1', 55435, 'growpath') or server_data_directory(conn).resolve() != DATA.resolve():
            raise ValueError('최종 작업 DB만 지원합니다.')
        pending = prepare(conn, rows)
    summary = {'input_files': files, 'chunks': len(rows), 'documents': len({r['document_id'] for r in rows}),
               'pending_embeddings': len(pending), 'paid_api_calls': 0, 'database_changes': False}
    if not args.apply or not pending:
        print(json.dumps({'status': 'prepared' if pending else 'already_applied', **summary}, ensure_ascii=False, indent=2))
        return 0
    path = ROOT / 'data/exports' / ('before_knowledge_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8] + '.dump')
    backup(path)
    # Source files may be finishing in another task; stop if they changed after preparation.
    if any(hashlib.sha256(p.read_bytes()).hexdigest() != f['sha256'] for p, f in zip(args.input, files)):
        raise ValueError('검사 후 원본 파일이 변경되었습니다. 다시 준비하세요.')
    with connect('SUPABASE_DB_URL') as conn:
        migration = migrate(conn)
        result = insert(conn, rows)
    print(json.dumps({'status': 'applied', 'backup': str(path.relative_to(ROOT)), 'input_files': files,
                      'migration_applied': migration['applied'], 'database_changes': True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Avoid dumping credentials/provider error bodies.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__,
                          'message': str(exc) if isinstance(exc, ValueError) else '적재 실패: DB 쓰기는 롤백됩니다. 연결·API 상태를 확인하세요.'}, ensure_ascii=False))
        raise SystemExit(1)

"""Normalize stored public outlines; read-only plan unless --apply is supplied."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.course_curriculum import backfill


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db-env', default='SUPABASE_DB_URL')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--outline-manifest', type=Path, help='Optional hash-verified public-page cache manifest')
    args = parser.parse_args()
    with connect(args.db_env) as conn:
        if not args.apply:
            conn.execute('SET TRANSACTION READ ONLY')
        supplements = json.loads(args.outline_manifest.read_text(encoding='utf-8')) if args.outline_manifest else None
        print(json.dumps(backfill(conn, apply=args.apply, supplements=supplements), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

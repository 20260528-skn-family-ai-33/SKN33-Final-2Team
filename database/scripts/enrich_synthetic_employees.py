"""Prepare an external fictional profile plan, or explicitly apply its reviewed hash."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.database.deployment import connect
from src.database.synthetic_employee_profiles import plan, apply_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path, help='Create an external review plan; no DB writes')
    group.add_argument('--plan', type=Path, help='Read an existing reviewed plan')
    parser.add_argument('--as-of', type=date.fromisoformat)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--sha256', help='Required file hash for --apply')
    args = parser.parse_args()
    if args.output and (args.apply or not args.as_of):
        parser.error('--output requires --as-of and cannot use --apply')
    if args.apply and not args.sha256:
        parser.error('--apply requires --sha256')
    with connect('SUPABASE_DB_URL') as conn:
        if args.output:
            if args.output.exists():
                parser.error('Output exists; preserve the reviewed artifact')
            reviewed = plan(conn, as_of=args.as_of)
            data = (json.dumps(reviewed, ensure_ascii=False, indent=2, default=str) + '\n').encode('utf-8')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            print(json.dumps({'employees': len(reviewed['entries']), 'sha256': hashlib.sha256(data).hexdigest(), 'database_writes': False}))
        else:
            data = args.plan.read_bytes()
            if args.sha256 and hashlib.sha256(data).hexdigest() != args.sha256:
                parser.error('Reviewed plan hash mismatch')
            print(json.dumps(apply_plan(conn, json.loads(data), apply=args.apply)))


if __name__ == '__main__':
    main()

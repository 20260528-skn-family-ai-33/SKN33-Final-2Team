"""Trusted operator JSON import. Preview rolls back; --apply persists atomically."""
import argparse
import json
from pathlib import Path
import sys
from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.employee_form import validate_form_payload, save_employee_input_form
from src.database.db_client import user_id_value


def import_forms(conn, records: list[dict], *, apply: bool = False) -> dict:
    if not isinstance(records, list) or not records:
        raise ValueError('Supply a nonempty records array')
    clean = []
    for record in records:
        if not isinstance(record, dict) or 'employee_id' not in record:
            raise ValueError('Each record must identify an existing employee_id')
        identity = user_id_value(record['employee_id'])
        payload = {k: v for k, v in record.items() if k != 'employee_id'}
        validate_form_payload(payload)
        clean.append((identity, payload))
    if len({identity for identity, _ in clean}) != len(clean):
        raise ValueError('Duplicate employees in one import')
    with conn.transaction(force_rollback=not apply):
        for identity, payload in clean:
            save_employee_input_form(conn, identity, payload)
    return {'status': 'APPLIED' if apply else 'PREVIEW_ROLLED_BACK',
            'employees_checked': len(clean), 'database_changes': apply,
            'api_called': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='UTF-8 JSON array; private employee values stay outside Git')
    parser.add_argument('--db-env', default='SUPABASE_DB_URL')
    parser.add_argument('--connection-file', type=Path, help='Optional private dotenv file containing the selected --db-env key')
    parser.add_argument('--apply', action='store_true', help='Commit the complete batch; default previews with rollback')
    args = parser.parse_args(argv)
    try:
        records = json.loads(args.input.read_text(encoding='utf-8-sig'))
        if args.connection_file:
            url = dotenv_values(args.connection_file).get(args.db_env)
            if not url:
                raise ValueError('Selected DB key is missing from the private connection file')
            connection = psycopg.connect(url, row_factory=dict_row)
        else:
            connection = connect(args.db_env)
        with connection as conn:
            result = import_forms(conn, records, apply=args.apply)
    except Exception as exc:
        result = {'status': 'FAILED', 'error_type': type(exc).__name__,
                  'message': str(exc) if isinstance(exc, ValueError) else 'Form import failed and rolled back; check schema, foreign keys and connection.'}
        print(json.dumps(result, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

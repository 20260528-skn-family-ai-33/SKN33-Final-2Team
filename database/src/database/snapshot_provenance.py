"""Verify recorded snapshot migrations without inventing their unavailable SQL."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'config/snapshot_migrations.json'


def verify_snapshot_history(conn):
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    applied = {row['version']: row['sha256'] for row in conn.execute(
        'SELECT version,sha256 FROM growpath_meta.schema_migrations'
    ).fetchall()}
    external = []
    for entry in manifest['applied_snapshot_migrations']:
        version = entry['version']
        if applied.get(version) != entry['sha256']:
            raise ValueError('Restore the verified source/latest snapshot; migration history mismatch: ' + version)
        source = ROOT / 'src/database/migrations' / version
        if entry['sql_file_available']:
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Historical SQL changed: ' + version)
        else:
            external.append(version)
    return {'verified_snapshot_migrations': len(manifest['applied_snapshot_migrations']),
            'snapshot_only_migrations': external,
            'original_sql_availability': '001-012 available; 013-020 preserved by snapshot and recorded checksum'}


def deferred_employee_number_constraint(conn):
    """Report the incoming, intentionally NOT VALID check; never silently waive others."""
    rows = conn.execute('''
        SELECT n.nspname AS schema_name,t.relname AS table_name,c.conname,
               pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE NOT c.convalidated AND n.nspname IN
            ('public','regulations','growpath_meta','growpath_legacy','knowledge')
        ORDER BY n.nspname,t.relname,c.conname
    ''').fetchall()
    warnings = []
    for row in rows:
        expected = (row['schema_name'], row['table_name'], row['conname']) == (
            'public', 'employees', 'employees_number_required')
        normalized = ''.join(row['definition'].split())
        signature = "CHECK(((employee_numberISNOTNULL)AND(employee_number!~'^[[:space:]]*$'::text)))NOTVALID"
        if not expected or normalized != signature:
            raise ValueError('Unexpected unvalidated DB constraint: ' + row['conname'])
        counts = conn.execute('''SELECT source_type,count(*) AS n FROM public.employees
            WHERE employee_number IS NULL OR employee_number ~ '^[[:space:]]*$'
            GROUP BY source_type ORDER BY source_type''').fetchall()
        warnings.append({'constraint':row['conname'], 'validation':'deferred_from_source_snapshot',
                         'existing_rows_missing_employee_number':sum(r['n'] for r in counts),
                         'missing_by_source':[dict(r) for r in counts],
                         'action':'Enter the actual employee number before updating incomplete accounts; then VALIDATE CONSTRAINT. No numbers were invented.'})
    return warnings

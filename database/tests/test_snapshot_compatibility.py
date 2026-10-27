"""Snapshot history and deferred-number checks must fail closed on unrelated drift."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.database import snapshot_provenance as provenance


class Cursor:
    def __init__(self,rows):self.rows=rows
    def fetchall(self):return self.rows


class Connection:
    def __init__(self,history=None,constraints=None,missing=None):
        self.history=history or []
        self.constraints=constraints or []
        self.missing=missing or []
        self.statements=[]
    def execute(self,statement,params=None):
        self.statements.append(statement)
        if 'schema_migrations' in statement:return Cursor(self.history)
        if 'pg_constraint' in statement:return Cursor(self.constraints)
        if 'GROUP BY source_type' in statement:return Cursor(self.missing)
        raise AssertionError('Unexpected SQL')


class SnapshotCompatibilityTests(unittest.TestCase):
    def manifest(self,directory):
        root=Path(directory)
        target=root/'src/database/migrations'
        target.mkdir(parents=True)
        body=b'-- preserved historical migration\nSELECT 1;\n'
        (target/'001_foundation.sql').write_bytes(body)
        entries=[{'version':'001_foundation.sql','sha256':hashlib.sha256(body).hexdigest(),'sql_file_available':True},
                 {'version':'013_external.sql','sha256':'a'*64,'sql_file_available':False}]
        manifest=root/'snapshot.json'
        manifest.write_text(json.dumps({'applied_snapshot_migrations':entries}),encoding='utf-8')
        return root,manifest,entries

    def test_snapshot_only_history_is_verified_without_fake_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            root,manifest,entries=self.manifest(directory)
            conn=Connection(history=entries)
            with patch.object(provenance,'ROOT',root),patch.object(provenance,'MANIFEST',manifest):
                result=provenance.verify_snapshot_history(conn)
            self.assertEqual(result['snapshot_only_migrations'],['013_external.sql'])
            self.assertFalse((root/'src/database/migrations/013_external.sql').exists())
            self.assertTrue(all(s.lstrip().startswith('SELECT') for s in conn.statements))

    def test_missing_or_forged_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root,manifest,entries=self.manifest(directory)
            for history in (entries[:1],[entries[0],{**entries[1],'sha256':'b'*64}]):
                with patch.object(provenance,'ROOT',root),patch.object(provenance,'MANIFEST',manifest):
                    with self.assertRaisesRegex(ValueError,'migration history mismatch'):
                        provenance.verify_snapshot_history(Connection(history=history))

    def test_applied_local_sql_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root,manifest,entries=self.manifest(directory)
            (root/'src/database/migrations/001_foundation.sql').write_text('SELECT 2;',encoding='utf-8')
            with patch.object(provenance,'ROOT',root),patch.object(provenance,'MANIFEST',manifest):
                with self.assertRaisesRegex(ValueError,'Historical SQL changed'):
                    provenance.verify_snapshot_history(Connection(history=entries))

    def deferred(self):
        return {'schema_name':'public','table_name':'employees','conname':'employees_number_required',
                'definition':"CHECK (((employee_number IS NOT NULL) AND (employee_number !~ '^[[:space:]]*$'::text))) NOT VALID"}

    def test_exact_incoming_check_is_reported_with_its_violations(self):
        conn=Connection(constraints=[self.deferred()],missing=[{'source_type':'REAL_USER','n':5}])
        result=provenance.deferred_employee_number_constraint(conn)
        self.assertEqual(result[0]['existing_rows_missing_employee_number'],5)
        self.assertEqual(result[0]['validation'],'deferred_from_source_snapshot')
        self.assertTrue(all(s.lstrip().startswith('SELECT') for s in conn.statements))

    def test_unrelated_or_weakened_unvalidated_constraint_is_not_waived(self):
        for changed in ({'conname':'another_constraint'},{'definition':'CHECK (true) NOT VALID'},{'table_name':'another_table'}):
            with self.subTest(changed=changed),self.assertRaisesRegex(ValueError,'Unexpected unvalidated'):
                provenance.deferred_employee_number_constraint(Connection(constraints=[{**self.deferred(),**changed}]))


if __name__=='__main__':unittest.main()

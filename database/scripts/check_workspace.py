"""Offline regression checks; --integration uses a disposable clone, never HR writes in growpath."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run_tests(names,log_path):
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    collected=suite.countTestCases()
    with log_path.open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    return {'collected':collected,'started_including_skips':result.testsRun,'executed':result.testsRun-len(result.skipped),
            'passed':result.testsRun-len(result.skipped)-len(result.failures)-len(result.errors),
            'skipped':len(result.skipped),'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful()}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integration',action='store_true')
    parser.add_argument('--app-contracts',action='store_true',help='Include authenticated reference API contracts; install backend requirements first')
    args=parser.parse_args(argv)
    if args.app_contracts and not args.integration:
        parser.error('--app-contracts requires --integration')
    out=ROOT/'migration_work';out.mkdir(exist_ok=True)
    scratch=out/'test_tmp';scratch.mkdir(exist_ok=True);tempfile.tempdir=str(scratch)
    unit_names=['tests.test_import_package','tests.test_db_deployment','tests.test_catalog_expansion','tests.test_regulation_vectors',
                'tests.test_ai_catalog_filter','tests.test_catalog_scope','tests.test_employee_form',
                'tests.test_local_runtime','tests.test_snapshot_compatibility','tests.test_course_supplement',
                'tests.test_knowledge_documents','tests.test_knowledge_search','tests.test_course_sources',
                'tests.test_instructional_content','tests.test_ingestion_execution','tests.test_resource_refresh',
                'tests.test_synthetic_employee_profiles']
    with patch.dict(os.environ,{'EMPLOYEE_FORM_TEST_DB_URL':''}):
        unit=run_tests(unit_names,out/'unit_tests.log')
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'unit':unit,'paid_api_calls':0}
    if args.integration and unit['successful']:
        from dotenv import dotenv_values
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict,make_conninfo
        from psycopg.rows import dict_row
        from src.database.local_runtime import server_data_directory,DATA
        params=conninfo_to_dict(dotenv_values(ROOT/'.env.local')['SUPABASE_DB_URL'])
        if params.get('host')!='127.0.0.1' or params.get('dbname')!='growpath':
            raise ValueError('Only the local final growpath database is supported')
        with psycopg.connect(**params,row_factory=dict_row) as conn:
            if server_data_directory(conn).resolve()!=DATA.resolve():
                raise ValueError('Application points at another cluster')
        clone='growpath_employee_form_test_20261026_'+uuid4().hex[:8]
        admin_params={**params,'dbname':'postgres'}
        with psycopg.connect(**admin_params,autocommit=True) as admin:
            if admin.execute('SELECT 1 FROM pg_database WHERE datname=%s',(clone,)).fetchone():raise ValueError('Test database already exists')
            admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(clone),sql.Identifier(params['dbname'])))
        test_url=make_conninfo(**{**params,'dbname':clone})
        try:
            if args.app_contracts:
                with psycopg.connect(test_url) as conn:
                    conn.execute((ROOT.parent/'backend/db/02_app_ext.sql').read_text(encoding='utf-8'))
            import tests.test_canonical_database as canonical
            def isolated_connect(_):return psycopg.connect(test_url,row_factory=dict_row)
            with patch.dict(os.environ,{'EMPLOYEE_FORM_TEST_DB_URL':test_url}),patch.object(canonical,'connect',side_effect=isolated_connect):
                names=['tests.test_synthetic_employee_database','tests.test_employee_form.EmployeeFormDatabaseTests','tests.test_canonical_database','tests.test_final_database','tests.test_catalog_history','tests.test_department_access','tests.test_resource_refresh_database']
                if args.app_contracts:names.append('tests.test_app_contracts')
                report['integration']=run_tests(names,out/'integration_tests.log')
        finally:
            with psycopg.connect(**admin_params,autocommit=True) as admin:
                if not clone.startswith('growpath_employee_form_test_20261026_'):raise ValueError('Unexpected cleanup target')
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(clone)))
            report['test_clone_removed']=True
    (out/'test_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if unit['successful'] and report.get('integration',{'successful':True})['successful'] else 1


if __name__=='__main__':raise SystemExit(main())

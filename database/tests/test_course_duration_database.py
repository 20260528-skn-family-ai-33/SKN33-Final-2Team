"""Real PostgreSQL migration/backfill contracts on an explicitly owned clone."""
import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from src.database.course_duration import backfill
from src.database.course_curriculum import backfill as curriculum_backfill


class CourseDurationDatabaseTests(unittest.TestCase):
    def app_schema(self):
        return (Path(__file__).resolve().parents[2]/'backend/db/02_app_ext.sql').read_text(encoding='utf-8')

    def setUp(self):
        url=os.environ.get('EMPLOYEE_FORM_TEST_DB_URL','')
        if not url:self.skipTest('An isolated local test DB is required')
        p=conninfo_to_dict(url)
        if p.get('host')!='127.0.0.1' or not p.get('dbname','').startswith('growpath_employee_form_test_'):
            raise ValueError('Refuse duration fixtures outside an owned local clone')
        self.c=psycopg.connect(url,row_factory=dict_row,connect_timeout=5)
        self.addCleanup(self.c.close);self.addCleanup(self.c.rollback)
        self.id='DURATION_FIXTURE_'+uuid4().hex
        self.c.execute("INSERT INTO public.courses(course_id,title,platform) VALUES(%s,'Duration fixture','MS Learn')",(self.id,))
        self.c.execute("""INSERT INTO growpath_meta.catalog_api_sources(resource_type,source,external_key,entity_key,payload,mapping_evidence,fetched_at)
            VALUES('courses','API_MS_LEARN',%s,%s,%s,'{}',now())""",(self.id,self.id,Jsonb({'duration_in_minutes':71})))

    def test_preview_is_readonly_and_apply_is_repeatable_without_legacy_field_changes(self):
        before=self.c.execute('SELECT title,platform,duration_weeks FROM public.courses WHERE course_id=%s',(self.id,)).fetchone()
        backfill(self.c)
        self.assertIsNone(self.c.execute('SELECT duration_seconds FROM public.courses WHERE course_id=%s',(self.id,)).fetchone()['duration_seconds'])
        backfill(self.c,apply=True)
        self.assertEqual(backfill(self.c,apply=True)['changed_count'],0)
        row=self.c.execute('SELECT duration_seconds,duration_kind,estimated_duration_seconds FROM public.courses WHERE course_id=%s',(self.id,)).fetchone()
        self.assertEqual(row,{'duration_seconds':4260,'duration_kind':'learning','estimated_duration_seconds':None})
        self.assertEqual(self.c.execute('SELECT title,platform,duration_weeks FROM public.courses WHERE course_id=%s',(self.id,)).fetchone(),before)

    def test_bad_duration_or_kind_rolls_back_the_entire_update(self):
        backfill(self.c,apply=True)
        for assignment in ('duration_seconds=-1','duration_kind=NULL'):
            with self.subTest(assignment=assignment), self.assertRaises(psycopg.errors.CheckViolation):
                with self.c.transaction():
                    self.c.execute('UPDATE public.courses SET duration_seconds=5000 WHERE course_id=%s',(self.id,))
                    self.c.execute('UPDATE public.courses SET '+assignment+' WHERE course_id=%s',(self.id,))
            self.assertEqual(self.c.execute('SELECT duration_seconds FROM public.courses WHERE course_id=%s',(self.id,)).fetchone()['duration_seconds'],4260)

    def test_timezone_changes_preserve_evidence_but_new_fetch_time_is_detected(self):
        backfill(self.c, apply=True)
        before = self.c.execute('SELECT duration_provenance FROM public.courses WHERE course_id=%s', (self.id,)).fetchone()
        for zone in ('Asia/Seoul', 'UTC'):
            self.c.execute("SELECT set_config('TimeZone',%s,true)", (zone,))
            self.assertEqual(backfill(self.c, apply=True)['changed_count'], 0)
            self.assertEqual(self.c.execute('SELECT duration_provenance FROM public.courses WHERE course_id=%s', (self.id,)).fetchone(), before)
        self.c.execute("UPDATE growpath_meta.catalog_api_sources SET fetched_at=fetched_at+interval '1 second' WHERE resource_type='courses' AND entity_key=%s", (self.id,))
        self.assertEqual(backfill(self.c)['changed_count'], 1)

    def test_fresh_and_legacy_app_schema_share_the_same_hours_origin_check(self):
        self.c.execute(self.app_schema())
        self.c.execute('ALTER TABLE app_ext.resource_meta DROP CONSTRAINT resource_meta_hours_origin_check')
        self.c.execute('ALTER TABLE app_ext.resource_meta DROP COLUMN hours_origin')
        for _ in range(2):
            self.c.execute(self.app_schema())
        count=self.c.execute("SELECT count(*) AS n FROM pg_constraint WHERE conrelid='app_ext.resource_meta'::regclass AND conname='resource_meta_hours_origin_check'").fetchone()['n']
        self.assertEqual(count,1)
        for value in ('legacy','catalog','manual'):
            self.c.execute("INSERT INTO app_ext.resource_meta(resource_key,resource_type,course_id,hours_origin) VALUES(%s,'course',%s,%s)",(self.id+value,self.id,value))
        with self.assertRaises(psycopg.errors.CheckViolation),self.c.transaction():
            self.c.execute("UPDATE app_ext.resource_meta SET hours_origin='invalid' WHERE resource_key=%s",(self.id+'legacy',))
        self.assertEqual(self.c.execute('SELECT hours_origin FROM app_ext.resource_meta WHERE resource_key=%s',(self.id+'legacy',)).fetchone()['hours_origin'],'legacy')

    def test_invalid_legacy_origin_fails_upgrade_without_silently_repairing_data(self):
        self.c.execute(self.app_schema())
        self.c.execute('ALTER TABLE app_ext.resource_meta DROP CONSTRAINT resource_meta_hours_origin_check')
        self.c.execute("INSERT INTO app_ext.resource_meta(resource_key,resource_type,course_id,hours_origin) VALUES(%s,'course',%s,'invalid')",(self.id,self.id))
        with self.assertRaises(psycopg.errors.CheckViolation),self.c.transaction():
            self.c.execute(self.app_schema())
        self.assertEqual(self.c.execute('SELECT hours_origin FROM app_ext.resource_meta WHERE resource_key=%s',(self.id,)).fetchone()['hours_origin'],'invalid')

    def test_curriculum_preview_repeatability_source_preservation_and_bad_json_rollback(self):
        original=self.c.execute('SELECT payload FROM growpath_meta.catalog_api_sources WHERE entity_key=%s',(self.id,)).fetchone()
        curriculum_backfill(self.c)
        self.assertEqual(self.c.execute('SELECT curriculum FROM public.courses WHERE course_id=%s',(self.id,)).fetchone()['curriculum'],{})
        curriculum_backfill(self.c,apply=True)
        self.assertEqual(curriculum_backfill(self.c,apply=True)['changed_count'],0)
        saved=self.c.execute('SELECT curriculum FROM public.courses WHERE course_id=%s',(self.id,)).fetchone()['curriculum']
        self.assertEqual(saved['coverage'],'description_only')
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.c.transaction():
                self.c.execute("UPDATE public.courses SET curriculum='{}' WHERE course_id=%s",(self.id,))
                self.c.execute("UPDATE public.courses SET curriculum='[]' WHERE course_id=%s",(self.id,))
        self.assertEqual(self.c.execute('SELECT curriculum FROM public.courses WHERE course_id=%s',(self.id,)).fetchone()['curriculum'],saved)
        self.assertEqual(self.c.execute('SELECT payload FROM growpath_meta.catalog_api_sources WHERE entity_key=%s',(self.id,)).fetchone(),original)


if __name__=='__main__':unittest.main()

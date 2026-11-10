"""시연 초기화·단계 이동 계약. DB 검사는 별도 복원한 테스트 DB에서만 명시적으로 실행한다."""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, db
from app.errors import ApiError, api_error_handler
from app.routers import account
from app.services import demo, drafts, plans


class CommentPreviewTests(unittest.TestCase):
    def test_old_comment_request_needs_no_database_or_supervisor(self):
        with patch.object(db, 'tx', side_effect=AssertionError('unexpected DB access')):
            self.assertEqual(demo.jump(123, 'comment'), {'entry': 'home'})


@unittest.skipUnless(os.getenv('GP_TEST_DEMO_RECORDS_DB'), '별도 복원한 시연 테스트 DB 필요')
class DemoDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(db.val('SELECT current_database()'), os.environ['GP_TEST_DEMO_RECORDS_DB'])
        self.org = 'qa-' + uuid.uuid4().hex
        with db.tx() as t:
            t.run("INSERT INTO public.institutions(institution_id, name) VALUES(:org, 'QA')", org=self.org)
            dept = t.val("""INSERT INTO public.departments(institution_id, name, department_code)
                            VALUES(:org, 'QA', 'QA') RETURNING department_id""", org=self.org)
            def employee(head):
                return t.val("""INSERT INTO public.employees(name, employee_number, institution_id, department_id, is_department_head)
                                VALUES('QA', :code, :org, :dept, :head) RETURNING employee_id""",
                             code=uuid.uuid4().hex, org=self.org, dept=dept, head=head)
            self.head, self.employee = employee(True), employee(False)
        self.addCleanup(self.clean_fixtures)
        app = FastAPI()
        app.include_router(account.r)
        app.add_exception_handler(ApiError, api_error_handler)
        app.dependency_overrides[account.require_demo_mode] = lambda: None
        app.dependency_overrides[auth.require_employee] = lambda: auth.Account('employee', self.employee, 'QA')
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def clean_fixtures(self):
        with db.tx() as t:
            t.run('DELETE FROM public.projects WHERE employee_id IN (:e, :h)', e=self.employee, h=self.head)
            t.run('DELETE FROM public.employees WHERE institution_id = :org', org=self.org)
            t.run('DELETE FROM public.departments WHERE institution_id = :org', org=self.org)
            t.run('DELETE FROM public.institutions WHERE institution_id = :org', org=self.org)

    def jump(self, stage):
        res = self.client.post('/api/v1/demo/jump', json={'stage': stage})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()['entry']

    def projects(self, employee):
        return db.all_('SELECT * FROM public.projects WHERE employee_id = :e ORDER BY project_id', e=employee)

    def test_all_stages_preserve_unmarked_project_and_other_employee(self):
        with db.tx() as t:
            t.run("""INSERT INTO public.projects(employee_id, project_name, status)
                     VALUES(:e, '새 로드맵(작성 중)', 'ARCHIVED')""", e=self.employee)
        original = self.projects(self.employee)[0]
        demo.jump(self.head, 'details')
        other = self.projects(self.head)
        for stage in demo.STAGES:
            with self.subTest(stage=stage):
                before = self.projects(self.employee)
                entry = self.jump(stage)
                rows = self.projects(self.employee)
                self.assertIn(original, rows)
                self.assertEqual(self.projects(self.head), other)
                if stage == 'comment':
                    self.assertEqual(rows, before)
                else:
                    self.assertEqual(len(rows) - 1, {'start': 0, 'multi': 2}.get(stage, 1))
                if stage == 'report':
                    self.assertTrue(entry.startswith('report:'))
                    self.assertTrue(db.val('SELECT report_content FROM public.growth_reports WHERE report_id = CAST(:id AS uuid)',
                                           id=entry.split(':')[1])['doneTitles'])
        for _ in range(2):
            self.assertEqual(self.client.post('/api/v1/demo/reset').status_code, 200)
            self.assertEqual(self.projects(self.employee), [original])

    def test_real_comment_and_notification_survive_reset_and_jump(self):
        self.jump('active')
        rid = str(plans._base_rows(self.employee)[0]['roadmap_id'])
        cid = plans.send_comment(self.head, self.employee, rid, demo.D['commentSample'])
        original = self.projects(self.employee)[0]
        for stage in ('comment', 'start', 'active', 'start'):
            self.jump(stage)
            self.assertIn(original, self.projects(self.employee))
            self.assertEqual(db.all_('SELECT comment_id::text AS id FROM public.roadmap_comments WHERE author_employee_id = :h',
                                     h=self.head), [{'id': cid}])
            self.assertEqual(db.val('SELECT count(*) FROM app_ext.notifications WHERE recipient_id = :e AND kind = \'comment\'',
                                    e=self.employee), 1)

    def test_existing_draft_failed_generation_and_concurrent_jumps(self):
        self.jump('active')
        drafts.create(self.employee, {'draft': {'goal': '직원의 초안', 'demoSeeded': True}})
        initial = self.projects(self.employee)
        res = self.client.post('/api/v1/demo/jump', json={'stage': 'quiz'})
        self.assertEqual((res.status_code, res.json()['error']['code']), (409, 'EXISTING_DRAFT'))
        with patch.object(demo, '_seed_report', side_effect=RuntimeError('중간 실패')):
            with self.assertRaises(RuntimeError):
                demo.jump(self.employee, 'report')
        self.assertEqual(self.projects(self.employee), initial)
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(list(pool.map(lambda _: demo.jump(self.employee, 'active')['entry'], range(2))), ['home', 'home'])
        self.assertEqual(len(self.projects(self.employee)), 2)
        demo.reset(self.employee)
        self.assertEqual(self.projects(self.employee), [next(row for row in initial if row['status'] == 'DRAFTING')])

    def test_concurrent_supervisor_comment_is_preserved_if_accepted(self):
        self.jump('active')
        rid = str(plans._base_rows(self.employee)[0]['roadmap_id'])
        with ThreadPoolExecutor(2) as pool:
            sending = pool.submit(plans.send_comment, self.head, self.employee, rid, demo.D['commentSample'])
            resetting = pool.submit(demo.reset, self.employee)
            resetting.result()
            try:
                cid = sending.result()
            except ApiError as error:
                self.assertEqual(error.status, 404)
                self.assertEqual(self.projects(self.employee), [])
            else:
                stored = db.one('SELECT author_employee_id FROM public.roadmap_comments WHERE comment_id = CAST(:c AS uuid)', c=cid)
                self.assertEqual(stored, {'author_employee_id': self.head})

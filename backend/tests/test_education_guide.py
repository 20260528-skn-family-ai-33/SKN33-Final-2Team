"""생성 화면 전용 교육비 근거의 조회 횟수와 직원 경계를 확인한다."""
import unittest
from unittest.mock import patch

from app.errors import ApiError
from app.services import drafts, job_recovery


class EducationGuideTests(unittest.TestCase):
    def setUp(self):
        self.row = {'draft_choices': {'gp5': 1, 'draft': {'genRun': {'key': 'k'}}}}
        self.enterContext(patch.object(drafts.db, 'tx'))
        self.owned = self.enterContext(patch.object(drafts, '_row', return_value=self.row))
        self.source = self.enterContext(patch.object(drafts.REG, 'education_guide'))
        self.enterContext(patch.object(drafts.PF, 'employee_group', return_value='일반직'))
        self.write = self.enterContext(patch.object(drafts, '_write', side_effect=self.save))

    def save(self, transaction, draft_id, wrapper):
        self.row['draft_choices'] = wrapper

    def test_reentry_reuses_stored_result_including_missing_source(self):
        for basis in (None, {'chunkId': 'article'}):
            with self.subTest(basis=basis):
                self.row['draft_choices']['draft'].pop('educationGuide', None)
                self.source.reset_mock()
                self.source.return_value = {'basis': basis}
                first = drafts.education_guide(1, 'draft')
                drafts._apply_client(self.row['draft_choices'], {'educationGuide': {'basis': 'client'}})
                self.assertEqual(drafts.education_guide(1, 'draft'), first)
                self.source.assert_called_once()

    def test_pre_generation_and_foreign_draft_do_not_invoke_agent(self):
        self.row['draft_choices']['draft'].clear()
        with self.assertRaises(ApiError) as err:
            drafts.education_guide(1, 'draft')
        self.assertEqual(err.exception.status, 409)
        self.owned.side_effect = ApiError(404, 'NOT_FOUND', '초안')
        with self.assertRaises(ApiError) as err:
            drafts.education_guide(2, 'draft')
        self.assertEqual(err.exception.status, 404)
        self.source.assert_not_called()
        self.write.assert_not_called()

    def test_failed_read_is_not_cached_and_old_recovery_starts_no_work(self):
        self.source.side_effect = RuntimeError('read failed')
        with self.assertRaises(RuntimeError):
            drafts.education_guide(1, 'draft')
        self.write.assert_not_called()
        with patch.object(drafts.jobs, 'start') as start:
            for op in ('drafts._maybe_support', 'plans.revision_support'):
                self.assertIsNone(job_recovery.invoke({'operation': op, 'kwargs': {'employee_id': 1}}, 1))
            start.assert_not_called()

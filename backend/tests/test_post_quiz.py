import unittest
from copy import deepcopy
from app.errors import ApiError
from app.services.post_quiz import validate,comparison,public_assessment

class PostQuizTests(unittest.TestCase):
    def test_parallel_quiz_preserves_measurement_and_original_survey(self):
        from app.services.post_quiz import generate
        self.plan['goal']='SQL 프로젝트'
        group=self.plan['assess']['v2']['survey']['groups'][0]
        group['surveys']=[{'id':'s','text':'중복 조인을 검증할 수 있다.'}]
        measurement={'concept':'일대다 조인의 행 증가','questionType':'오류 원인 판단','difficulty':'적용'}
        group['quizzes'][0].update(measurement)
        original=deepcopy(self.plan)
        row={'id':'q','skill':'SQL','q':'주문 조인 후 행이 늘어난 원인은?',
             'options':['a','b','c','d','e'],'answer':1,'explain':'일대다 관계 때문이다.',**measurement}
        result=generate(self.plan,lambda *_:{'quizzes':[row]})
        self.assertEqual(self.plan,original)
        self.assertEqual(result['groups'][0]['surveys'],[])
        self.assertEqual(result['groups'][0]['quizzes'][0]['concept'],measurement['concept'])
        for key in measurement:
            bad=deepcopy(row);bad[key]='다른 기준'
            with self.subTest(key=key), self.assertRaises(ApiError):
                generate(self.plan,lambda *_:{'quizzes':[bad]})

    def test_whitespace_only_rewording_and_duplicate_choices_are_rejected(self):
        from app.services.post_quiz import generate
        self.plan['goal']='SQL 프로젝트'
        row={'id':'q','skill':'SQL','q':'조인   구문','options':['a','b','c','d','e'],'answer':1,'explain':'근거'}
        with self.assertRaises(ApiError):generate(self.plan,lambda *_:{'quizzes':[row]})
        row.update(q='새로운 조인 상황',options=['a',' a ','c','d','e'])
        with self.assertRaises(ApiError):generate(self.plan,lambda *_:{'quizzes':[row]})

    def setUp(self):
        self.plan={'assess':{'v2':{'survey':{'groups':[{'skill':'SQL','quizzes':[{'id':'q','q':'조인 구문','options':['JOIN','DROP'],'answer':0,'explain':'근거'}]}]},'answers':{'q':1}}}}
    def test_zero_answer_is_valid_and_required(self):
        self.assertEqual(validate(self.plan,{'q':'0'},True),{'q':'0'})
        for answers in ({},{'q':'2'},{'other':0},{'q':False}):
            with self.assertRaises(ApiError):validate(self.plan,answers,True)
    def test_pre_post_comparison(self):
        row=comparison(self.plan,{'q':'0'})[0]
        self.assertEqual((row['pre'],row['post']),('오답','정답'))
    def test_public_questions_hide_answer_without_mutation(self):
        self.plan['assess']['v2']['survey']['groups'][0]['quizzes'][0]['concept']='조인 관계'
        value=public_assessment(self.plan['assess'])
        self.assertNotIn('answer',value['v2']['survey']['groups'][0]['quizzes'][0])
        self.assertNotIn('concept',value['v2']['survey']['groups'][0]['quizzes'][0])
        revealed=public_assessment(self.plan['assess'],reveal=True)
        self.assertEqual(revealed['v2']['survey']['groups'][0]['quizzes'][0]['answer'],0)
        self.assertEqual(revealed['v2']['survey']['groups'][0]['quizzes'][0]['explain'],'근거')
        self.assertNotIn('concept',revealed['v2']['survey']['groups'][0]['quizzes'][0])
        self.assertEqual(self.plan['assess']['v2']['survey']['groups'][0]['quizzes'][0]['answer'],0)
    def test_legacy_plan_has_no_required_v2_quiz(self):
        self.assertEqual(validate({'assess':{}},{},True),{})

    def test_new_quiz_keeps_ids_and_rejects_repeated_question(self):
        from app.services.post_quiz import generate
        row={'id':'q','skill':'SQL','q':'새 조인 상황','options':['a','b','c','d','e'],'answer':1,'explain':'근거'}
        self.plan['goal']='SQL 프로젝트'
        result=generate(self.plan,lambda *_:{'quizzes':[row]})
        self.assertEqual(result['groups'][0]['quizzes'][0]['id'],'q')
        self.assertEqual(comparison(self.plan,{'q':'1'},result)[0]['post'],'정답')
        row['q']='조인 구문'
        with self.assertRaises(ApiError):generate(self.plan,lambda *_:{'quizzes':[row]})

    def test_post_record_only_reveals_quiz_answers_after_submission_starts_or_completes(self):
        from unittest.mock import MagicMock, patch
        from app.services import plans
        survey = self.plan['assess']['v2']['survey']
        row_active = {'roadmap_id': 'r1', 'diagnostic_round_id': 1, 'status': 'IN_PROGRESS'}
        row_done = {'roadmap_id': 'r1', 'diagnostic_round_id': 1, 'status': 'COMPLETED'}
        with patch.object(plans.db, 'all_', return_value=[]), patch.object(plans.db, 'tx', return_value=MagicMock()), patch.object(plans.db, 'J', side_effect=lambda x: x):
            with patch.object(plans.db, 'one', return_value={'running': False, 'deep': {'v2Quiz': survey}}):
                hidden = plans._post(row_active, {'assess': {'questions': []}})
            with patch.object(plans.db, 'one', return_value={'running': True, 'deep': {'v2Quiz': survey}}):
                running = plans._post(row_active, {'assess': {'questions': []}})
            with patch.object(plans.db, 'one', return_value={'running': False, 'deep': {'v2Quiz': survey}}):
                done = plans._post(row_done, {'assess': {'questions': []}})
        self.assertNotIn('answer', hidden['quizSurvey']['groups'][0]['quizzes'][0])
        self.assertNotIn('explain', hidden['quizSurvey']['groups'][0]['quizzes'][0])
        self.assertEqual(running['quizSurvey']['groups'][0]['quizzes'][0]['answer'], 0)
        self.assertEqual(running['quizSurvey']['groups'][0]['quizzes'][0]['explain'], '근거')
        self.assertEqual(done['quizSurvey']['groups'][0]['quizzes'][0]['answer'], 0)
        self.assertEqual(done['quizSurvey']['groups'][0]['quizzes'][0]['explain'], '근거')

    def test_save_post_rejects_answer_changes_after_submission_even_if_report_failed(self):
        from unittest.mock import MagicMock, patch
        from app.services import plans
        survey = self.plan['assess']['v2']['survey']
        plan = {'assess': {'questions': [], **self.plan['assess']}}
        row = {'roadmap_id': 'r1', 'status': 'IN_PROGRESS', 'project_id': 1, 'diagnostic_round_id': 1, 'content': plan}
        tx = MagicMock()
        tx.all.return_value = []
        with patch.object(plans, '_owned', return_value=row), patch.object(plans, 'record', return_value={'post': True}), patch.object(plans.db, 'J', side_effect=lambda x: x), patch.object(plans.db, 'tx') as transaction:
            transaction.return_value.__enter__.return_value = tx
            with patch.object(plans.db, 'one', return_value={'running': False, 'deep': {'v2Quiz': survey, 'v2Answers': {'q': '0'}, 'v2Submitted': True}}):
                with self.assertRaises(ApiError) as err:
                    plans.save_post(1, 'r1', {'answers': {}, 'quizAnswers': {'q': '1'}, 'goalSelf': '1'})
                self.assertEqual(err.exception.code, 'POST_LOCKED')
                self.assertEqual(plans.save_post(1, 'r1', {'answers': {}, 'quizAnswers': {'q': '0'}, 'goalSelf': '1'}), {'post': True})
                self.assertEqual(plans.save_post(1, 'r1', {'answers': {}, 'goalSelf': '1'}), {'post': True})

    def test_save_post_and_report_start_reject_invalid_scores_and_goal_self(self):
        from unittest.mock import MagicMock, patch
        from app.services import plans
        plan = {'assess': {'questions': [{'id': 'q1'}]}}
        row = {'roadmap_id': 'r1', 'status': 'IN_PROGRESS', 'project_id': 1, 'diagnostic_round_id': 1, 'content': plan}
        with patch.object(plans, '_owned', return_value=row):
            for bad_answers in ('not-dict', {'q1': 'abc'}, {'q1': '0'}, {'q1': '6'}, {'q1': 99}, {'q1': True}):
                with self.subTest(bad_answers=bad_answers), self.assertRaises(ApiError) as err:
                    plans.save_post(1, 'r1', {'answers': bad_answers, 'goalSelf': '1'})
                self.assertEqual(err.exception.status, 422)
                self.assertEqual(err.exception.code, 'POST_ANSWERS_INVALID')
            for bad_goal in ('0', '99', 'abc', True, 1.5):
                with self.subTest(bad_goal=bad_goal), self.assertRaises(ApiError) as err:
                    plans.save_post(1, 'r1', {'answers': {'q1': '3'}, 'goalSelf': bad_goal})
                self.assertEqual(err.exception.status, 422)
                self.assertEqual(err.exception.code, 'POST_GOAL_SELF_INVALID')
            for bad_goal in ('0', '99', 'abc', True):
                with patch.object(plans, 'record', return_value={'plan': plan, 'post': {'answers': {'q1': '3'}, 'goalSelf': bad_goal}}):
                    with self.subTest(report_goal=bad_goal), self.assertRaises(ApiError) as err:
                        plans.report_start(1, 'r1')
                    self.assertEqual(err.exception.status, 422)
                    self.assertEqual(err.exception.code, 'POST_GOAL_SELF_INVALID')
            with patch.object(plans, 'record', return_value={'plan': plan, 'post': {'answers': {'q1': '9'}, 'goalSelf': '1'}}):
                with self.assertRaises(ApiError) as err:
                    plans.report_start(1, 'r1')
                self.assertEqual(err.exception.status, 422)
                self.assertEqual(err.exception.code, 'POST_ANSWERS_INVALID')

    def test_save_progress_and_save_post_validate_attachment_metadata(self):
        from contextlib import nullcontext
        from unittest.mock import MagicMock, patch
        from app.services import plans
        bad_files = [
            'bad',
            {'name': 'a.pdf'},
            {'fileId': 'short', 'name': 'a.pdf', 'size': 10},
            {'fileId': 'a' * 32, 'name': ' ', 'size': 10},
            {'fileId': 'a' * 32, 'name': 'a\npdf', 'size': 10},
            {'fileId': 'a' * 32, 'name': 'a.pdf', 'size': -1},
            {'fileId': 'a' * 32, 'name': 'a.pdf', 'size': 15_000_001},
            {'fileId': 'a' * 32, 'name': 'a.pdf', 'size': True},
            {'fileId': 'a' * 32, 'name': 'a.pdf', 'size': 10, 'extra': 1},
        ]
        for bad in bad_files:
            with self.subTest(progress_bad=bad), self.assertRaises(ApiError) as err:
                plans.save_progress(1, 'r1', 'act1', {'status': 'doing', 'file': bad})
            self.assertEqual(err.exception.status, 422)
            self.assertEqual(err.exception.code, 'ATTACHMENT_INVALID')
            with self.subTest(post_bad=bad), self.assertRaises(ApiError) as err:
                plans.save_post(1, 'r1', {'answers': {}, 'goalSelf': '1', 'file': bad})
            self.assertEqual(err.exception.status, 422)
            self.assertEqual(err.exception.code, 'ATTACHMENT_INVALID')

        valid_file = {'fileId': 'a' * 32, 'name': ' result.pdf ', 'size': 1024}
        progress_row = {'roadmap_id': 'r1', 'project_id': 1, 'status': 'IN_PROGRESS', 'content': {'acts': [{'id': 'act1', 'res': None}]}}
        for file_payload, expected_f in ((valid_file, {'fileId': 'a' * 32, 'name': 'result.pdf', 'size': 1024}), (None, None)):
            tx = MagicMock()
            tx.one.side_effect = [{'content': progress_row['content']}, {'memo': '', 'attachment': None}]
            tx.val.return_value = 'IN_PROGRESS'
            with patch.object(plans, '_owned', return_value=progress_row), patch.object(plans, 'record', return_value={'ok': True}), patch.object(plans.db, 'tx', return_value=nullcontext(tx)), patch.object(plans.db, 'J', side_effect=lambda x: x):
                self.assertEqual(plans.save_progress(1, 'r1', 'act1', {'status': 'done', 'file': file_payload}), {'ok': True})
            insert = next(c.kwargs for c in tx.run.call_args_list if 'INSERT INTO app_ext.activity_progress' in c.args[0])
            self.assertEqual(insert['f'], expected_f)

        post_row = {'roadmap_id': 'r1', 'status': 'IN_PROGRESS', 'project_id': 1, 'diagnostic_round_id': 1, 'content': {'assess': {'questions': []}}}
        for file_payload, expected_a in ((valid_file, {'fileId': 'a' * 32, 'name': 'result.pdf', 'size': 1024}), (None, None)):
            tx = MagicMock()
            tx.all.return_value = []
            with patch.object(plans, '_owned', return_value=post_row), patch.object(plans, 'record', return_value={'post': True}), patch.object(plans.db, 'one', return_value={'running': False, 'deep': {}}), patch.object(plans.db, 'J', side_effect=lambda x: x), patch.object(plans.db, 'tx', return_value=nullcontext(tx)):
                self.assertEqual(plans.save_post(1, 'r1', {'answers': {}, 'goalSelf': '2', 'file': file_payload}), {'post': True})
            insert = next(c.kwargs for c in tx.run.call_args_list if 'INSERT INTO app_ext.post_checks' in c.args[0])
            self.assertEqual(insert['a'], expected_a)
            self.assertEqual(insert['g'], 2)

    def test_workspace_prepares_post_quiz_only_once_for_eligible_active_plan(self):
        from unittest.mock import patch
        from app.services import plans, post_quiz
        eligible_plan = {'version': 1, 'assess': {'v2': {'survey': {'groups': [{'skill': 'S', 'quizzes': [{'id': 'q'}]}]}}}}
        legacy_plan = {'version': 1, 'assess': {'questions': []}}
        plans._WORKSPACE_QUIZ_PREPARED.clear()
        try:
            records = {
                'eligible': {'id': 'eligible', 'status': 'active', 'plan': eligible_plan, 'versions': [eligible_plan], 'post': {'quizSurvey': None, 'submitted': False, 'running': False}},
                'submitted': {'id': 'submitted', 'status': 'active', 'plan': eligible_plan, 'versions': [eligible_plan], 'post': {'quizSurvey': None, 'submitted': True, 'running': False}},
                'legacy': {'id': 'legacy', 'status': 'active', 'plan': legacy_plan, 'versions': [legacy_plan], 'post': {'quizSurvey': None, 'submitted': False, 'running': False}},
            }
            with patch.object(plans, 'records', return_value=records), patch.object(plans, 'reports', return_value=[]), patch.object(plans, 'resources_of', return_value={}), patch.object(post_quiz, 'prepare', return_value='job-1') as prep:
                plans.workspace(1)
                plans.workspace(1)
                prep.assert_called_once_with(1, 'eligible', eligible_plan)
        finally:
            plans._WORKSPACE_QUIZ_PREPARED.clear()



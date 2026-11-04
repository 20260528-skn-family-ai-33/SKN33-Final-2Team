from contextlib import nullcontext
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
from app import db,jobs
from app.auth import Account
from app.errors import ApiError
from app.services import job_recovery as recovery,generation_job,post_quiz,generation_lock
from app.routers import preassessment

class RecoveryTests(TestCase):
    def test_existing_redirect_does_not_start_second_recovery(self):
        with patch.object(jobs,'view'),patch.object(recovery,'generation_guard',return_value=nullcontext()),patch.object(db,'one',return_value={'status':'failed','error':{'code':'JOB_INTERRUPTED'},'progress':{'redirectJobId':'new'}}),patch.object(recovery,'invoke') as invoke:
            self.assertEqual(recovery.resume('old',1),'new');invoke.assert_not_called()

    def test_cancelled_or_model_failure_is_never_automatically_retried(self):
        for status,code in [('cancelled','JOB_INTERRUPTED'),('failed','MODEL_ERROR')]:
            with patch.object(jobs,'view'),patch.object(recovery,'generation_guard',return_value=nullcontext()),patch.object(db,'one',return_value={'status':status,'error':{'code':code},'progress':{'_resume':{'operation':'post-quiz'}}}),patch.object(recovery,'invoke') as invoke:
                with self.assertRaises(ApiError):recovery.resume('old',1)
                invoke.assert_not_called()

    def test_interrupted_job_redirect_is_persisted_before_next_poll(self):
        t=Mock()
        row={'status':'failed','error':{'code':'JOB_INTERRUPTED'},'progress':{'_resume':{'operation':'post-quiz','kwargs':{'employee_id':1,'plan_id':'p'}}}}
        with patch.object(jobs,'view'),patch.object(recovery,'generation_guard',return_value=nullcontext()),patch.object(db,'one',return_value=row),patch.object(recovery,'invoke',return_value='new'),patch.object(db,'tx',return_value=nullcontext(t)):
            self.assertEqual(recovery.resume('old',1),'new')
            self.assertEqual(t.run.call_args.kwargs['n'],'new')

    def test_queued_route_recovery_keeps_account_and_request(self):
        original=Mock(return_value={'survey':{'ready':True}})
        original.__signature__=__import__('inspect').signature(lambda project_id,a:None)
        spec={'operation':'route','module':'app.routers.preassessment','function':'make_survey','kwargs':{'project_id':'p','a':{'type':'employee','id':1,'name':'test'}}}
        def start(kind,employee,ref,run):
            self.assertEqual(run(None),{'survey':{'ready':True}})
            return 'j'
        with patch.object(preassessment,'make_survey',SimpleNamespace(__wrapped__=original)),patch.object(jobs,'start',side_effect=start):
            self.assertEqual(recovery.invoke(spec,1),'j')
            self.assertIsInstance(original.call_args.kwargs['a'],Account)
            with self.assertRaises(ApiError):recovery.invoke(spec,2)

    def test_post_screen_joins_background_generation_and_restart_can_start_new_job(self):
        with patch('app.services.generation_lock.generation_guard',return_value=nullcontext()),patch.object(db,'one',return_value={'job_id':'existing'}),patch.object(jobs,'start') as start:
            self.assertEqual(generation_job.start_shared(1,'post-quiz:p',Mock()),'existing');start.assert_not_called()
        with patch('app.services.generation_lock.generation_guard',return_value=nullcontext()),patch.object(db,'one',return_value=None),patch.object(jobs,'start',return_value='replacement'):
            self.assertEqual(generation_job.start_shared(1,'post-quiz:p',Mock()),'replacement')

    def test_orphan_partial_survey_is_recoverable_but_live_work_is_not_restarted(self):
        saved={'quizStatus':'pending'};project={'goal':'g'}
        for live,status in [(False,'interrupted'),(True,'pending')]:
            with patch.object(preassessment.db,'tx',return_value=nullcontext(Mock())),patch.object(preassessment,'read',return_value=saved),patch.object(preassessment,'project_input',return_value=project),patch.object(preassessment.profile,'view',return_value={}),patch.object(preassessment,'inputs_match',return_value=True),patch.object(preassessment,'public_view',return_value={'quizStatus':'pending'}),patch.object(generation_lock,'generation_running',return_value=live):
                self.assertEqual(preassessment.get_survey('p',Account('employee',1,''))['survey']['quizStatus'],status)

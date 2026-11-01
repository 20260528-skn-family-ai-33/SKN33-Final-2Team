from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from app.agents.prompt_improvement import ImprovementError
from app.services import prompt_improvement_runner as runner, prompt_improvement_worker as worker
from app.services.prompt_improvement_evaluation import CHECKS, SCORES
from app.services.prompt_improvement_schedule import KST
from app.services.prompt_evaluation_replay import evaluate_change, load_cases
from app.agents import roadmap


def evaluation(score):
    return [{'caseId': 'sql', 'checks': dict.fromkeys(CHECKS, True), 'scores': dict.fromkeys(SCORES, score)}]


class PromptCycleTests(TestCase):
    def setUp(self):
        self.snapshot = {course: {'promptVersionId': course+'-v', 'systemPrompt': '### GENERATION\n기존\n### REVISION\n수정'} for course in ('A1','A2','A3')}
        self.change = {'course':'A1','basePromptVersionId':'A1-v','systemPrompt':'### GENERATION\n개선\n### REVISION\n수정','changeReason':'근거','references':[]}
        self.proposal = {'status':'proposed','model':'growpath-27b','metrics':{'eligibleDecisions':30},'changes':[self.change]}

    def test_approved_evaluation_is_bound_to_candidate_before_activation(self):
        evaluate = Mock(return_value=(evaluation(0.5), evaluation(0.6)))
        with patch.object(runner,'current_prompts',return_value=self.snapshot), patch.object(runner,'read_decisions',return_value=[]), patch.object(runner.agent,'run',return_value=self.proposal), patch.object(runner,'activate',return_value={'A1':'new'}) as activate:
            result = runner.run_cycle('prompt-improvement/2026-11', evaluate, ctx=SimpleNamespace())
        self.assertEqual(result['status'],'applied')
        self.assertEqual(evaluate.call_args.args[2],self.snapshot['A1']['systemPrompt'])
        approved=activate.call_args.args[1][0]
        self.assertEqual(approved['systemPrompt'],self.change['systemPrompt'])
        self.assertEqual(approved['candidateEvaluation'],evaluation(0.6))

    def test_regression_or_evaluation_error_keeps_existing_prompt(self):
        for evaluate in (Mock(return_value=(evaluation(0.5), evaluation(0.4))), Mock(side_effect=RuntimeError('private model output'))):
            with patch.object(runner,'current_prompts',return_value=self.snapshot), patch.object(runner,'read_decisions',return_value=[]), patch.object(runner.agent,'run',return_value=self.proposal), patch.object(runner,'activate') as activate:
                result=runner.run_cycle('month',evaluate,ctx=SimpleNamespace())
            activate.assert_not_called()
            self.assertFalse(result['evaluations'][0]['approved'])
            self.assertNotIn('private model output',str(result))

    def test_dry_run_never_activates(self):
        with patch.object(runner,'current_prompts',return_value=self.snapshot), patch.object(runner,'read_decisions',return_value=[]), patch.object(runner.agent,'run',return_value=self.proposal), patch.object(runner,'activate') as activate:
            result=runner.run_cycle('month',Mock(return_value=(evaluation(0.5),evaluation(0.6))),ctx=SimpleNamespace(),apply=False)
        self.assertTrue(result['dryRun'])
        activate.assert_not_called()

    def test_stale_parent_or_already_applied_month_never_updates(self):
        approved=dict(self.change,baselineEvaluation=evaluation(0.5),candidateEvaluation=evaluation(0.6))
        for stale in (True,False):
            transaction=Mock()
            transaction.one.return_value=None if stale else {'exists':True}
            with patch.object(runner.db,'tx') as tx, patch.object(runner,'current_prompts',return_value={} if stale else self.snapshot):
                tx.return_value.__enter__.return_value=transaction
                with self.assertRaises(ImprovementError):runner.activate(self.snapshot,[approved],'prompt-improvement/2026-11')
            transaction.run.assert_not_called()

    def test_activation_preserves_parent_and_uses_one_transaction_without_deleting_history(self):
        approved=dict(self.change,baselineEvaluation=evaluation(0.5),candidateEvaluation=evaluation(0.6))
        transaction=Mock()
        transaction.one.return_value=None
        transaction.val.side_effect=[None,None,None,2,'new-version']
        with patch.object(runner.db,'tx') as tx, patch.object(runner,'current_prompts',return_value=self.snapshot):
            tx.return_value.__enter__.return_value=transaction
            result=runner.activate(self.snapshot,[approved],'prompt-improvement/2026-11')
        self.assertEqual(result,{'A1':'new-version'})
        tx.assert_called_once()
        insert=transaction.val.call_args
        self.assertEqual(insert.kwargs['parent'],'A1-v')
        self.assertIn('monthly-prompt-improvement:prompt-improvement/2026-11',insert.kwargs['reason'])
        self.assertNotIn('DELETE',str(transaction.mock_calls))


class PromptWorkerTests(TestCase):
    def test_month_is_claimed_once_even_after_failure(self):
        when=datetime(2026,11,2,6,tzinfo=KST)
        with TemporaryDirectory() as directory, patch.object(worker,'run_cycle',side_effect=RuntimeError('private')) as cycle:
            result=worker.execute_month(when,Path(directory),Mock(),now=when)
            duplicate=worker.execute_month(when,Path(directory),Mock(),now=when)
            record=json.loads(next(Path(directory).glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(result['status'],'failed')
        self.assertEqual(duplicate['status'],'already_claimed')
        self.assertEqual(record['errorType'],'RuntimeError')
        self.assertNotIn('private',str(record))
        cycle.assert_called_once()

    def test_early_or_wrong_calendar_date_never_runs(self):
        when=datetime(2026,11,2,6,tzinfo=KST)
        with TemporaryDirectory() as directory, patch.object(worker,'run_cycle') as cycle:
            for scheduled,now in ((when,datetime(2026,11,2,5,tzinfo=KST)),(datetime(2026,11,3,6,tzinfo=KST),datetime(2026,11,3,7,tzinfo=KST))):
                with self.assertRaises(ValueError):worker.execute_month(scheduled,Path(directory),Mock(),now=now)
            cycle.assert_not_called()


class ReplayEvaluationTests(TestCase):
    def test_replay_uses_identical_input_and_does_not_edit_active_prompt(self):
        ctx=SimpleNamespace()
        cases=[{'caseId':'sql','handoff':{'goal':'집계','prefs':{}},'revision':{'changes':{},'request':'완료 기준 보완'}}]
        graded={'left':{'checks':dict.fromkeys(CHECKS,True),'scores':dict.fromkeys(SCORES,0.5)},'right':{'checks':dict.fromkeys(CHECKS,True),'scores':dict.fromkeys(SCORES,0.5)}}
        with patch.object(roadmap,'option',return_value={'id':'A1','acts':[{'res':None}]}) as option, patch.object(roadmap,'revise',return_value={'id':'A1','acts':[{'res':None}]}) as revise, patch.object(roadmap,'build_plan',return_value={'acts':[]}), patch.object(roadmap,'params_of',return_value={}), patch('app.services.prompt_evaluation_replay.catalog.items',return_value={}), patch('app.services.prompt_evaluation_replay.runtime.llm_json',return_value=graded):
            before,after=evaluate_change(ctx,'A1','old','new',cases)
        self.assertEqual(before,after)
        self.assertEqual(option.call_args_list[0].args[1]['handoff'],option.call_args_list[1].args[1]['handoff'])
        self.assertEqual([call.args[1]['_evaluationPrompt'] for call in option.call_args_list],['old','new'])
        self.assertEqual([call.args[1]['_evaluationPrompt'] for call in revise.call_args_list],['old','new'])
        self.assertEqual(revise.call_args_list[0].args[1]['plan'],revise.call_args_list[1].args[1]['plan'])
        self.assertEqual(len(before),2)

    def test_missing_or_duplicate_fixed_cases_are_rejected(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'cases.json'
            path.write_text('{}',encoding='utf-8')
            with self.assertRaises(ImprovementError):load_cases(str(path))
            row={'caseId':'same','handoff':{'goal':'집계','prefs':{},'startStage':1},'revision':{'changes':{},'request':'완료 기준 보완'}}
            path.write_text(json.dumps({'caseSetId':'v1','cases':[row,row]}),encoding='utf-8')
            with self.assertRaises(ImprovementError):load_cases(str(path))

    def test_temporary_prompt_does_not_query_or_update_db(self):
        with patch.object(roadmap.db,'all_') as read:
            text=roadmap._sys('A1',roadmap.R_SYS,evaluation_prompt='### GENERATION\n임시\n### REVISION\n수정')
        self.assertTrue(text.startswith('임시'))
        read.assert_not_called()

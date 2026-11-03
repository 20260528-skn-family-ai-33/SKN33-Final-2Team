from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from app.agents.prompt_improvement import ImprovementError, propose, run
from app.services.prompt_selection_metrics import confirmed_decision
from app.services.prompt_improvement_evaluation import CHECKS, SCORES, evaluate_gate


class PromptImprovementTests(TestCase):
    def setUp(self):
        self.prompts = {course: {'promptVersionId': course + '-v1', 'systemPrompt': '### GENERATION\n목표에 맞는 계획\n### REVISION\n기존 정책 유지'} for course in ('A1', 'A2', 'A3')}
        displayed = [{'course': course, 'optionId': course + '-o', 'promptVersionId': row['promptVersionId'], 'source': 'ollama'} for course, row in self.prompts.items()]
        self.events = [confirmed_decision(str(i), datetime(2026, 11, 1, tzinfo=timezone.utc), 'A3', displayed) for i in range(30)]
        self.output = {'note': '선택 비율은 선호 신호이며 효과는 평가가 필요함', 'changes': [{'course': 'A1', 'basePromptVersionId': 'A1-v1',
            'systemPrompt': '### GENERATION\n목표와 완료 기준을 명확히 연결\n### REVISION\n기존 정책 유지', 'changeReason': '선택된 안의 설명 명확성을 참고',
            'references': [{'course': 'A3', 'promptVersionId': 'A3-v1', 'source': 'ollama'}]}]}

    def test_generates_version_bound_proposal_without_raw_personal_inputs(self):
        generate = Mock(return_value=self.output)
        result = propose(self.prompts, self.events, 30, generate)
        self.assertEqual(result['status'], 'proposed')
        self.assertTrue(result['requiresEvaluation'])
        self.assertEqual(generate.call_args.args[1]['selectionMetrics']['eligibleDecisions'], 30)
        self.assertNotIn('events', generate.call_args.args[1])

    def test_insufficient_or_old_versions_do_not_call_model(self):
        generate = Mock()
        self.assertEqual(propose(self.prompts, self.events[:29], 30, generate)['status'], 'insufficient_data')
        old = deepcopy(self.events)
        old[0]['displayed'][0]['promptVersionId'] = 'old'
        self.assertEqual(propose(self.prompts, old, 30, generate)['status'], 'insufficient_data')
        generate.assert_not_called()

    def test_stale_target_unknown_evidence_and_broken_format_are_rejected(self):
        for field, value in [('basePromptVersionId', 'old'), ('systemPrompt', '구역 없음'), ('references', [{'course': 'A3', 'promptVersionId': 'invented', 'source': 'ollama'}])]:
            output = deepcopy(self.output)
            output['changes'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ImprovementError):
                propose(self.prompts, self.events, 30, Mock(return_value=output))

    def test_operational_entrypoint_pins_model_and_minimum_sample(self):
        with patch('app.llm.model_name', return_value='growpath-27b'), patch('app.agents.runtime.llm_json', return_value=self.output) as model:
            result = run(SimpleNamespace(mode='ollama'), self.prompts, self.events)
            self.assertEqual(result['model'], 'growpath-27b')
            self.assertEqual(model.call_args.kwargs['role'], 'roadmap')
            with self.assertRaises(ImprovementError):
                run(SimpleNamespace(mode='ollama'), self.prompts, self.events, 1)
            with self.assertRaises(ImprovementError):
                run(SimpleNamespace(mode='openai'), self.prompts, self.events)

    def test_no_change_does_not_request_evaluation_or_application(self):
        result = propose(self.prompts, self.events, 30, Mock(return_value={'note': '근거 부족', 'changes': []}))
        self.assertEqual(result['status'], 'no_change')
        self.assertFalse(result['requiresEvaluation'])


class PromptEvaluationGateTests(TestCase):
    def cases(self, value=0.5):
        return [{'caseId': 'sql', 'checks': dict.fromkeys(CHECKS, True), 'scores': dict.fromkeys(SCORES, value)}]

    def test_only_improvement_without_regression_passes(self):
        self.assertTrue(evaluate_gate(self.cases(), self.cases(0.6))['approved'])
        self.assertFalse(evaluate_gate(self.cases(), self.cases())['approved'])
        candidate = self.cases(0.9)
        candidate[0]['scores']['constraints'] = 0.4
        self.assertFalse(evaluate_gate(self.cases(), candidate)['approved'])

    def test_missing_cases_failed_policy_and_invalid_scores_fail_closed(self):
        variants = [[], self.cases(0.9), self.cases(0.9), self.cases(0.9)]
        variants[1][0]['caseId'] = 'different'
        variants[2][0]['checks']['freePolicy'] = False
        variants[3][0]['scores']['clarity'] = float('nan')
        for value in variants:
            with self.subTest(value=value):
                self.assertFalse(evaluate_gate(self.cases(), value)['approved'])

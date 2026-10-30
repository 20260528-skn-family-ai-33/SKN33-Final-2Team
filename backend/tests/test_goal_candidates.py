"""목표 후보의 입력 범위·정확한 개수·실제 근거 검증. 외부 모델/DB 호출 없음."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from app.agents import goals
from app.llm import LlmError


class GoalCandidateContractTests(unittest.TestCase):
    def setUp(self):
        self.person = {'name': '입력에 보내지 않을 이름', 'code': 'PRIVATE-NUMBER',
                       'dept': '업무시스템팀', 'grade': '5급', 'job': '인공지능 엔지니어',
                       'certs': ['사회조사분석사 2급']}
        self.inp = goals.goal_input(self.person)
        self.output = {'candidates': [
            {'goal': f'{topic}의 기초 활용 방법을 배우고 싶어요.', 'why': '제공된 소속을 참고해 기초 학습 방향을 골랐어요.', 'basis': ['직급·부서']}
            for topic in ('문서 검색', '데이터 분석', '서비스 운영')], 'note': '담당 업무 입력이 없어 기초 방향으로 제안했어요.'}

    def call(self, output=None):
        with patch.object(goals.rt, 'llm_json', return_value=output or self.output) as model:
            result = goals._api(SimpleNamespace(), self.inp)
        return result, model

    def test_organization_context_without_personal_inputs_uses_real_model_contract(self):
        self.assertTrue(goals.profile_enough(self.person))
        result, model = self.call()
        self.assertEqual(len(result['candidates']), 3)
        model.assert_called_once()
        self.assertEqual(model.call_args.args[2]['profile'], self.inp['profile'])
        self.assertEqual(model.call_args.args[2]['availableBasis'], ['직급·부서', '직무', '보유 자격'])

    def test_identifiers_are_excluded_and_only_consented_evaluations_are_input(self):
        person = dict(self.person, evals=[{'period': '2025', 'grade': 'A', 'consent': False}, {'period': '2026', 'grade': 'B', 'consent': True}])
        inp = goals.goal_input(person)['profile']
        self.assertNotIn('name', inp)
        self.assertNotIn('code', inp)
        self.assertEqual([row['period'] for row in inp['evaluations']], ['2026'])

    def test_identity_only_or_unprovided_context_is_not_a_model_basis(self):
        self.assertFalse(goals.profile_enough({'name': '이름', 'code': '123'}))
        self.assertFalse(goals.profile_enough({'job': '해당 없음', 'dept': '미지정'}))

    def test_two_or_duplicate_candidates_fail_without_fixed_fallback(self):
        for rows in (self.output['candidates'][:2], [self.output['candidates'][0]] * 3):
            with self.subTest(rows=rows), self.assertRaises(LlmError):
                self.call(dict(self.output, candidates=rows))

    def test_empty_reason_or_unprovided_work_basis_is_rejected(self):
        for field, value in (('why', ''), ('basis', []), ('basis', ['업무 설명'])):
            rows = [dict(row) for row in self.output['candidates']]
            rows[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(LlmError):
                self.call(dict(self.output, candidates=rows))

    def test_goal_sentence_must_match_the_requested_ending(self):
        rows = [dict(row) for row in self.output['candidates']]
        rows[0]['goal'] = 'RAG를 운영하는 것이 업무 목표입니다.'
        with self.assertRaises(LlmError):
            self.call(dict(self.output, candidates=rows))


if __name__ == '__main__':
    unittest.main()

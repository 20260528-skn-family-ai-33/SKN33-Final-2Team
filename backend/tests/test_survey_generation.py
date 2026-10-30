import copy
import unittest
from unittest.mock import Mock

from app.agents.survey_generation import SurveyError, generate_survey, profile_input


class SurveyTests(unittest.TestCase):
    def setUp(self):
        self.project = {'goal': '수질 예측', 'projectSummary': '예측·검증 포함. 자동 제어 제외.',
                        'desiredCompetencies': '전처리와 모델 비교', 'rawText': '전달하면 안 되는 원문'}
        self.profile = {'department': '운영부', 'education': ['대학 통계학과 (학사)'], 'self': {}}

    def selection(self, n):
        return {'skills': [{'name': f'스킬{i}', 'reason': '필요', 'application': '검증'} for i in range(n)]}

    def result(self, n):
        count = 5 if n == 1 else 3
        return {'groups': [{'skill': f'스킬{i}', 'title': f'{i}번째 작업을 살펴볼까요',
                            'surveys': [{'text': f'{i}-{j} 작업을 수행할 수 있다.'} for j in range(count)],
                            'quizzes': [{'q': f'{i}-{j} 상황에서 적절한 방법은?',
                                         'options': ['방법 A', '방법 B', '방법 C', '방법 D', '방법 E'],
                                         'answer': j % 4, 'explain': '조건에 맞는 처리 방법이다.'} for j in range(count)]}
                           for i in range(n)]}

    def run_result(self, result, n=2):
        return generate_survey(self.project, self.selection(n), self.profile, lambda *_: result)

    def test_exact_counts_for_every_allowed_skill_count(self):
        for n in range(1, 6):
            with self.subTest(n=n):
                result = self.run_result(self.result(n), n)
                self.assertEqual(result['questionCount'], 10 if n == 1 else n * 6)
                ids = [row['id'] for g in result['groups'] for k in ('surveys', 'quizzes') for row in g[k]]
                self.assertEqual(len(ids), len(set(ids)))

    def test_summary_desired_skills_and_full_profile_pass_without_raw_document(self):
        model = Mock(return_value=self.result(2))
        generate_survey(self.project, self.selection(2), self.profile, model)
        payload = model.call_args.args[1]
        self.assertEqual(payload['projectSummary'], self.project['projectSummary'])
        self.assertEqual(payload['desiredCompetencies'], self.project['desiredCompetencies'])
        self.assertEqual(payload['profile'], self.profile)
        self.assertEqual(payload['skills'], self.selection(2)['skills'])
        self.assertNotIn('rawText', payload)

    def test_full_self_input_and_education_are_kept_without_person_identifiers(self):
        me = {'name': '이름', 'code': '사번', 'dept': '부서', 'parentDept': '본부',
              'education': ['대학교 전공 (석사)'], 'profile': {'workDesc': '업무', 'expSummary': '경험', 'devYears': 0},
              'tech': ['기술'], 'certs': ['자격'], 'learning': ['학습'], 'projects': ['프로젝트']}
        out = profile_input(me)
        for key in ('tech', 'certs', 'learning', 'projects', 'profile'):
            self.assertEqual(out['self'][key], me[key])
        self.assertEqual(out['education'], me['education'])
        self.assertEqual(out['department'], me['dept'])
        self.assertNotIn('name', out)
        self.assertNotIn('code', out)
        out['self']['tech'].append('수정')
        self.assertEqual(me['tech'], ['기술'])

    def test_missing_profile_values_are_not_invented(self):
        out = profile_input({})
        self.assertIsNone(out['department'])
        self.assertIsNone(out['self']['profile'])
        self.assertEqual(out['education'], [])

    def test_skill_order_is_preserved(self):
        raw = self.result(2)
        raw['groups'].reverse()
        self.assertEqual([g['skill'] for g in self.run_result(raw)['groups']], ['스킬0', '스킬1'])

    def test_wrong_count_and_wrong_skill_are_rejected(self):
        bad = []
        raw = self.result(2); raw['groups'][0]['surveys'].pop(); bad.append(raw)
        raw = self.result(2); raw['groups'][0]['quizzes'].append(copy.deepcopy(raw['groups'][0]['quizzes'][0])); bad.append(raw)
        raw = self.result(2); raw['groups'][0]['skill'] = '다른 스킬'; bad.append(raw)
        raw = self.result(2); raw['groups'][0]['skill'] = '스킬1'; bad.append(raw)
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(SurveyError):
                self.run_result(raw)

    def test_invalid_answers_options_and_missing_explanation_are_rejected(self):
        for change in ({'answer': True}, {'answer': -1}, {'answer': 5}, {'answer': '0'},
                       {'options': ['A', 'A ', 'B', 'C']}, {'options': ['A']}, {'explain': ' '}):
            raw = self.result(2)
            raw['groups'][0]['quizzes'][0].update(change)
            with self.subTest(change=change), self.assertRaises(SurveyError):
                self.run_result(raw)

    def test_duplicate_question_or_raw_tag_title_is_rejected(self):
        raw = self.result(2); raw['groups'][1]['surveys'][0] = copy.deepcopy(raw['groups'][0]['surveys'][0])
        with self.assertRaises(SurveyError): self.run_result(raw)
        raw = self.result(2); raw['groups'][0]['title'] = '스킬0'
        with self.assertRaises(SurveyError): self.run_result(raw)

    def test_all_surveys_precede_all_quizzes(self):
        for n in range(1, 6):
            with self.subTest(n=n):
                result = self.run_result(self.result(n), n)
                self.assertEqual([phase['kind'] for phase in result['phases']], ['surveys', 'quizzes'])
                for phase in result['phases']:
                    expected = [q['id'] for group in result['groups'] for q in group[phase['kind']]]
                    self.assertEqual(phase['questionIds'], expected)

    def test_five_options_and_shuffled_answer_stay_consistent(self):
        raw = self.result(2)
        result = self.run_result(raw)
        for before, after in zip(raw['groups'], result['groups']):
            for original, shuffled in zip(before['quizzes'], after['quizzes']):
                self.assertEqual(len(shuffled['options']), 5)
                self.assertEqual(shuffled['options'][shuffled['answer']], original['options'][original['answer']])

    def test_without_project_summary_still_uses_skills_desired_and_profile(self):
        for summary in (None, '', '   '):
            project = dict(self.project, projectSummary=summary)
            model = Mock(return_value=self.result(2))
            result = generate_survey(project, self.selection(2), self.profile, model)
            self.assertEqual(result['questionCount'], 12)
            self.assertIsNone(model.call_args.args[1]['projectSummary'])
            self.assertEqual(model.call_args.args[1]['profile'], self.profile)

    def test_missing_goal_or_desired_blocks_model_call(self):
        for key in ('goal', 'desiredCompetencies'):
            project = dict(self.project); project.pop(key)
            model = Mock()
            with self.subTest(key=key), self.assertRaises(SurveyError):
                generate_survey(project, self.selection(2), self.profile, model)
            model.assert_not_called()

    def test_malformed_output_is_rejected_and_provider_errors_propagate(self):
        for raw in (None, {}, {'groups': 'wrong'}, {'groups': [None, None]}):
            with self.subTest(raw=raw), self.assertRaises(SurveyError): self.run_result(raw)
        with self.assertRaisesRegex(RuntimeError, '접속 실패'):
            generate_survey(self.project, self.selection(2), self.profile, Mock(side_effect=RuntimeError('접속 실패')))


if __name__ == '__main__':
    unittest.main()
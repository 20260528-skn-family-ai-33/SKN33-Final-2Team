import unittest
from unittest.mock import Mock

from app.agents.skill_selection import SelectionError, select_skills


class SkillSelectionTests(unittest.TestCase):
    def setUp(self):
        self.project = {'goal': '문서 검색 프로젝트', 'desiredCompetencies': '검색 결과를 검증하는 역량', 'projectSummary': '근거를 제시하는 RAG',
                        'details': {'weeks': 7, 'etc': '로컬 환경에서 실행'}}
        self.tags = ['스킬' + str(i) for i in range(7)]

    def row(self, name):
        return {'name': name, 'reason': '프로젝트에 필요', 'application': '검색 구현'}

    def select(self, rows):
        return select_skills(self.project, self.tags, lambda *_: {'skills': rows})

    def test_one_three_and_five_kept_without_padding_or_reordering(self):
        for count in (1, 3, 5):
            with self.subTest(count=count):
                rows = [self.row(tag) for tag in reversed(self.tags[:count])]
                self.assertEqual(self.select(rows)['skills'], rows)

    def test_goal_summary_details_and_all_db_tags_reach_model(self):
        generate = Mock(return_value={'skills': [self.row(self.tags[0])]})
        select_skills(self.project, self.tags, generate)
        system, payload = generate.call_args.args
        for key in ('goal', 'projectSummary', 'details', 'desiredCompetencies'):
            self.assertEqual(payload[key], self.project[key])
        self.assertEqual(payload['availableSkills'], self.tags)
        self.assertEqual(payload['maxSkills'], 5)

    def test_only_exact_duplicate_desired_competencies_is_omitted_without_mutation(self):
        from copy import deepcopy
        for desired in ('문서 검색 프로젝트', '  문서 검색 프로젝트  ', '문서 검색 프로젝트 심화', '문서  검색 프로젝트', None):
            with self.subTest(desired=desired):
                project = dict(self.project, desiredCompetencies=desired)
                before = deepcopy(project)
                generate = Mock(return_value={'skills': [self.row(self.tags[0])]})
                result = select_skills(project, self.tags, generate)
                system, payload = generate.call_args.args
                if isinstance(desired, str) and desired.strip() == project['goal'].strip():
                    self.assertNotIn('desiredCompetencies', payload)
                else:
                    self.assertIn('desiredCompetencies', payload)
                    self.assertEqual(payload['desiredCompetencies'], desired)
                self.assertEqual(project, before)
                self.assertEqual(result, {'skills': [self.row(self.tags[0])]})
                self.assertIn('미제공 시 goal 기준', system)

    def test_zero_or_more_than_five_is_rejected_without_silent_truncation(self):
        for count in (0, 6):
            with self.subTest(count=count), self.assertRaises(SelectionError):
                self.select([self.row(tag) for tag in self.tags[:count]])

    def test_unknown_and_duplicate_tag_is_rejected(self):
        for rows in ([self.row('임의 태그')], [self.row(self.tags[0])] * 2):
            with self.subTest(rows=rows), self.assertRaises(SelectionError):
                self.select(rows)

    def test_malformed_output_and_missing_explanations_are_rejected(self):
        for result in (None, {}, {'skills': '잘못된 형식'}, {'skills': [None]},
                       {'skills': [dict(self.row(self.tags[0]), reason=' ')]},
                       {'skills': [dict(self.row(self.tags[0]), application=None)]}):
            with self.subTest(result=result), self.assertRaises(SelectionError):
                select_skills(self.project, self.tags, lambda *_: result)

    def test_missing_goal_or_catalog_never_calls_model(self):
        for project, tags in (({}, self.tags), (self.project, [])):
            generate = Mock()
            with self.subTest(project=project, tags=tags), self.assertRaises(SelectionError):
                select_skills(project, tags, generate)
            generate.assert_not_called()

    def test_provider_failure_is_not_replaced_with_fake_skills(self):
        generate = Mock(side_effect=RuntimeError('연결 실패'))
        with self.assertRaisesRegex(RuntimeError, '연결 실패'):
            select_skills(self.project, self.tags, generate)

    def test_top_level_key_variations_and_bare_list_are_supported(self):
        expected = [self.row(self.tags[0])]
        for payload in (
            {'selected_skills': [self.row(self.tags[0])]},
            {'selectedSkills': [self.row(self.tags[0])]},
            {'skill_list': [self.row(self.tags[0])]},
            {'skills_list': [self.row(self.tags[0])]},
            {'recommended_skills': [self.row(self.tags[0])]},
            {'result': [self.row(self.tags[0])]},
            [self.row(self.tags[0])],
            {'skills': {'1': self.row(self.tags[0])}},
        ):
            with self.subTest(payload=payload):
                res = select_skills(self.project, self.tags, lambda *_: payload)
                self.assertEqual(res['skills'], expected)

    def test_field_name_variations_are_mapped_correctly(self):
        cases = [
            ({'skill': self.tags[0], 'why': '핵심 라이브러리', 'use_case': '파이프라인 구축'},
             {'name': self.tags[0], 'reason': '핵심 라이브러리', 'application': '파이프라인 구축'}),
            ({'skill_name': self.tags[1], 'explanation': '학습 필요', 'usage': '서비스 적용'},
             {'name': self.tags[1], 'reason': '학습 필요', 'application': '서비스 적용'}),
            ({'tag': self.tags[2], 'description': '기반 역량', 'purpose': '데이터 처리'},
             {'name': self.tags[2], 'reason': '기반 역량', 'application': '데이터 처리'}),
        ]
        for item, exp in cases:
            with self.subTest(item=item):
                res = select_skills(self.project, self.tags, lambda *_: {'skills': [item]})
                self.assertEqual(res['skills'], [exp])

    def test_string_array_is_normalized_to_skill_objects(self):
        res = select_skills(self.project, self.tags, lambda *_: {'skills': [self.tags[0], self.tags[1]]})
        self.assertEqual(len(res['skills']), 2)
        self.assertEqual(res['skills'][0]['name'], self.tags[0])
        self.assertEqual(res['skills'][1]['name'], self.tags[1])
        for row in res['skills']:
            self.assertTrue(bool(row.get('reason')))
            self.assertTrue(bool(row.get('application')))

    def test_tag_name_normalization_and_numbering_bullet_stripping(self):
        real_tags = ['Docker 컨테이너 가상화', 'SQL 기본 문법 & 조인', 'PyTorch/TensorFlow 딥러닝 구현']
        payload = [
            {'name': '1. docker 컨테이너 가상화', 'reason': '컨테이너 배포', 'application': '서버 구동'},
            {'name': '- sql 기본 문법 & 조인', 'reason': '데이터 추출', 'application': '쿼리 작성'},
            {'name': '• pytorch/tensorflow 딥러닝 구현', 'reason': '모델 학습', 'application': '추론 파이프라인'},
        ]
        res = select_skills(self.project, real_tags, lambda *_: payload)
        self.assertEqual([r['name'] for r in res['skills']], real_tags)


if __name__ == '__main__':
    unittest.main()
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


if __name__ == '__main__':
    unittest.main()
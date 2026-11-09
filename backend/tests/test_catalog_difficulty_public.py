"""공개 난이도는 신·구 DB에서 원본/추정과 근거를 보존한다. 추천 정렬 정책은 별도다."""
from unittest import TestCase
from unittest.mock import patch
from app import catalog, catalog_candidates, course_levels
from app.services import course_recommendations


class CatalogDifficultyPublicTests(TestCase):
    def test_original_and_db_estimated_difficulties_keep_their_provenance(self):
        raw = {'difficulty': 'UPPER_INTERMEDIATE', 'curriculum': {}}
        self.assertEqual(catalog.difficulty_info(raw, '과정'), {
            'difficulty': 'UPPER_INTERMEDIATE', 'difficultyEstimated': False, 'difficultyBasis': '원본', 'difficultySource': 'original'})
        estimated = dict(raw, difficulty_estimated='true', difficulty_basis='공개 목차의 심화 실습 검토')
        result = catalog.difficulty_info(estimated, '과정')
        self.assertTrue(result['difficultyEstimated'])
        self.assertEqual(result['difficultyBasis'], estimated['difficulty_basis'])

    def test_null_original_in_old_database_is_classified_and_marked_as_estimated(self):
        for raw in ({}, {'difficulty': None}, {'difficulty': None, 'difficulty_estimated': 'false'}):
            with self.subTest(raw=raw):
                result = catalog.difficulty_info(raw, 'SQL 기초')
                self.assertEqual(result['difficulty'], course_levels.LOW)
                self.assertTrue(result['difficultyEstimated'])
                self.assertNotEqual(result['difficultyBasis'], '원본')

    def test_estimates_use_distinct_active_units_and_source_always_wins(self):
        units = [{'title': '성능 튜닝'}, {'title': '장애 복구', 'suspended': True}, {'title': '성능 튜닝'}]
        raw = {'curriculum': {'items': units}}
        self.assertEqual(catalog.difficulty_info(raw, 'SQL')['difficulty'], course_levels.MID)
        units.append({'title': '장애 복구 실습'})
        self.assertEqual(catalog.difficulty_info(raw, 'SQL')['difficulty'], course_levels.HIGH)
        self.assertEqual(catalog.difficulty_info(dict(raw, difficulty=course_levels.LOW), '고급 SQL')['difficulty'], course_levels.LOW)

    def test_public_projection_preserves_provenance(self):
        result = catalog._public({'difficulty': 'BEGINNER', 'difficultyEstimated': True,
                                  'difficultyBasis': '제목의 입문·기초 표기', 'estimated': ['difficulty']})
        self.assertEqual(result['difficulty'], 'BEGINNER')
        self.assertTrue(result['difficultyEstimated'])
        self.assertEqual(result['estimated'], ['difficulty'])
        self.assertEqual(result['difficultyBasis'], '제목의 입문·기초 표기')

    def test_internal_cover_allowlist_does_not_accept_arbitrary_paths(self):
        for path in ('/images/internal-training/crash-05.webp', '/images/internal-training/challenge-1000.webp', '/images/resource-course.svg'):
            self.assertEqual(catalog._image(path), path)
        for path in ('//remote.test/cover', '/images/internal-training/../secret', '/other.webp'):
            self.assertEqual(catalog._image(path), '')

    def test_llm_candidate_receives_estimate_and_basis(self):
        record = {'id': 'sql', 'type': 'course', 'kind': '강좌', 'title': 'SQL 기초',
                  'provider': 'test', 'skills': ['SQL'], 'usable': True, 'cost': 0,
                  'hours': 1, 'content': 'SQL 쿼리 실습', 'curriculum': {},
                  'difficulty': 'BEGINNER', 'difficultyEstimated': True,
                  'difficultyBasis': '제목의 입문·기초 표기', 'estimated': ['difficulty']}
        selection = catalog_candidates.select({'sql': record}, ['SQL'], ['SQL'], 'A1')
        result = catalog_candidates.entry(record, selection)
        self.assertEqual(result['estimated'], ['difficulty'])
        self.assertTrue(result['difficultyEstimated'])
        self.assertEqual(result['difficultyBasis'], record['difficultyBasis'])

    def test_reviewed_basis_is_distinct_from_provider_original_without_becoming_estimated(self):
        result = catalog.difficulty_info({'difficulty': 'UPPER_INTERMEDIATE', 'difficulty_estimated': 'false',
                                          'difficulty_basis': '목차 검토로 중상 확정'}, 'SQL')
        self.assertEqual(result['difficultySource'], 'reviewed')
        self.assertFalse(result['difficultyEstimated'])
        self.assertEqual(catalog._public(result)['difficultySource'], 'reviewed')

    def test_reviewed_basis_reaches_llm_candidates_even_without_new_source_field(self):
        record = {'id': 'sql', 'type': 'course', 'kind': '강좌', 'title': 'SQL', 'provider': 'test',
                  'skills': ['SQL'], 'usable': True, 'cost': 0, 'hours': 1, 'content': 'SQL 실습',
                  'difficulty': 'UPPER_INTERMEDIATE', 'difficultyEstimated': False,
                  'difficultyBasis': '목차 검토로 중상 확정', 'curriculum': {}}
        selection = catalog_candidates.select({'sql': record}, ['SQL'], ['SQL'], 'A1')
        result = catalog_candidates.entry(record, selection)
        self.assertEqual(result['difficultySource'], 'reviewed')
        self.assertFalse(result['difficultyEstimated'])
        self.assertNotIn('difficulty', result.get('estimated', []))

    def test_saved_recommendation_only_refreshes_matching_level_provenance_without_mutation(self):
        old = {'id': 'sql', 'difficulty': 'UPPER_INTERMEDIATE', 'why': '기존 근거', 'cost': 0,
               'estimated': ['format', 'difficulty']}
        current = dict(old, type='course', usable=True, difficultySource='reviewed', difficultyEstimated=False,
                       difficultyBasis='목차 검토로 중상 확정')
        saved = {'skills': [{'name': 'SQL', 'courses': [old], 'books': []}]}
        with patch.object(catalog, 'items', return_value={'sql': current}):
            result = course_recommendations.available_recommendations(saved, 'A3')
        self.assertEqual(result['skills'][0]['courses'][0]['difficultySource'], 'reviewed')
        self.assertEqual(result['skills'][0]['courses'][0]['estimated'], ['format'])
        self.assertNotIn('difficultySource', old)
        self.assertEqual(old['estimated'], ['format', 'difficulty'])
        different_level = dict(old, difficulty='ADVANCED')
        self.assertEqual(catalog.refresh_course_levels([different_level], {'sql': current}), [different_level])

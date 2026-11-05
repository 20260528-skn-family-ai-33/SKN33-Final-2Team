"""영문 경계만 조사에 대응하고 한글 구역 경계·기존 접두사 패턴을 유지한다."""
import re
import unittest

from app import catalog_candidates as candidates, catalog_evidence, learner_knowledge
from app.english_patterns import english_token
from app.services import resource_evidence as evidence


class EnglishPatternTests(unittest.TestCase):
    def test_resource_evidence_matches_particles_without_ascii_substrings(self):
        for pattern, text, rejected in ((evidence._document_target, 'PDF를 검색', 'pdfs'),
                                        (evidence._linux, 'Linux를 사용', 'alinux'),
                                        (evidence._rag_objects, 'RAG로 검색', 'ragged'),
                                        (evidence._foundations, 'context를 이해', 'contexts')):
            with self.subTest(text=text):
                self.assertIsNotNone(pattern.search(text))
                self.assertIsNone(pattern.search(rejected))
        self.assertIn('fastapi', evidence._stack_names('FastAPI로 API 구현'))
        self.assertIsNone(evidence._framework_after.search(' apis'))
        self.assertIsNotNone(evidence._framework_after.search(' API로 구현'))

    def test_catalog_candidates_match_english_actions_and_keep_heading_boundaries(self):
        self.assertIsNotNone(candidates._actions['build'].search('project를 학습'))
        self.assertIsNotNone(candidates._depth_actions['design'].search('design을 배움'))
        self.assertIsNone(candidates._actions['build'].search('projects'))
        self.assertIsNone(candidates._depth_actions['design'].search('redesign'))
        self.assertIsNotNone(candidates._blocked.search('prerequisite는 Python'))
        self.assertIsNotNone(candidates._learning.search('overview를 확인'))
        for text in ('선수지식이 필요함', '수강대상자', '소개합니다'):
            self.assertIsNone((candidates._learning if text.startswith('소개') else candidates._blocked).search(text))
        self.assertIsNone(candidates._blocked.search('Python prerequisites'))
        self.assertIsNone(candidates._learning.search('설명 overview'))
        self.assertIsNotNone(candidates._blocked.search('학습자의 prerequisites는 Python'))
        self.assertEqual(candidates.learning_lines('prerequisites는 Python\n비공개 선수 내용\noverview를 확인\nDocker를 사용'),
                         ['overview를 확인', 'Docker를 사용'])

    def test_learner_knowledge_accepts_korean_adjacency_and_preserves_prefix_matching(self):
        knowledge = {'technologies': ['Python']}
        def exclusion(title):
            return learner_knowledge.exclusion({'type': 'course', 'title': title}, knowledge)
        self.assertIsNotNone(exclusion('Python으로beginner를 시작'))
        self.assertIsNone(exclusion('Python으로beginner와advanced를 학습'))
        self.assertIsNone(exclusion('Python notbeginner'))
        self.assertIsNotNone(exclusion('Python beginnerplus'))

    def test_catalog_evidence_normalizes_html_with_korean_adjacent_tag(self):
        self.assertEqual(catalog_evidence.content_text('<DIV를>Docker를 사용</DIV를>'), 'Docker를 사용')
        self.assertEqual(catalog_evidence.content_text('<divs>Docker를 사용</divs>'), '<divs>Docker를 사용</divs>')

    def test_shared_helper_keeps_ascii_edges_and_caller_case_flags(self):
        pattern = re.compile(english_token('docker'), re.I)
        self.assertIsNotNone(pattern.search('Docker를 사용'))
        for text in ('dockerize', 'adocker', 'docker_2'):
            self.assertIsNone(pattern.search(text))
        self.assertIsNone(re.search(english_token('docker'), 'Docker를 사용'))

"""공통 기술 근거 판정: 경계, 기술별 문맥, 독립 기준, 긴 모델 출력 회귀."""
from copy import deepcopy
from pathlib import Path
import re
import subprocess
import sys
import unittest

from app.services.technology_mentions import applied_technologies, technology_pattern


class TechnologyPatternTests(unittest.TestCase):
    def test_both_sides_use_korean_and_english_word_boundaries(self):
        pattern = technology_pattern('Django', ('장고',))
        self.assertIsInstance(pattern, re.Pattern)
        for text in ('Django', 'django API', '`Django`로 구현', '장고 API', '(장고)',
                     'Django만 구현', '장고도 구현', 'Django로만 구현', '장고으로도 구현',
                     '장고로도 구현', '장고를 구현', '장고와 FastAPI', '장고에서 구현'):
            with self.subTest(text=text):
                self.assertIsNotNone(pattern.search(text))
        for text in ('냉장고 재고 API 구현', '냉장고 사용 필수', '장고기술 구현',
                     'Djangoish 구현', 'MyDjango 구현', 'Django2 구현', '_Django 구현',
                     'Django_filter 구현', 'django-filter 구현', '한글Django 구현',
                     'Django한글 구현', '장고만두 API 구현'):
            with self.subTest(text=text):
                self.assertIsNone(pattern.search(text))
        self.assertEqual(pattern.search('장고으로도 구현')[0], '장고')

    def test_java_does_not_match_javascript_in_either_language(self):
        pattern = technology_pattern('Java', ('자바',))
        for text in ('JavaScript 앱 구현', '자바스크립트로 구현', 'myjava', 'Java_17'):
            with self.subTest(text=text):
                self.assertIsNone(pattern.search(text))
        for text in ('Java로 API 구현', '자바만 사용', 'JAVA 17 서버'):
            with self.subTest(text=text):
                self.assertIsNotNone(pattern.search(text))

    def test_aliases_are_literal_and_owned_by_the_caller(self):
        self.assertIsNone(technology_pattern('django').search('장고 API'))
        for name, aliases, positive, negative in (
            ('Node.js', ('NodeJS',), 'NodeJS API', 'NodeXjs API'),
            ('C++', (), 'C++로 구현', 'C 언어 구현'),
            ('C#', (), 'C# API', 'C API'),
            ('sql server', ('Microsoft SQL Server', 'SQL 서버'), 'SQL 서버로 구현', '일반 server 구현'),
            ('spring boot', ('스프링 부트', 'springboot'), '스프링 부트로 구현', 'Spring 비교'),
        ):
            with self.subTest(name=name):
                pattern = technology_pattern(name, aliases)
                self.assertIsNotNone(pattern.search(positive))
                self.assertIsNone(pattern.search(negative))
        with self.assertRaises(ValueError):
            technology_pattern('', (' ',))


class AppliedTechnologiesTests(unittest.TestCase):
    def setUp(self):
        self.patterns = {
            name: technology_pattern(name, aliases)
            for name, aliases in (
                ('django', ('장고',)), ('fastapi', ('패스트API', '패스트 API')),
                ('flask', ('플라스크',)), ('redis', ('레디스',)),
                ('java', ('자바',)), ('javascript', ('자바스크립트',)),
                ('postgresql', ('postgres', '포스트그레스큐엘')),
            )
        }

    def assertApplied(self, text, expected):
        self.assertEqual(applied_technologies([text], self.patterns), expected)

    def test_positive_implementation_and_verification_from_pr_review(self):
        for text in (
            '인증되지 않은 요청을 차단하는 Django API 구현',
            'Django로 오류 없이 REST API 구현',
            'Django로 선택적 필터링 API 구현',
            'Django로 보안 사용자 인증 구현',
            'Django API 응답을 기대값과 비교해 확인',
            'Django API 응답이 기대값과 같지 않음을 확인',
            'Django 구현', 'Django REST API', 'Django API 응답 검증',
            'Django에서 JWT 권한 경계 검증', 'Django JWT 인증 테스트',
            '장고 API 구현', 'Django(장고) REST API 구현',
            '`Django`로 API 구현과 테스트', 'Ｄｊａｎｇｏ REST API 구현',
            '장고만 API 구현', '장고도 API 구현', '장고로만 API 구현', '장고으로도 API 구현',
            'Django 문서를 참고하여 API 구현',
        ):
            with self.subTest(text=text):
                self.assertApplied(text, {'django'})

    def test_substitutions_and_lists_preserve_only_the_chosen_side(self):
        for text, expected in (
            ('FastAPI를 쓰지 않고 Django로 구현', {'django'}),
            ('FastAPI 대신 Django로 REST API 구현', {'django'}),
            ('Django 대신에 FastAPI로 REST API 구현', {'fastapi'}),
            ('Flask, FastAPI를 제외하고 장고로 구현', {'django'}),
            ('FastAPI 없이 Django로 구현', {'django'}),
            ('Django 아닌 FastAPI 구현', {'fastapi'}),
            ('Implement Django instead of FastAPI', {'django'}),
            ('Use Django instead of FastAPI and Flask', {'django'}),
            ('Build a Django API without FastAPI', {'django'}),
            ('Django와 PostgreSQL로 API 구현', {'django', 'postgresql'}),
            ('Django/FastAPI API 구현', {'django', 'fastapi'}),
            ('Django 5.2 및 FastAPI API 구현', {'django', 'fastapi'}),
        ):
            with self.subTest(text=text):
                self.assertApplied(text, expected)

    def test_reference_comparison_and_introduction_do_not_borrow_other_implementation(self):
        for text, expected in (
            ('FastAPI로 구현하고 Django 문서 참고', {'fastapi'}),
            ('FastAPI 구현 (Django는 참고)', {'fastapi'}),
            ('Django 소개 영상 시청', set()),
            ('Django 비교', set()),
            ('Django는 비교하고 FastAPI를 구현', {'fastapi'}),
            ('Django와 비교한 FastAPI를 구현', {'fastapi'}),
            ('FastAPI 구현 후 Django 비교', {'fastapi'}),
            ('Django API 비교', set()),
            ('Django REST API 문서 참고', set()),
            ('Django 구현 방법 문서 참고', set()),
            ('Django와 FastAPI 비교', set()),
            ('Compare Django and FastAPI', set()),
            ('Django 구현, Redis는 후속 학습', {'django'}),
            ('Django 구현, FastAPI 문서 참고, Redis 캐시 연동', {'django', 'redis'}),
            ('Django 구현 (FastAPI 소개 (Redis 참고))', {'django'}),
        ):
            with self.subTest(text=text):
                self.assertApplied(text, expected)

    def test_previous_negative_core_cases_remain_negative(self):
        for text in (
            'Django 없이 FastAPI 구현', 'Django 대신 FastAPI 구현', 'Django 사용하지 않음',
            'Django 사용 안 함', 'Django 아닌 FastAPI 구현', 'Django 비교',
            'Django는 후속 학습', 'Django는 필수가 아님',
            'FastAPI 대신 Django 비교', '나중에 FastAPI 대신 Django로 구현',
            'FastAPI 대신 Django를 사용하지 않음', 'Using Django without FastAPI is optional',
            'Django API 구현하지 않음', 'Django API 미구현', '안 사용 Django',
        ):
            with self.subTest(text=text):
                self.assertNotIn('django', applied_technologies([text], self.patterns))

    def test_names_and_choices_alone_are_not_application_evidence(self):
        for text in ('Django', 'Django 선택', 'Django를 선택', 'Django 사용 기술 선택',
                     'Django 프레임워크', '장고', 'Django 5.2',
                     '냉장고 재고 API 구현', '냉장고 사용 필수'):
            with self.subTest(text=text):
                self.assertApplied(text, set())
        self.assertApplied('JavaScript 앱 구현', {'javascript'})
        self.assertApplied('자바스크립트로 구현', {'javascript'})
        self.assertApplied('Java API 구현', {'java'})

    def test_independent_comma_clauses_do_not_require_patterns_for_other_technologies(self):
        patterns = {'django': self.patterns['django']}
        for text in ('Django 구현, Redis는 후속 학습',
                     'Redis는 후속 학습, Django 구현',
                     'Django REST API, Redis는 참고',
                     'Django 문서 참고, Redis 캐시 구현'):
            with self.subTest(text=text):
                expected = set() if text.startswith('Django 문서') else {'django'}
                self.assertEqual(applied_technologies([text], patterns), expected)

    def test_substitution_excludes_fastapi_even_when_it_is_the_only_required_pattern(self):
        patterns = {'fastapi': self.patterns['fastapi']}
        for text in ('FastAPI 대신 Django로 구현',
                     'FastAPI를 쓰지 않고 Django로 구현',
                     'Implement Django instead of FastAPI',
                     'Use Django instead of FastAPI and Flask'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), set())

    def test_security_evidence_is_local_to_each_independent_unit(self):
        patterns = {'fastapi': self.patterns['fastapi']}
        for text in ('FastAPI에서 JWT 권한 경계 검증', 'FastAPI 권한 테스트 통과',
                     'FastAPI에서 권한 경계를 점검', 'FastAPI JWT 보안 검증 실습'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), {'fastapi'})
        self.assertEqual(applied_technologies(['JWT 권한 경계 검증 실습'], patterns), set())
        self.assertEqual(applied_technologies(['FastAPI 소개 영상 확인'], patterns), set())
        self.assertEqual(applied_technologies(['FastAPI 비교해 확인'], patterns), set())
        self.assertEqual(applied_technologies(['FastAPI REST API 구현 실습',
                                               'JWT 권한 경계 검증 실습'], patterns), {'fastapi'})
        replacement = 'FastAPI 대신 Django에서 JWT 권한 경계 검증'
        self.assertEqual(applied_technologies([replacement], self.patterns), {'django'})
        self.assertEqual(applied_technologies([replacement], patterns), set())
        self.assertEqual(applied_technologies([replacement], {'django': self.patterns['django']}), {'django'})

    def test_criteria_are_independent_and_never_mutate_input(self):
        texts = ['Django', 'API 구현', 'FastAPI REST API', 'Django 비교', 'Redis 캐시 연동']
        before, patterns_before = deepcopy(texts), dict(self.patterns)
        self.assertEqual(applied_technologies(texts, self.patterns), {'fastapi', 'redis'})
        self.assertEqual(texts, before)
        self.assertEqual(self.patterns, patterns_before)
        self.assertEqual(applied_technologies([], self.patterns), set())
        self.assertEqual(applied_technologies(['Django API 구현'], {}), set())
        self.assertEqual(applied_technologies(iter(['Django 비교', 'Django API 구현']), self.patterns), {'django'})
        self.assertEqual(applied_technologies(['Django는 후속 학습', 'Django API 구현'], self.patterns), {'django'})

    def test_long_outputs_finish_in_a_killable_process_without_a_length_fail_safe(self):
        # 스레드 제한시간으로는 정규식의 GIL 점유를 끊을 수 없다.
        script = """
from app.services.technology_mentions import applied_technologies, technology_pattern
patterns = {name: technology_pattern(name) for name in ('django', 'fastapi')}
for count in (5000, 20000):
    repeated = 'django 비교 ' * count
    assert applied_technologies([repeated], patterns) == set()
    assert applied_technologies([repeated + 'Django REST API'], patterns) == {'django'}
    assert applied_technologies(['응답 기준 ' * count + 'Django REST API'], patterns) == {'django'}
    assert applied_technologies(['Django and ' * count + 'FastAPI API 구현'], patterns) == {'django', 'fastapi'}
    assert applied_technologies(['(' * count + 'Django 비교'], patterns) == set()
"""
        subprocess.run([sys.executable, '-B', '-c', script],
                       cwd=Path(__file__).resolve().parents[1], timeout=5, check=True)

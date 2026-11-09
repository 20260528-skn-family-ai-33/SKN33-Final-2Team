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

    def test_work_outside_a_verb_list_counts_unless_it_is_excluded(self):
        for name, text in (
            ('docker', 'Docker 이미지 빌드'), ('python', 'Python으로 CSV 파일 파싱'),
            ('python', 'Python으로 데이터 분석'), ('python', 'Python 크롤러'),
            ('python', 'Python 기본 문법 익히기'), ('pandas', 'pandas로 데이터 전처리'),
            ('pytorch', 'PyTorch로 분류 모델 학습'), ('pytorch', 'Train a PyTorch model'),
            ('langchain', 'LangChain으로 RAG 챗봇'), ('django', 'Django 게시판'),
            ('django', 'Django 모델과 뷰 설계'), ('django', 'Django 기반 시스템'),
            ('django', 'REST API 구현 (Django)'), ('django', 'REST API를 구현하는 Django'),
            ('django', '구현 기술: Django'), ('django', 'Django라는 프레임워크로 게시판 작성'),
            ('react', 'React 대시보드 화면'), ('react', 'React 컴포넌트'),
            ('fastapi', 'FastAPI 엔드포인트 3개'), ('redis', 'Redis 캐싱'),
            ('postgresql', 'PostgreSQL 스키마 설계'), ('git', 'Git 브랜치 관리'),
            ('kubernetes', 'Kubernetes 클러스터 운영'), ('sql', 'SQL 조인으로 매출 집계'),
            ('django', 'Django API 구현 및 Swagger 문서'), ('django', 'Django API 구현 및 결과 검토'),
            ('django', 'Django로 구현한 코드 검토'), ('django', 'Django 영상 업로드 서버'),
            ('django', 'Django, Celery로 비동기 작업 구현'), ('python', 'Python Flask 앱 컨테이너화'),
        ):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], {name: technology_pattern(name)}), {name})

    def test_scope_predicates_exclude_the_technology_but_not_its_detail(self):
        patterns = {'django': self.patterns['django']}
        for text in ('Django 구현 없이 FastAPI로 API 작성', 'Django 빼고 FastAPI 구현',
                     'Django를 대체하는 FastAPI 구현', 'Django에서 FastAPI로 마이그레이션 구현',
                     'Migrate from Django to FastAPI', 'Django 구현은 제외', 'Django 구현은 하지 않는다',
                     'Django API 구현은 범위 밖', 'Django 구현은 다음 단계', 'Django 구현을 다음 단계로 미룸',
                     'Django 서버는 다루지 않음', 'Django API는 필요 없음', 'Django, Celery는 제외',
                     'Django 구현 개요', 'Django 튜토리얼 문서'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), set())
        for text in ('Django로 구현하되 배포는 제외', 'Django로 저장은 제외하고 조회 API 구현',
                     'Django로 저장 없이 조회 API 구현', 'Django로 권한이 필요 없는 공개 API 구현',
                     'Django API 구현 및 배포는 다음 단계', 'Django로 비로그인 사용자는 제외한 API 작성'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), {'django'})

    def test_excluding_a_feature_keeps_the_technology_but_excluding_the_technology_does_not(self):
        patterns = {'django': self.patterns['django']}
        for text in ('Django로 관리자 API는 제외하고 공개 API 구현', 'Django로 관리자 API는 제외하고, 공개 API 구현',
                     'Django로 관리자 API를 제외하고 공개 API를 구현한다', 'Django로 관리자 API는 구현하지 않고 공개 API 구현',
                     'Django로 관리자 API는 후속으로 미루고 공개 API 구현', 'Django로 관리자 API는 다음 단계로 넘기고 공개 API 구현',
                     'Django로 결제 기능은 구현하지 않고 조회 API만 구현', 'Django 관리자 API는 제외하고 공개 API 구현',
                     'Django로 Admin API는 제외하고 Public API 구현'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), {'django'})
        for text in ('Django는 제외하고 FastAPI로 공개 API 구현', 'Django를 제외하고 FastAPI로 공개 API 구현',
                     'Django로 관리자 API는 제외하고 FastAPI로 공개 API 구현',
                     'Django로 관리자 API는 구현하지 않고 FastAPI를 사용해 공개 API 구현',
                     'Django API는 제외하고 공개 API 구현', 'Django 구현은 제외하고 공개 API 구현',
                     'Django 서버 구현은 제외하고 공개 API 구현', 'Django 프레임워크 사용은 제외하고 공개 API 구현',
                     'Django로 API는 구현하지 않고 공개 API 구현', 'Django로 구현하지 않고 공개 API 구현',
                     'Django와 FastAPI는 제외하고 공개 API 구현', 'Django와 FastAPI는 구현하지 않고 공개 API 구현',
                     'Django 비교는 제외하고 공개 API 구현', 'Django 관리자 API는 제외',
                     'Django는 후속 학습으로 미루고 공개 API 구현', 'Django API는 후속으로 미루고 공개 API 구현'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), set())

    def test_unadopted_and_candidate_mentions_are_not_application(self):
        patterns = {'django': self.patterns['django']}
        for text in ('Django는 도입하지 않음', 'Django 도입하지 않음', 'Django는 채택하지 않음', 'Django는 포함하지 않음',
                     'Django는 학습하지 않음', 'Django API 안 씀', 'Django 없음', 'Django 미도입', 'Django 미포함',
                     'Django 사용 금지', 'Django 도입 불가', 'Django 도입 계획 없음',
                     'Django는 프로젝트에 도입하지 않음', 'Django를 도입하지 않는 FastAPI 구현',
                     'Django was not adopted', 'Do not adopt Django', 'Django will not be used',
                     '후보 기술 목록: Django', 'Django 후보', 'Django는 후보로 둠', 'Django 후보 기술', 'Django 대안'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), set())
        for text in ('Django로 오류가 발생하지 않도록 구현', 'Django는 권한 없는 요청을 허용하지 않음',
                     'Django로 저장하지 않는 조회 API 구현', 'Django로 후보 추천 API 구현',
                     'Django로 후보 필터링', 'Django 게시글 목록', 'Django 도입', 'Django 도입 후 API 구현',
                     '오류 없는 Django 서버', 'Django 로그 수집'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), {'django'})

    def test_parenthesis_condition_applies_to_its_named_target(self):
        patterns = {'django': self.patterns['django']}
        for text in ('Django API 구현 (후속 학습)', 'Django API 구현(후속 학습)', 'Django (선택 사항)로 API 구현',
                     'Django API 구현 (선택)', 'Django API 구현 (나중에 구현)', 'Django API 구현 (참고)',
                     'Django API 구현 (구현 안 함)', 'Django API 구현 (optional)', '(후속) Django API 구현'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), set())
        for text in ('Django API 구현 (Redis는 후속 학습)', 'Django API 구현 (레디스는 후속 학습)',
                     'Django API 구현 (ORM 심화는 후속 학습)', 'Django API 구현 (선택적 필터링 포함)',
                     'Django API 구현 (참고 자료 제공)', 'Redis 캐시 (선택 사항), Django API 구현'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), {'django'})
        self.assertApplied('Django API 구현 (Redis는 후속 학습)', {'django'})
        self.assertApplied('Django 구현, FastAPI 연동 (후속)', {'django'})

    def test_outer_work_applies_to_a_bare_parenthesis_but_not_a_reference(self):
        patterns = {'django': self.patterns['django']}
        for text in ('REST API 구현 (Django)', 'JWT 인증 구현 (Django)', 'CRUD API 구현 (Django 5.2)',
                     'Build a REST API (Django)'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), {'django'})
        for text in ('FastAPI 구현 (Django는 참고)', 'FastAPI 비교 (Django)',
                     'FastAPI로 REST API 구현. 후보 기술 목록 (Django)', 'FastAPI로 REST API 구현 (Django)',
                     'FastAPI로 구현. (Django)', 'FastAPI로 구현, 후보 (Django)'):
            with self.subTest(text=text):
                self.assertEqual(applied_technologies([text], patterns), set())

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
    assert applied_technologies(['Django ' + 'test' * count + '!a'], patterns) == {'django'}
    assert applied_technologies(['Django ' + '영상 ' * count], patterns) == set()
    assert applied_technologies(['Django, ' * count + '비교'], patterns) == set()
    assert applied_technologies(['Django ' + '가' * count + '지'], patterns) == {'django'}
    assert applied_technologies(['구현 (Django) ' * count], patterns) == {'django'}
    assert applied_technologies(['Django ' + '후보 ' * count], patterns) == set()
    assert applied_technologies(['Django API 구현 (' + '후속 ' * count + 'x)'], patterns) == {'django'}
    assert applied_technologies(['Django 구현 (후속) ' * count], patterns) == set()
"""
        subprocess.run([sys.executable, '-B', '-c', script],
                       cwd=Path(__file__).resolve().parents[1], timeout=5, check=True)

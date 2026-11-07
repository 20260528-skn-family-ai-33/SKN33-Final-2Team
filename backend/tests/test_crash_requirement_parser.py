"""필수 기술의 명시적 표현과 선택·부정·후속 범위를 구분한다."""
from copy import deepcopy
import unittest
from app.services.crash_requirements import required_technologies, validate_core_requirements


class CrashRequirementParserTests(unittest.TestCase):
    def test_explicit_requirements_and_aliases(self):
        cases = {
            'Django 사용 필수': {'django'},
            'Django(장고) 사용 필수': {'django'},
            '`Django` 사용 필수': {'django'},
            'Spring Boot 사용 필수': {'spring boot'},
            'Microsoft SQL Server 사용 필수': {'sql server'},
            'Django/FastAPI 사용 필수': {'django', 'fastapi'},
            'Django and FastAPI required': {'django', 'fastapi'},
            '반드시 Django로 구현하고 Redis는 후속 학습': {'django'},
            'Django를 반드시 사용': {'django'},
            '반드시 Django로 구현': {'django'},
            '장고를 반드시 사용': {'django'},
            'must use Django': {'django'},
            'Django is required': {'django'},
            '필수 기술: Docker, PostgreSQL': {'docker', 'postgresql'},
            'Django와 PostgreSQL 사용 필수': {'django', 'postgresql'},
            '필수 기술: Node.js, C++, C#': {'node.js', 'c++', 'c#'},
            '사용자 도구 Temporal 사용 필수': {'temporal'},
            'FastAPI는 필수, Django는 비교만': {'fastapi'},
            'Django는 필수가 아니고 FastAPI 사용 필수': {'fastapi'},
            'Django 사용 필수, ORM 심화는 후속 학습': {'django'},
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(required_technologies({'goal': text}), expected)

    def test_optional_comparison_and_negation_are_not_requirements(self):
        for text in ('FastAPI 구현 후 Django 비교', 'Django는 필수가 아닙니다',
                     'Django 반드시 사용하지 않는다', 'Django는 반드시 쓰지 않는다', 'Django 필수 기술이 아니다', 'Django 사용 필수 아님', 'Django is not required', 'Django not required', '필수 기술 아님: Django',
                     'Django는 선택 사항', 'must use Django later', 'Django 없이 FastAPI 구현'):
            with self.subTest(text=text):
                self.assertEqual(required_technologies({'goal': text}), set())

    def test_sources_exclude_profile_and_model_targets(self):
        handoff = {'goal': 'API 개발', 'profile': {'workDesc': 'Java 필수'},
                   'skillDetails': [{'application': 'Django 필수'}],
                   'details': {'etc': 'Docker 필수'}}
        self.assertEqual(required_technologies(handoff, {'wish': 'PostgreSQL 필수', 'removeActs': ['Redis 필수']}),
                         {'docker', 'postgresql'})

    def test_only_positive_core_counts_and_boundaries_are_exact(self):
        for text in ('Django 없이 FastAPI 구현', 'Django 대신 FastAPI 구현', 'Django 사용하지 않음',
                     'Django는 비교하고 FastAPI를 구현', 'Django와 비교한 FastAPI를 구현',
                     'Django 사용 안 함', 'Django 아닌 FastAPI 구현', 'Django 비교', 'Django는 후속 학습', 'Django는 필수가 아님'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_core_requirements([{'coreOutcome': text}], {'goal': 'Django 사용 필수'})
        for target in ('JavaScript 앱 구현', '자바스크립트로 구현'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_core_requirements([{'coreOutcome': target}], {'goal': 'Java 사용 필수'})
        with self.assertRaises(ValueError):
            validate_core_requirements([{'coreOutcome': '일반 server 구현'}], {'goal': 'Microsoft SQL Server 사용 필수'})
        validate_core_requirements([{'coreOutcome': 'Django 구현, Redis는 후속 학습'}], {'goal': 'Django 필수'})

    def test_application_and_followup_do_not_satisfy_requirement(self):
        with self.assertRaises(ValueError):
            validate_core_requirements([{'application': 'Django 구현', 'coreOutcome': 'API 구현',
                                         'followUpScope': ['Django 활용']}], {'goal': 'Django 필수'})

    def test_requirement_can_be_met_once_across_multiple_skills_without_mutation(self):
        rows = [{'name': 'SQL', 'coreOutcome': 'SQL 조인'},
                {'name': '웹', 'coreOutcome': '장고 API 구현', 'coreCriteria': ['실행 결과 확인'],
                 'followUpScope': ['Django ORM 성능 최적화']}]
        before = deepcopy(rows)
        validate_core_requirements(rows, {'goal': 'Django 사용 필수'})
        self.assertEqual(rows, before)

"""필수 기술의 명시적 표현과 선택·부정·후속 범위를 구분한다."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import unittest
from app.services.crash_requirements import (
    MAX_REQUIREMENT_CHARS, RequirementTextTooLong, required_technologies, validate_core_requirements,
)


class CrashRequirementParserTests(unittest.TestCase):
    def test_long_technology_lists_finish_with_and_without_an_obligation(self):
        # 별도 프로세스여야 정규식 회귀로 GIL이 막혀도 테스트 자체를 중단할 수 있다.
        script = """
from app.services.crash_requirements import required_technologies
names = 'django and ' * 1000 + 'FastAPI'
assert required_technologies({}, {'wish': names}) == set()
assert required_technologies({}, {'wish': names + ' required'}) == {'django', 'fastapi'}
"""
        subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                       timeout=5, check=True)

    def test_versions_preserve_the_technology_but_are_not_separate_requirements(self):
        for text, expected in (
            ('Django 5.2 사용 필수', {'django'}),
            ('Python 3.12 및 Django 5.2는 필수', {'python', 'django'}),
            ('필수 기술: Spring Boot 3.4, Node.js v22, C++', {'spring boot', 'node.js', 'c++'}),
            ('django-filter 24.3 required', {'django-filter'}),
            ('Django 5.2는 필수가 아님', set()),
            ('Python 3.12로 구현 후 Django 5.2 비교', set()),
        ):
            with self.subTest(text=text):
                self.assertEqual(required_technologies({'goal': text}), expected)

    def test_input_budget_includes_nested_requirements_and_does_not_truncate_the_end(self):
        wish = 'Django 필수'
        project = {'details': {'scope': '가' * (MAX_REQUIREMENT_CHARS - len(wish))},
                   'profile': {'workDesc': '가' * MAX_REQUIREMENT_CHARS}}
        self.assertEqual(required_technologies(project, {'wish': wish}), {'django'})
        with self.assertRaises(RequirementTextTooLong):
            required_technologies(project, {'wish': wish + '!'})

    def test_only_the_chosen_side_of_a_substitution_counts_as_core(self):
        for text, chosen, excluded in (
            ('FastAPI 대신 Django로 REST API 구현', 'Django', ['FastAPI']),
            ('Django 대신에 FastAPI로 REST API 구현', 'FastAPI', ['Django']),
            ('Flask, FastAPI를 제외하고 장고로 구현', 'Django', ['Flask', 'FastAPI']),
            ('FastAPI 없이 Django로 구현', 'Django', ['FastAPI']),
            ('Implement Django instead of FastAPI', 'Django', ['FastAPI']),
            ('Use Django instead of FastAPI and Flask', 'Django', ['FastAPI', 'Flask']),
        ):
            rows = [{'coreOutcome': text}]
            with self.subTest(text=text):
                validate_core_requirements(rows, {'goal': f'{chosen} 사용 필수'})
                for name in excluded:
                    with self.assertRaisesRegex(ValueError, name.casefold()):
                        validate_core_requirements(rows, {'goal': f'{name} 사용 필수'})
        for text in ('FastAPI 대신 Django 비교', '나중에 FastAPI 대신 Django로 구현',
                     'FastAPI 대신 Django를 사용하지 않음', 'Using Django without FastAPI is optional'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'django'):
                validate_core_requirements([{'coreCriteria': [text]}], {'goal': 'Django 필수'})

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

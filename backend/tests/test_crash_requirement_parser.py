"""필수 기술의 명시적 표현과 선택·부정·후속 범위를 구분한다."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import unittest
from app.services.crash_requirements import (
    MAX_REQUIREMENT_CHARS, RequirementTextTooLong, prompt_requirements, required_technologies,
    validate_core_requirements,
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
            ('Python3 사용 필수', {'python'}),
            ('python3.12 사용 필수', {'python'}),
            ('Python 3.12 이상 필수', {'python'}),
            ('Django 5.x 필수', {'django'}),
            ('Python 3.12 및 Django 5.2는 필수', {'python', 'django'}),
            ('필수 기술: Spring Boot 3.4, Node.js v22, C++', {'spring boot', 'node.js', 'c++'}),
            ('django-filter 24.3 required', {'django-filter'}),
            ('Django 5.2는 필수가 아님', set()),
            ('Python 3.12로 구현 후 Django 5.2 비교', set()),
        ):
            with self.subTest(text=text):
                self.assertEqual(required_technologies({'goal': text}), expected)

    def test_required_versions_and_aliases_accept_the_same_core_technology(self):
        for requirement, expected, core in (
            ('Python3 사용 필수', 'python', 'Python으로 로그 파서 구현'),
            ('python3.12 사용 필수', 'python', 'Python으로 로그 파서 구현'),
            ('Python 3.12 이상 필수', 'python', 'python3.12로 로그 파서 구현'),
            ('Django 5.x 필수', 'django', 'Django로 REST API 구현'),
            ('Django 프레임워크 사용 필수', 'django', '장고로 REST API 구현'),
            ('Django REST Framework 필수', 'django rest framework', 'DRF로 REST API 구현'),
            ('DRF(Django REST Framework) 필수', 'django rest framework', 'Django REST Framework로 API 구현'),
            ('Oracle DB 필수', 'oracle db', 'Oracle DB로 데이터 저장 구현'),
            ('NodeJS 사용 필수', 'node.js', 'Node.js로 HTTP 서버 구현'),
            ('Node.js 사용 필수', 'node.js', 'NodeJS로 HTTP 서버 구현'),
            ('스프링부트 사용 필수', 'spring boot', 'Spring Boot로 REST API 구현'),
            ('Temporal 사용 필수', 'temporal', 'Temporal로 워크플로 구현'),
        ):
            with self.subTest(requirement=requirement):
                handoff = {'goal': requirement}
                self.assertEqual(required_technologies(handoff), {expected})
                self.assertIn(expected, prompt_requirements(handoff))
                validate_core_requirements([{'coreOutcome': core}], handoff)
                with self.assertRaisesRegex(ValueError, expected):
                    validate_core_requirements([{'coreOutcome': '일반 API 구현'}], handoff)

    def test_prefix_requirement_is_not_cancelled_by_another_technology(self):
        for text in ('must use Django instead of FastAPI',
                     '반드시 Django로 구현하되 Redis는 선택 사항',
                     'must use Django without FastAPI'):
            with self.subTest(text=text):
                handoff = {'goal': text}
                self.assertEqual(required_technologies(handoff), {'django'})
                self.assertIn('django', prompt_requirements(handoff))
                validate_core_requirements([{'coreOutcome': 'Django로 API 구현'}], handoff)
                with self.assertRaisesRegex(ValueError, 'django'):
                    validate_core_requirements([{'coreOutcome': 'FastAPI로 API 구현'}], handoff)

    def test_alternatives_require_one_positive_core_and_prompt_preserves_the_choice(self):
        for text in ('Django 또는 FastAPI 필수', 'Django or FastAPI required',
                     'Django나 FastAPI 필수', '장고나 FastAPI 필수',
                     '필수 기술: Django 또는 FastAPI', 'must use Django OR FastAPI'):
            with self.subTest(text=text):
                handoff = {'goal': text}
                self.assertEqual(required_technologies(handoff), {'django', 'fastapi'})
                self.assertIn('(django 또는 fastapi 중 하나)', prompt_requirements(handoff))
                for chosen in ('Django', 'FastAPI'):
                    validate_core_requirements([{'coreOutcome': f'{chosen}로 API 구현'}], handoff)
                with self.assertRaisesRegex(ValueError, 'django.*또는.*fastapi'):
                    validate_core_requirements([{'coreOutcome': 'Flask로 API 구현'}], handoff)
                with self.assertRaises(ValueError):
                    validate_core_requirements([{'coreOutcome': 'Django와 FastAPI 비교',
                                                 'followUpScope': ['Django로 구현']}], handoff)

    def test_and_lists_still_require_every_item_alongside_alternatives(self):
        for text in ('Django 또는 FastAPI 및 Redis 필수', '필수 기술: Django or FastAPI, Redis'):
            with self.subTest(text=text):
                handoff = {'goal': text}
                self.assertEqual(required_technologies(handoff), {'django', 'fastapi', 'redis'})
                for chosen in ('Django', 'FastAPI'):
                    rows = [{'coreOutcome': f'{chosen}로 API 구현'}, {'coreCriteria': ['Redis로 캐시 구현']}]
                    validate_core_requirements(rows, handoff)
                    with self.assertRaisesRegex(ValueError, 'redis'):
                        validate_core_requirements(rows[:1], handoff)
                with self.assertRaisesRegex(ValueError, 'django.*또는.*fastapi'):
                    validate_core_requirements([{'coreOutcome': 'Redis로 캐시 구현'}], handoff)
        for text in ('Django and FastAPI required', 'Django/FastAPI 사용 필수',
                     '필수 기술: Django, FastAPI', 'Django와 FastAPI 사용 필수'):
            with self.subTest(text=text):
                handoff = {'goal': text}
                validate_core_requirements([{'coreOutcome': 'Django와 FastAPI로 API 구현'}], handoff)
                with self.assertRaisesRegex(ValueError, 'fastapi'):
                    validate_core_requirements([{'coreOutcome': 'Django로 API 구현'}], handoff)

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
                     'Django를 반드시 쓸 필요는 없다', 'Django가 꼭 필요한 건 아니에요',
                     'Django는 필수 조건은 아니에요', '반드시 Django를 쓸 필요는 없다',
                     'Django는 선택 사항', 'must use Django later', 'Django 없이 FastAPI 구현'):
            with self.subTest(text=text):
                self.assertEqual(required_technologies({'goal': text}), set())

    def test_ordinary_words_and_refrigerator_are_not_technologies(self):
        for text in ('An API key is required', '냉장고 사용 필수', '반드시 냉장고 사용'):
            with self.subTest(text=text):
                self.assertEqual(required_technologies({'goal': text}), set())
                self.assertEqual(prompt_requirements({'goal': text}), '')
        with self.assertRaisesRegex(ValueError, 'django'):
            validate_core_requirements([{'coreOutcome': '냉장고 재고 API 구현'}], {'goal': '장고 사용 필수'})

    def test_sources_exclude_profile_and_model_targets(self):
        handoff = {'goal': 'API 개발', 'profile': {'workDesc': 'Java 필수'},
                   'skillDetails': [{'application': 'Django 필수'}],
                   'details': {'etc': 'Docker 필수'}}
        self.assertEqual(required_technologies(handoff, {'wish': 'PostgreSQL 필수', 'removeActs': ['Redis 필수']}),
                         {'docker', 'postgresql'})

    def test_user_notes_key_supersedes_only_legacy_etc_without_mutating_handoff(self):
        for notes in ([], None, '', ['Redis 필수']):
            handoff = {'goal': 'FastAPI로 API 구현', 'userNotes': notes,
                       'details': {'etc': 'Django 사용 필수', 'database': 'PostgreSQL 필수',
                                   'scope': {'deployment': 'Docker 필수'}}}
            before = deepcopy(handoff)
            expected = {'postgresql', 'docker'} | ({'redis'} if notes else set())
            with self.subTest(notes=notes):
                self.assertEqual(required_technologies(handoff), expected)
                self.assertNotIn('django', prompt_requirements(handoff))
                self.assertEqual(handoff, before)
        self.assertEqual(required_technologies({'details': {'etc': 'Django 필수'}}), {'django'})

    def test_ignored_etc_does_not_consume_the_current_requirement_budget(self):
        handoff = {'userNotes': ['Django 필수'], 'details': {'etc': '가' * MAX_REQUIREMENT_CHARS}}
        self.assertEqual(required_technologies(handoff), {'django'})

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

    def test_previous_handoff_exempts_existing_obligations_including_legacy_missing_core(self):
        previous = {'goal': 'Django 필수', 'userNotes': ['Redis 필수']}
        handoff = {'goal': '장고 사용 필수', 'userNotes': ['Redis 필수'], 'hours': 2}
        rows = [{'coreOutcome': 'FastAPI로 API 구현'}]
        before = deepcopy((rows, handoff, previous))
        validate_core_requirements(rows, handoff, {'wish': '주 2시간으로 변경', 'removeActs': ['Django 필수']},
                                   previous_handoff=previous)
        validate_core_requirements([], handoff, previous_handoff=previous)
        self.assertEqual((rows, handoff, previous), before)
        with self.assertRaisesRegex(ValueError, 'django'):
            validate_core_requirements(rows, handoff)
        with self.assertRaisesRegex(ValueError, 'django'):
            validate_core_requirements(rows, handoff, previous_handoff={})

    def test_previous_handoff_still_validates_new_singletons_and_direct_rerequirements(self):
        previous = {'goal': 'Django 필수'}
        handoff = {'goal': 'Django 필수', 'userNotes': ['Redis 필수']}
        rows = [{'coreOutcome': 'Redis로 캐시 구현'}]
        validate_core_requirements(rows, handoff, previous_handoff=previous)
        with self.assertRaisesRegex(ValueError, 'redis'):
            validate_core_requirements([], handoff, previous_handoff=previous)
        for request in ('Django 필수', {'wish': '장고를 반드시 사용'}, {'quick': 'Django 필수'}):
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, 'django'):
                validate_core_requirements(rows, handoff, request, previous_handoff=previous)

    def test_previous_handoff_compares_obligation_groups_instead_of_flattened_candidates(self):
        previous = {'goal': 'Django 또는 FastAPI 필수'}
        unchanged = {'goal': 'FastAPI or Django required'}
        validate_core_requirements([], unchanged, previous_handoff=previous)
        with self.assertRaisesRegex(ValueError, 'django.*또는.*fastapi'):
            validate_core_requirements([], unchanged, {'wish': 'Django 또는 FastAPI 필수'},
                                       previous_handoff=previous)
        # 후보 집합이 같아도 OR에서 AND로 바뀌면 두 의무 모두 새로 검증한다.
        conjunction = {'goal': 'Django and FastAPI required'}
        with self.assertRaisesRegex(ValueError, 'fastapi'):
            validate_core_requirements([{'coreOutcome': 'Django로 API 구현'}], conjunction,
                                       previous_handoff=previous)
        # 이미 알려진 후보로 구성된 새 대안도 저장된 그룹과 다르면 검사한다.
        for old, new in (
            (conjunction, previous),
            (previous, {'goal': 'Django 또는 Redis 필수'}),
        ):
            with self.subTest(old=old, new=new), self.assertRaises(ValueError):
                validate_core_requirements([], new, previous_handoff=old)

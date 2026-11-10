from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from app import catalog
from app.agents import roadmap
from app.agents.resource_recommendations import recommend_resources
from app.agents.roadmap_revision import revision
from app.routers import preassessment as api
from app.services import activity_selection, drafts
from app.services.course_recommendations import compatible_recommendations
from app.services.resource_rag import version_for
from test_recommendation_suitability import WEB
from test_resource_followups import course


class CachedSelectionTests(TestCase):
    def setUp(self):
        self.rec = {'id': 'old', 'skills': [{'name': 'SQL', 'courses': [{'id': 'sql'}, {'id': 'unused'}],
                                            'books': [{'id': 'book'}]}], 'retrieval': {'version': 'old'}}
        self.choices = {'SQL': {'course': 'sql', 'books': ['book'], 'enabled': True}}
        self.items = {'sql': {'type': 'course', 'usable': True}, 'book': {'type': 'book', 'usable': True}}
        self.saved = {'recommendations': self.rec, 'resourceChoices': self.choices}

    def test_preserves_choices_on_rule_change_if_selected_resources_are_usable(self):
        with patch.object(catalog, 'items', return_value=self.items):
            self.assertIsNotNone(compatible_recommendations(self.saved, 'current'))
        self.assertEqual(self.saved['resourceChoices'], self.choices)

    def test_invalidates_selected_course_or_book_even_on_current_rule_version(self):
        for version in ('old', 'current'):
            for rid in self.items:
                for item in (None, dict(self.items[rid], usable=False), {'type': 'cert', 'usable': True}):
                    with self.subTest(version=version, rid=rid, item=item):
                        items = dict(self.items, **{rid: item})
                        with patch.object(catalog, 'items', return_value=items):
                            self.assertIsNone(compatible_recommendations(self.saved, version))

    def test_deleted_choice_triggers_fresh_recommendations_through_existing_route(self):
        draft = {'chosen': 'A2', 'gen': {'options': {'A2': {'id': 'A2'}}}}
        scoped = {**self.saved, 'generationId': 'g', 'selection': {'skills': [{'name': 'SQL'}]},
                  'skillOrder': ['SQL'], 'courseRecommendations': {'A2': self.saved}}
        self.rec['retrieval']['version'] = version_for('A2')
        updated = {'generationId': 'g', 'recommendations': {'id': 'new'}}
        with patch.object(api, 'recommendation_context', return_value=scoped), \
             patch.object(drafts, '_row', return_value={'draft_choices': {'draft': draft}}), \
             patch.object(catalog, 'items', return_value={'book': self.items['book']}), \
             patch.object(api.db, 'tx', return_value=nullcontext(Mock())), \
             patch.object(api, 'generation_guard', return_value=nullcontext()), \
             patch.object(api, 'course_input', return_value={'id': 'A2'}), \
             patch.object(api.runtime, 'context', return_value=Mock(live=True)), \
             patch.object(api, 'recommend_from_catalog', return_value={}) as recommend, \
             patch.object(api, 'save_recommendations', return_value=updated):
            result = api.generate_recommendations.__wrapped__(uuid4(), Mock(id=1), 'A2')
        recommend.assert_called_once()
        self.assertIsNone(recommend.call_args.args[1]['recommendations'])
        self.assertEqual(result['recommendations']['id'], 'new')


class LearningTargetPersistenceTests(TestCase):
    def make_plan(self, pid, target):
        name = target['name']
        choices = {name: {'course': None, 'books': [], 'enabled': True}}
        saved = {'generationId': 'g', 'project': {'goal': '주문 파이프라인 구현'},
                 'recommendations': {'id': 'r', 'skills': [{'name': name, 'courses': [], 'books': []}]},
                 'skillOrder': [name], 'selection': {'skills': [target]}, 'resourceChoices': choices}
        handoff = {'key': 'h', 'goal': saved['project']['goal'], 'skillOrder': [name],
                   'skillDetails': [target], 'prefs': {'weeklyHours': 4}, 'startStage': 1}
        option = {'id': pid, 'learningSkills': [target], 'learningSkillsVersion': 'v1',
                  'learningSkillsKey': 'key', 'learningSkillSelection': [{'name': name, 'enabled': True}],
                  'weeklyHours': 4}
        draft = {'chosen': pid, 'goal': handoff['goal'], 'handoff': handoff, 'gen': {'options': {pid: option}}}
        task = {'stage': 3, 'title': '증분 모델 구현', 'res': None, 'hours': 2,
                'how': '실행 결과 확인', 'skill': name, 'skills': [name]}
        def generate(_, payload):
            self.assertEqual(payload['skillTargets'][name], target)
            return {'skillSummaries': {name: ['모델 작성', '실행 확인', '결과 비교']}, 'acts': [task]}
        with patch.object(catalog, 'items', return_value={}), patch.object(catalog, 'skill_names', return_value=[name]):
            proposal = activity_selection.propose(saved, draft, generate, 'openai')
            saved['activityProposal'] = proposal
            selection = activity_selection.selection_option(saved, draft, proposal['selectedIds'])
            plan = roadmap.build_plan(selection, {'start': 1, 'hours': 4}, draft['goal'])
        for field in roadmap.LEARNING_SKILL_FIELDS:
            self.assertEqual(plan['def'][field], option[field])
            if isinstance(option[field], list):
                self.assertIsNot(plan['def'][field], option[field])
        return plan, handoff, task

    def revise(self, pid, plan, handoff, task):
        payloads = []
        def model(ctx, system, payload, **kwargs):
            payloads.append(deepcopy(payload))
            return {'acts': [dict(task, key=plan['acts'][0]['id'])], 'summary': '시간 조정'}
        inp = {'pid': pid, 'plan': plan, 'handoff': handoff, 'changes': {'weeklyHours': 6}}
        before = deepcopy(inp)
        with patch.object(roadmap, '_sys', return_value=revision(pid)), \
             patch.object(catalog, 'skill_names', return_value=[task['skill']]), \
             patch.object(roadmap, '_catalog_payload', side_effect=lambda pid, payload, *args: payload), \
             patch.object(roadmap.rt, 'llm_json', side_effect=model), \
             patch.object(roadmap.rt, 'run', side_effect=lambda ctx, name, task, data, mock, api, **kw: api(None)):
            out = roadmap.revise(SimpleNamespace(mode='openai'), inp)
        self.assertEqual(inp, before)
        return payloads[0]['skillTargets'], out

    def test_crash_and_challenge_targets_survive_activity_selection_and_revision(self):
        common = {'name': 'ETL', 'application': 'dbt 모델 작성'}
        targets = {'A2': dict(common, coreOutcome='증분 모델', coreCriteria=['증분 실행 확인'],
                              followUpScope=['품질 테스트 확장']),
                   'A3': dict(common, targetOutcome='주문 처리 검증 모델',
                              completionCriteria=['기준선 비교', '실패와 한계 검증'])}
        for pid, target in targets.items():
            with self.subTest(pid=pid):
                plan, handoff, task = self.make_plan(pid, target)
                # 확정 정의가 있으면 이전 handoff의 다른 문구가 덮어쓰지 않는다.
                handoff['skillDetails'] = [dict(target, application='이전 범위')]
                sent, revised = self.revise(pid, plan, handoff, task)
                self.assertEqual(sent, [target])
                self.assertEqual(revised['learningSkills'], [target])

    def test_legacy_plan_recovers_only_matching_valid_saved_targets(self):
        target = {'name': 'ETL', 'application': 'dbt 증분 모델 작성', 'coreOutcome': '증분 모델',
                  'coreCriteria': ['증분 실행 확인'], 'followUpScope': []}
        plan, handoff, task = self.make_plan('A2', target)
        for field in roadmap.LEARNING_SKILL_FIELDS:
            plan['def'].pop(field)
        handoff['skillDetails'] += [dict(target, name='선택 안 한 스킬')]
        sent, revised = self.revise('A2', plan, handoff, task)
        self.assertEqual(sent, [target])
        self.assertEqual(revised['learningSkills'], [target])
        handoff['skillDetails'][0] = dict(target, coreCriteria=[''])
        sent, revised = self.revise('A2', plan, handoff, task)
        self.assertEqual(sent, [])
        self.assertNotIn('learningSkills', revised)


class CourseDiagnosticTests(TestCase):
    def crash(self, rows, picks, *, two_skills=False):
        names = ('ETL', 'SQL') if two_skills else ('ETL',)
        selection = {'skills': [{'name': name, 'application': application}
                                for name, application in zip(names, ('dbt 모델 구현', 'SQL 조인 구현'))]}
        pools = [{'name': name, 'courses': [row for row in rows if name in row['skills']], 'books': []} for name in names]
        def generate(_, payload):
            self.assertEqual(payload['crashStudyPlan']['uniqueCourses'], 1)
            return {'skills': [{'name': name, 'courses': [{'id': rid}], 'books': [],
                                'courseDiagnostic': {'reason': 'longer_for_coverage', 'detail': '다른 실습으로 보완'}}
                               for name, rid in zip(names, picks)]}
        return recommend_resources({'goal': 'dbt 모델과 SQL 조인 구현'}, selection,
                                   {row['id']: row for row in rows}, generate,
                                   course={'id': 'A2'}, retrieved_pools=pools)['skills']

    def test_equal_duration_or_unconfirmed_duration_never_claims_longer(self):
        default = course('a', ['dbt 모델 실습'], hours=5)
        equal = course('b', ['dbt 모델 실습'], hours=5)
        for alternative in (equal, dict(equal, hours=10, timeStatus='estimated'), dict(equal, hours=None)):
            with self.subTest(alternative=alternative):
                result, = self.crash([default, alternative], ['b'])
                self.assertEqual(result['selectedCourse'], 'b')
                self.assertNotIn('courseDiagnostic', result)

    def test_two_distinct_courses_increase_total_vs_one_shared_course_at_same_hours(self):
        shared = course('a', ['dbt 모델 실습', 'SQL 조인 실습'], hours=5, skills=['ETL', 'SQL'])
        etl = course('etl', ['dbt 모델 실습'], hours=5)
        sql = course('sql', ['SQL 조인 실습'], hours=5, skills=['SQL'])
        result = self.crash([shared, etl, sql], ['etl', 'sql'], two_skills=True)
        self.assertEqual([row['selectedCourse'] for row in result], ['etl', 'sql'])
        self.assertEqual([row['courseDiagnostic']['reason'] for row in result], ['longer_for_coverage'] * 2)

    def test_missing_stack_is_distinct_from_confirmed_conflict_for_model_or_server_diagnostic(self):
        project = {'goal': 'FastAPI REST API 구현'}
        selection = {'skills': [{'name': WEB, 'application': project['goal']}]}
        for unit, expected in (('웹 프레임워크 REST API 구현', 'insufficient_evidence'),
                               ('Spring REST API 구현', 'stack_mismatch')):
            for model_diagnostic in (False, True):
                with self.subTest(unit=unit, model_diagnostic=model_diagnostic):
                    item = course('web', [unit], skills=[WEB])
                    item['difficulty'] = 'ADVANCED'
                    raw = {'name': WEB, 'courses': [], 'books': []}
                    if model_diagnostic:
                        raw['courseDiagnostic'] = {'reason': 'stack_mismatch', 'detail': '구현 기술이 달라요.'}
                    result = recommend_resources(project, selection, {'web': item}, lambda *_: {'skills': [raw]},
                                                 course={'id': 'A3'},
                                                 retrieved_pools=[{'name': WEB, 'courses': [item], 'books': []}])
                    self.assertEqual(result['skills'][0]['courseDiagnostic']['reason'], expected)

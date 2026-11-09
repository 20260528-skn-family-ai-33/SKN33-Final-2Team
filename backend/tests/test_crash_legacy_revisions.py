"""#111 재현 1·2: 기존 핵심 유지, 새 의무 사전 거절, 구형 생성 결과의 검증·보존."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import llm
from app.agents import roadmap
from app.errors import ApiError
from app.services.course_skills import recommendation_key, validate_recommendations
from app.services.crash_requirements import MAX_REQUIREMENT_CHARS
from test_crash_required_technologies import target
from test_recommendation_suitability import WEB


REQUIREMENT_FIELDS = ('goal', 'projectSummary', 'desiredCompetencies', 'details', 'userNotes')


class CrashLegacyRevisionsTests(unittest.TestCase):
    def revision_input(self, *, legacy=False, goal='Django 사용 필수'):
        handoff = {'goal': goal, 'projectSummary': '', 'desiredCompetencies': '',
                   'details': {'etc': ''}, 'userNotes': [],
                   'skillNames': [WEB], 'skillOrder': [WEB], 'skillDetails': [],
                   'startStage': 1, 'prefs': {'weeklyHours': 6}}
        definition = {} if legacy else {
            'learningSkills': [target()], 'learningSkillsVersion': 'saved-version',
            'learningSkillsKey': 'saved-key',
            'learningSkillSelection': [{'name': WEB, 'enabled': True}],
        }
        plan = {'opt': 'A2', 'name': 'Crash', 'tagline': '기존 계획', 'def': definition,
                'hours': 4, 'start': 1,
                'acts': [{'id': f'task-{i}', 'stage': 3, 'title': f'API 구현 {i}',
                          'res': None, 'hours': 2, 'how': '응답을 확인해요.',
                          'skill': WEB, 'skills': [WEB], 'done': i == 1} for i in (1, 2)]}
        return {'pid': 'A2', 'plan': plan, 'handoff': handoff,
                'previousHandoff': {key: deepcopy(handoff[key]) for key in REQUIREMENT_FIELDS},
                'changes': {'weeklyHours': 6}, 'request': None}

    def revision_answer(self, inp):
        # 실제 수정 계약은 모델이 활동을 삭제하고, 서버는 삭제된 key의 재사용만 막는다.
        removed = {row['key'] for row in inp['changes'].get('removeActs') or []}
        return {'acts': [dict(deepcopy(act), key=act['id']) for act in inp['plan']['acts'] if act['id'] not in removed],
                'weeklyHours': 6, 'summary': '시간 변경',
                # 같은 코스에서 새 모델 기준을 검증 대상으로 삼으면 잘못 통과할 수 있다.
                'learningSkills': [target('Django')]}

    def generation_input(self):
        # 실제 구형 handoff에는 목표만 있고 선정 스킬 이름은 없을 수 있다.
        return {'pid': 'A2', 'handoff': {'goal': 'Django 사용 필수'}}

    def generation_answer(self):
        return {'acts': [{'stage': 3, 'title': 'Django REST API 구현', 'res': None,
                          'hours': 2, 'how': '응답을 확인해요.', 'skills': [WEB]}],
                'learningSkills': [target('Django')]}

    @contextmanager
    def model_boundary(self, inp, raw, *, registered_names=None):
        """실제 finish_option을 사용하고 모델·DB·카탈로그 I/O만 모의 처리한다."""
        before, raw_before = deepcopy(inp), deepcopy(raw)
        captured = {}
        registered_names = [WEB] if registered_names is None else list(registered_names)

        def pack(pid, payload, *args):
            captured['payload'] = deepcopy(payload)
            return deepcopy(payload)

        def dispatch(ctx, name, task, data, demo, api, **kwargs):
            captured['log_input'] = deepcopy(kwargs.get('log_input'))
            return api(data)

        with patch.object(roadmap, '_sys', return_value='DB Track prompt'), \
             patch.object(roadmap.catalog, 'items', return_value={}), \
             patch.object(roadmap.catalog, 'skill_names', return_value=registered_names), \
             patch.object(roadmap, '_catalog_payload', side_effect=pack), \
             patch.object(roadmap.rt, 'llm_json', side_effect=lambda *args, **kwargs: deepcopy(raw)) as model, \
             patch.object(roadmap.rt, 'run', side_effect=dispatch):
            try:
                yield model, captured
            finally:
                self.assertEqual(inp, before)
                self.assertEqual(raw, raw_before)

    def test_existing_mismatch_or_absent_core_allows_time_change_and_deletion(self):
        for legacy in (False, True):
            for delete in (False, True):
                with self.subTest(legacy=legacy, delete=delete):
                    inp = self.revision_input(legacy=legacy)
                    if delete:
                        inp['changes'] = {'removeActs': [{'key': 'task-2', 'title': 'API 구현 2'}]}
                    with self.model_boundary(inp, self.revision_answer(inp)) as (model, _):
                        result = roadmap.revise(SimpleNamespace(mode='openai'), inp)
                        model.assert_called_once()
                    if legacy:
                        self.assertNotIn('learningSkills', result)
                    else:
                        for field in roadmap.LEARNING_SKILL_FIELDS:
                            self.assertEqual(result[field], inp['plan']['def'][field])
                    self.assertEqual(result['weeklyHours'], 6)
                    self.assertEqual([act['key'] for act in result['acts']], ['task-1'] if delete else ['task-1', 'task-2'])
                    self.assertTrue(inp['plan']['acts'][0]['done'])

    def test_new_requirement_from_each_user_source_is_rejected_without_model_call(self):
        for source in (*REQUIREMENT_FIELDS, 'request'):
            for legacy in (False, True):
                with self.subTest(source=source, legacy=legacy):
                    inp = self.revision_input(legacy=legacy, goal='웹 API 구현')
                    if source == 'request':
                        inp['request'] = 'Django 사용 필수'
                    else:
                        value = ['Django 사용 필수'] if source == 'userNotes' else \
                            {'environment': 'Django 사용 필수'} if source == 'details' else 'Django 사용 필수'
                        inp['handoff'][source] = value
                    with self.model_boundary(inp, self.revision_answer(inp)) as (model, _):
                        with self.assertRaises(ApiError) as caught:
                            roadmap.revise(SimpleNamespace(mode='openai'), inp)
                        model.assert_not_called()
                    error = caught.exception
                    self.assertEqual((error.status, error.code), (422, 'CRASH_CORE_REQUIREMENT_CONFLICT'))
                    self.assertIn('새 Crash 로드맵', error.message)
                    self.assertIn('django', error.message.casefold())
                    self.assertNotIn('다시 생성해 주세요', error.message)
                    self.assertIn('django', error.extra['cause'].casefold())
                    self.assertFalse(error.retryable)

    def test_existing_missing_obligation_does_not_hide_new_missing_obligation(self):
        inp = self.revision_input()
        inp['request'] = 'PostgreSQL 사용 필수'
        with self.model_boundary(inp, self.revision_answer(inp)) as (model, _):
            with self.assertRaises(ApiError) as caught:
                roadmap.revise(SimpleNamespace(mode='openai'), inp)
            model.assert_not_called()
        self.assertIn('postgresql', caught.exception.extra['cause'].casefold())

    def test_directly_repeated_missing_obligation_is_not_silently_ignored(self):
        inp = self.revision_input()
        inp['request'] = 'Django 사용 필수'
        with self.model_boundary(inp, self.revision_answer(inp)) as (model, _):
            with self.assertRaises(ApiError) as caught:
                roadmap.revise(SimpleNamespace(mode='openai'), inp)
            model.assert_not_called()
        self.assertEqual(caught.exception.code, 'CRASH_CORE_REQUIREMENT_CONFLICT')

    def test_existing_missing_obligation_allows_new_requirement_covered_by_saved_core(self):
        inp = self.revision_input()
        inp['request'] = 'FastAPI 사용 필수'
        with self.model_boundary(inp, self.revision_answer(inp)) as (model, captured):
            result = roadmap.revise(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()
        self.assertEqual(result['learningSkills'], [target()])
        self.assertNotIn('previousHandoff', captured['payload'])
        self.assertNotIn('previousHandoff', captured['log_input'])
        self.assertEqual(captured['payload']['current']['learningSkills'], [target()])

    def test_deleted_obligation_does_not_block_legacy_revision(self):
        inp = self.revision_input(legacy=True, goal='웹 API 구현')
        inp['previousHandoff']['details']['etc'] = 'Django 사용 필수'
        inp['previousHandoff']['userNotes'] = ['Django 사용 필수']
        with self.model_boundary(inp, self.revision_answer(inp)) as (model, _):
            result = roadmap.revise(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()
        self.assertNotIn('learningSkills', result)

    def test_unknown_previous_requirements_do_not_exempt_current_requirements(self):
        for baseline in ('missing', None, {}, 'invalid'):
            with self.subTest(baseline=baseline):
                inp = self.revision_input(legacy=True)
                if baseline == 'missing':
                    inp.pop('previousHandoff')
                else:
                    inp['previousHandoff'] = baseline
                with self.model_boundary(inp, self.revision_answer(inp)) as (model, _):
                    with self.assertRaises(ApiError) as caught:
                        roadmap.revise(SimpleNamespace(mode='openai'), inp)
                    model.assert_not_called()
                self.assertEqual(caught.exception.code, 'CRASH_CORE_REQUIREMENT_CONFLICT')

    def test_legacy_direct_call_without_requirements_still_allows_revision(self):
        inp = self.revision_input(legacy=True, goal='웹 API 구현')
        inp.pop('previousHandoff')
        with self.model_boundary(inp, self.revision_answer(inp)) as (model, _):
            result = roadmap.revise(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()
        self.assertNotIn('learningSkills', result)

    def test_direct_call_with_saved_core_covering_current_requirements_allows_revision(self):
        inp = self.revision_input()
        inp.pop('previousHandoff')
        inp['plan']['def']['learningSkills'] = [target('Django')]
        raw = self.revision_answer(inp)
        raw['learningSkills'] = [target()]
        with self.model_boundary(inp, raw) as (model, _):
            result = roadmap.revise(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()
        self.assertEqual(result['learningSkills'], [target('Django')])

    def test_oversized_same_course_request_is_rejected_without_model_call(self):
        inp = self.revision_input()
        inp['request'] = '가' * MAX_REQUIREMENT_CHARS
        with self.model_boundary(inp, self.revision_answer(inp)) as (model, _):
            with self.assertRaises(ApiError) as caught:
                roadmap.revise(SimpleNamespace(mode='openai'), inp)
            model.assert_not_called()
        self.assertEqual((caught.exception.status, caught.exception.code), (422, 'CRASH_REQUIREMENTS_TOO_LONG'))

    def test_switch_to_crash_checks_all_requirements_even_with_previous_snapshot(self):
        inp = self.revision_input()
        inp['plan']['opt'] = 'A1'
        inp['changes'] = {'perspective': 'A2'}
        raw = self.revision_answer(inp)
        raw['learningSkills'] = [target()]
        with self.model_boundary(inp, raw) as (model, _):
            with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
                roadmap.revise(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()

    def test_legacy_generation_validates_and_preserves_model_core(self):
        inp, raw = self.generation_input(), self.generation_answer()
        raw['learningSkills'][0]['modelOnlyField'] = '저장 금지'
        raw['learningSkillSelection'] = [{'name': '알 수 없는 스킬', 'enabled': True}]
        with self.model_boundary(inp, raw) as (model, captured):
            result = roadmap.option(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()
        self.assertEqual(result['learningSkills'], [target('Django')])
        self.assertNotIn('learningSkillSelection', result)
        self.assertEqual(result['learningSkillsKey'], recommendation_key(result))
        self.assertEqual(captured['payload']['handoff'], {'goal': 'Django 사용 필수'})
        self.assertEqual(captured['payload']['skillTags'], [WEB])
        self.assertIn('[구형 Crash 필수 기술 응답 계약]', model.call_args.args[1])
        self.assertIn('coreCriteria', model.call_args.args[1])

    def test_legacy_generation_rejects_names_outside_registered_tags_including_empty_tags(self):
        for registered_names in ([], ['다른 등록 스킬']):
            with self.subTest(registered_names=registered_names):
                inp, raw = self.generation_input(), self.generation_answer()
                with self.model_boundary(inp, raw, registered_names=registered_names) as (model, _):
                    with self.assertRaises(llm.LlmError):
                        roadmap.option(SimpleNamespace(mode='openai'), inp)
                    model.assert_called_once()
        with self.assertRaises(ValueError):
            validate_recommendations([target('Django')], set(), 'A2', require_depth=True)

    def test_legacy_generation_registered_tags_do_not_override_explicit_selection(self):
        inp, raw = self.generation_input(), self.generation_answer()
        inp['handoff'].update(skillNames=['다른 선정 스킬'], skillOrder=['다른 선정 스킬'])
        with self.model_boundary(inp, raw) as (model, _):
            with self.assertRaises(llm.LlmError):
                roadmap.option(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()

    def test_legacy_generation_without_required_technologies_keeps_existing_option_behavior(self):
        for rows in ('missing', [target('Django')], None, [{'name': '알 수 없는 스킬'}]):
            with self.subTest(rows=rows):
                inp, raw = self.generation_input(), self.generation_answer()
                inp['handoff']['goal'] = '웹 API 구현'
                if rows == 'missing':
                    raw.pop('learningSkills')
                else:
                    raw['learningSkills'] = rows
                with self.model_boundary(inp, raw) as (model, _):
                    result = roadmap.option(SimpleNamespace(mode='openai'), inp)
                    model.assert_called_once()
                for field in roadmap.LEARNING_SKILL_FIELDS:
                    self.assertNotIn(field, result)
                self.assertEqual(result['acts'][0]['title'], raw['acts'][0]['title'])
                self.assertNotIn('[구형 Crash 필수 기술 응답 계약]', model.call_args.args[1])

    def test_legacy_generation_rejects_invalid_model_skill_list(self):
        invalid = (None, [], '원시 문자열', [target('Django', name='알 수 없는 스킬')],
                   [target('Django')] * 2, [target('Django', application=' ')],
                   [target('Django', coreCriteria=[])], [target('Django', coreOutcome=' ')])
        for rows in invalid:
            with self.subTest(rows=rows):
                inp, raw = self.generation_input(), self.generation_answer()
                raw['learningSkills'] = rows
                with self.model_boundary(inp, raw) as (model, _):
                    with self.assertRaises(llm.LlmError):
                        roadmap.option(SimpleNamespace(mode='openai'), inp)
                    model.assert_called_once()

    def test_legacy_generation_cannot_skip_missing_core_or_inherit_requirement_exemption(self):
        for omit in (False, True):
            with self.subTest(omit=omit):
                inp, raw = self.generation_input(), self.generation_answer()
                inp['previousHandoff'] = {'goal': inp['handoff']['goal']}
                if omit:
                    raw.pop('learningSkills')
                else:
                    raw['learningSkills'] = [target()]
                with self.model_boundary(inp, raw) as (model, _):
                    with self.assertRaisesRegex(llm.LlmError, '(?i)django'):
                        roadmap.option(SimpleNamespace(mode='openai'), inp)
                    model.assert_called_once()

    def test_fixed_selection_without_assessment_id_cannot_skip_model_skill_validation(self):
        inp, raw = self.generation_input(), self.generation_answer()
        inp['handoff'].update(selectedSkillsFixed=True, skillNames=[WEB], skillOrder=[WEB])
        raw.pop('learningSkills')
        with self.model_boundary(inp, raw) as (model, _):
            with self.assertRaises(llm.LlmError):
                roadmap.option(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()

    def test_fixed_selection_without_names_cannot_expand_to_all_registered_tags(self):
        inp, raw = self.generation_input(), self.generation_answer()
        inp['handoff']['selectedSkillsFixed'] = True
        with self.model_boundary(inp, raw) as (model, _):
            with self.assertRaises(llm.LlmError):
                roadmap.option(SimpleNamespace(mode='openai'), inp)
            model.assert_called_once()


if __name__ == '__main__':
    unittest.main()

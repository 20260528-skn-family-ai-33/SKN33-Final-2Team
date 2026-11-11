from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from app import catalog, llm
from app.agents import roadmap
from app.agents.roadmap_revision import revision
from app.services.course_skills import recommendation_key
from test_recommendation_suitability import course


class CourseTransitionTargetsTests(TestCase):
    def target(self, course, name='ETL'):
        base = {'name': name, 'application': '주문 증분 모델 구현'}
        if course == 'A2':
            base.update(coreOutcome='최소 증분 모델', coreCriteria=['증분 실행과 결과 확인'],
                        followUpScope=['실패 복구와 대안 비교'])
        if course == 'A3':
            base.update(targetOutcome='실패 복구 가능한 모델',
                        completionCriteria=['대안별 실행 결과 비교', '실패 복구와 한계 검증'])
        return base

    def revision_input(self, source, destination, *, names=None, disabled=(), legacy=False):
        names = names or ['ETL']
        old = [self.target(source, name) for name in names]
        acts = [{'id': f'task-{i}', 'stage': 3, 'title': f'{name} 모델 구현', 'res': None,
                 'hours': 2, 'how': '결과 확인', 'skill': name, 'skills': [name], 'done': True}
                for i, name in enumerate(names) if name not in disabled]
        choices = {name: {'enabled': name not in disabled} for name in names}
        definition = {'learningSkills': old, 'learningSkillsVersion': 'old-version', 'learningSkillsKey': 'old-key',
                      'learningSkillSelection': [dict(choices[name], name=name) for name in names],
                      'learningReport': {'skillOrder': names, 'choices': choices,
                          'skillDetails': [{'name': name, 'application': '증분 처리', 'competencySummary': ['이전 기준의 검토']} for name in names]}}
        handoff = {'goal': '주문 데이터 처리', 'skillNames': names, 'skillOrder': names,
                   'skillDetails': deepcopy(old), 'startStage': 1, 'prefs': {'weeklyHours': 4}}
        if legacy:
            definition = {}
            for field in ('skillOrder', 'skillNames', 'skillDetails'):
                handoff.pop(field)
        plan = {'opt': source, 'name': source, 'def': definition, 'hours': 4, 'start': 1, 'acts': acts}
        return {'pid': destination, 'plan': plan, 'handoff': handoff,
                'changes': {'perspective': destination} if source != destination else {'weeklyHours': 6}}

    def revise_input(self, inp, response_targets, *, mock=False, catalog_items=None):
        destination, plan = inp['pid'], inp['plan']
        names = inp['handoff'].get('skillNames') or [act['skill'] for act in plan['acts']]
        # 카탈로그 픽스처를 준 검사는 실제 입력 조립과 토큰 예산 적용까지 실행한다.
        packer = (nullcontext() if catalog_items is not None else
                  patch.object(roadmap, '_catalog_payload', side_effect=lambda pid, payload, *args: payload))
        before = deepcopy(inp)
        captured = {}
        def model(ctx, system, payload, **kwargs):
            captured.update(system=system, payload=deepcopy(payload))
            result = {'acts': [dict(act, key=act['id']) for act in plan['acts']], 'summary': '기준 조정'}
            if response_targets is not None:
                result['learningSkills'] = deepcopy(response_targets)
            return result
        with patch.object(roadmap, '_sys', return_value=revision(destination)), \
             patch.object(catalog, 'items', return_value=catalog_items or {}), \
             patch.object(catalog, 'skill_names', return_value=names), \
             packer, \
             patch.object(roadmap.rt, 'llm_json', side_effect=model), \
             patch.object(roadmap, '_mock_revise', side_effect=lambda data: {'id': destination, 'acts': []}), \
             patch.object(roadmap.rt, 'run', side_effect=lambda ctx, name, task, data, demo, api, **kw: demo(data) if mock else api(None)):
            try:
                out = roadmap.revise(SimpleNamespace(mode='mock' if mock else 'openai'), inp)
            finally:
                self.assertEqual(inp, before)
        return out, captured, plan

    def run_revision(self, source, destination, response_targets, *, names=None, mock=False, legacy=False):
        inp = self.revision_input(source, destination, names=names, legacy=legacy)
        return self.revise_input(inp, response_targets, mock=mock)

    def test_challenge_to_crash_creates_core_and_preserves_activity_identity(self):
        target = self.target('A2')
        out, captured, plan = self.run_revision('A3', 'A2', [target])
        self.assertEqual(out['learningSkills'], [target])
        self.assertNotIn('completionCriteria', out['learningSkills'][0])
        self.assertNotEqual(out['learningSkillsVersion'], 'old-version')
        self.assertEqual(out['learningSkillsKey'], recommendation_key(out))
        self.assertNotIn('learningSkillSelection', out)
        self.assertEqual(out['acts'][0]['key'], plan['acts'][0]['id'])
        self.assertTrue(captured['payload']['current']['acts'][0]['done'])
        self.assertIn('completionCriteria', captured['payload']['current']['learningSkills'][0])
        self.assertEqual(set(captured['payload']['skillTargets'][0]), {'name', 'application'})
        self.assertEqual(set(captured['payload']['handoff']['skillDetails'][0]), {'name', 'application'})
        self.assertIn('[코스 전환 시 목표 재작성]', captured['system'])
        self.assertEqual(out['learningReport']['skillDetails'][0]['competencySummary'], [])

    def test_crash_to_challenge_requires_new_depth(self):
        target = self.target('A3')
        out, _, _ = self.run_revision('A2', 'A3', [target])
        self.assertEqual(out['learningSkills'], [target])
        self.assertNotIn('coreCriteria', out['learningSkills'][0])

    def test_crash_to_free_removes_old_depth(self):
        out, _, _ = self.run_revision('A2', 'A1', [self.target('A1')])
        self.assertEqual(out['learningSkills'], [self.target('A1')])

    def test_free_to_crash_gets_new_core(self):
        out, _, _ = self.run_revision('A1', 'A2', [self.target('A2')])
        self.assertEqual(out['learningSkills'], [self.target('A2')])

    def test_same_course_preserves_saved_targets_even_if_model_changes_them(self):
        out, captured, _ = self.run_revision('A2', 'A2', [self.target('A3')])
        self.assertEqual(out['learningSkills'], [self.target('A2')])
        self.assertEqual(out['learningSkillsVersion'], 'old-version')
        self.assertNotIn('[코스 전환 시 목표 재작성]', captured['system'])
        self.assertEqual(out['learningReport']['skillDetails'][0]['competencySummary'], ['이전 기준의 검토'])

    def test_missing_or_old_course_targets_are_rejected(self):
        for rows in (None, [], [self.target('A3')], [dict(self.target('A2'), coreCriteria=[''])]):
            with self.subTest(rows=rows), self.assertRaises(llm.LlmError):
                self.run_revision('A3', 'A2', rows)

    def test_invalid_changed_names_and_duplicates_are_rejected(self):
        for rows in ([self.target('A2', 'SQL')], [self.target('A2')] * 2):
            with self.subTest(rows=rows), self.assertRaises(llm.LlmError):
                self.run_revision('A3', 'A2', rows)

    def test_all_fixed_skills_and_order_are_required(self):
        names = ['ETL', 'SQL', 'Python']
        targets = [self.target('A2', name) for name in names]
        out, _, _ = self.run_revision('A3', 'A2', targets, names=names)
        self.assertEqual([row['name'] for row in out['learningSkills']], names)
        for rows in (targets[:-1], list(reversed(targets))):
            with self.subTest(rows=rows), self.assertRaises(llm.LlmError):
                self.run_revision('A3', 'A2', rows, names=names)

    def test_actual_catalog_preserves_three_active_skills_in_order(self):
        active = ['Docker', 'ETL', 'Python']
        disabled = 'Linux'
        names = [active[0], disabled, *active[1:]]
        inp = self.revision_input('A3', 'A2', names=names, disabled=(disabled,))
        items = {name: course(name, [f'{name} 주문 증분 모델 구현 실습'], skills=[name]) for name in names}
        targets = [self.target('A2', name) for name in active]
        out, captured, _ = self.revise_input(inp, targets, catalog_items=items)
        payload = captured['payload']
        self.assertEqual(payload['current']['skillOrder'], active)
        self.assertEqual(payload['handoff']['skillOrder'], active)
        self.assertEqual(payload['trackGuidance']['coreSkills'], active)
        self.assertEqual(payload['trackGuidance']['maxCoreSkills'], 3)
        self.assertEqual([row['name'] for row in payload['skillTargets']], active)
        self.assertEqual([row['name'] for row in payload['handoff']['skillDetails']], active)
        self.assertEqual(set(payload['catalogSkillMap'].values()), set(active))
        self.assertEqual({row['id'] for row in payload['catalog']}, set(active))
        self.assertEqual(out['learningSkills'], targets)
        self.assertEqual(out['learningReport']['skillOrder'], active)

    def test_saved_four_active_skills_revise_only_first_three(self):
        names = ['Docker', 'ETL', 'Python', 'SQL']
        inp = self.revision_input('A3', 'A2', names=names)
        items = {name: course(name, [f'{name} 주문 증분 모델 구현 실습'], skills=[name]) for name in names}
        targets = [self.target('A2', name) for name in names[:3]]
        out, captured, _ = self.revise_input(inp, targets, catalog_items=items)
        payload = captured['payload']
        self.assertEqual(payload['handoff']['skillOrder'], names[:3])
        self.assertEqual([row['name'] for row in payload['skillTargets']], names[:3])
        self.assertEqual(out['learningSkills'], targets)
        with self.assertRaises(llm.LlmError):
            self.revise_input(inp, [self.target('A2', name) for name in names], catalog_items=items)

    def test_next_revision_uses_converted_targets_with_stale_handoff(self):
        inp = self.revision_input('A3', 'A2')
        target = self.target('A2')
        out, _, base = self.revise_input(inp, [target])
        converted = roadmap.build_plan(roadmap.keep_ids(deepcopy(out), base, 2),
                                       {'start': 1, 'hours': 4}, inp['handoff']['goal'])
        # 확정 뒤에도 최초 handoff 원본이 남아 있는 실제 수정 요청을 재현한다.
        same_course = dict(inp, plan=converted, changes={'weeklyHours': 6})
        result, captured, _ = self.revise_input(same_course, None)
        payload = captured['payload']
        self.assertIn('completionCriteria', same_course['handoff']['skillDetails'][0])
        self.assertEqual(payload['handoff']['skillDetails'], [target])
        self.assertEqual(payload['skillTargets'], [target])
        self.assertEqual(result['learningSkillsVersion'], out['learningSkillsVersion'])

    def test_new_report_details_persist_after_same_course_revision(self):
        target = dict(self.target('A2'), application='최소 증분 조회만 구현')
        inp = self.revision_input('A3', 'A2')
        out, _, base = self.revise_input(inp, [target])
        expected = [dict(target, competencySummary=[])]
        self.assertEqual(out['learningReport']['skillDetails'], expected)
        same_course = dict(inp, plan={**base, 'opt': 'A2', 'def': out}, changes={'weeklyHours': 6})
        result, _, _ = self.revise_input(same_course, None)
        self.assertEqual(result['learningReport']['skillDetails'], expected)

    def test_mock_cannot_silently_reuse_old_targets(self):
        """가데이터 모드에서 새 기준을 생성하지 못하면 기존 계획을 유지한다."""
        with self.assertRaisesRegex(llm.LlmError, 'AI 모델'):
            self.run_revision('A3', 'A2', None, mock=True)

    def test_legacy_without_skill_targets_keeps_old_revision_path(self):
        out, captured, _ = self.run_revision('A3', 'A2', None, legacy=True)
        self.assertNotIn('learningSkills', out)
        self.assertNotIn('[코스 전환 시 목표 재작성]', captured['system'])

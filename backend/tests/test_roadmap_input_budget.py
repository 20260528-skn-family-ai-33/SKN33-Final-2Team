"""모델 전달용 투영·스킬 정합성·실제 직렬화 예산 회귀. 외부 연결 없음."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import catalog, catalog_budget as budget, catalog_candidates as candidates, llm, roadmap_input
from app.agents import roadmap as rm, runtime
from app.learner_knowledge import from_profile, hr_context
from app.services.planning_handoff import build_handoff
from test_catalog_candidates import resource, resources


def completed_five():
    names = [f'skill-{i}' for i in range(5)]
    profile = {'department': '데이터 운영', 'job': '사내 규정 검색 업무',
               'task': '규정 PDF와 조회 API를 운영하고 오류 신고를 확인한다.',
               'education': ['컴퓨터공학 학사'],
               'self': {'profile': '외부 인터넷에 내부 문서를 전송할 수 없다.',
                        'tech': ['Python 2년'], 'certs': ['정보처리기사'],
                        'learning': ['비동기 API 구현 연습'],
                        'projects': ['공개 자료로 SQL 조회 API를 작성했다.']}}
    groups, answers = [], {}
    for i, name in enumerate(names):
        group = {'skill': name, 'title': f'검색 서비스의 동작을 점검해 볼까요 {i}', 'surveys': [], 'quizzes': []}
        for j in range(3):
            sid, qid = f's{i}_surveys_{j}', f's{i}_quizzes_{j}'
            group['surveys'].append({'id': sid, 'text': f'SQL 조회 결과와 출처를 대조하여 오류 원인을 확인할 수 있다. 점검 {j}'})
            group['quizzes'].append({'id': qid, 'q': f'SQL 조회 API의 중복 응답이 발생할 때 검증할 근거는 무엇인가? 사례 {j}',
                                    'concept': '조인 결과 정합성', 'difficulty': '적용', 'questionType': '오류 원인 판단',
                                    'options': ['기본 키별 응답을 입력 행과 비교한다.', '호출 수를 늘려 응답 속도를 비교한다.',
                                                '캐시를 비우고 오류 비율을 비교한다.', '배포 인스턴스의 메모리를 비교한다.',
                                                '동일한 질문의 문장 길이를 비교한다.'],
                                    'answer': 0, 'explain': '중복 원인을 찾으려면 입력 행과 조인 결과의 키를 대조한다.'})
            answers[sid], answers[qid] = j + 2, j % 2
        groups.append(group)
    saved = {'completed': True, 'generationId': 'test-generated-not-human', 'profile': profile,
             'project': {'goal': 'SQL 조회 API와 규정 검색을 구현한다.', 'selectedSkills': names,
                         'projectSummary': '내부 규정의 근거와 출처를 함께 반환하는 검색 API다.',
                         'desiredCompetencies': '검색 오류를 분석하고 조회 결과를 검증한다.',
                         'details': {'etc': '기존 LLM만 사용하고 모델은 새로 학습시키지 않는다.'}},
             'selection': {'skills': [{'name': name, 'application': f'SQL 조회 결과를 검증한다. {i}'} for i, name in enumerate(names)]},
             'survey': {'groups': groups}, 'answers': answers}
    return saved, build_handoff(saved, {'weeklyHours': 6, 'deadlineWeeks': 12}, profile)


class InputProjectionTests(unittest.TestCase):
    def test_answers_correctness_and_all_personal_context_survive_without_mutating_saved_input(self):
        saved, h = completed_five()
        h['customConstraint'] = '주말에는 업무망을 사용할 수 없다.'
        before = deepcopy((saved, h))
        result = roadmap_input.project({'handoff': h, 'learnerKnowledge': h['learnerKnowledge'],
                                        'request': {'wish': '종료 시 출처 오류를 재현해 주세요.'}})
        out = result['handoff']
        self.assertEqual((saved, h), before)
        self.assertEqual(out['goal'], h['goal'])
        for key in ('details', 'projectSummary', 'desiredCompetencies', 'skillDetails', 'skillOrder', 'customConstraint'):
            self.assertEqual(out[key], h[key])
        self.assertEqual(out['hrContext'], hr_context(saved['profile']))
        self.assertEqual(out['learnerKnowledge'], from_profile(saved['profile']))
        self.assertEqual(out['profile']['self']['profile'], saved['profile']['self']['profile'])
        self.assertEqual(out['profile']['self']['projects'], saved['profile']['self']['projects'])
        self.assertNotIn('tech', out['profile']['self'])
        self.assertNotIn('learnerKnowledge', result)
        self.assertEqual(len(out['assessment']['groups']), 5)
        for group in out['assessment']['groups']:
            self.assertEqual([q['rating'] for q in group['surveys']], [2, 3, 4])
            self.assertEqual([q['correct'] for q in group['quizzes']], [True, False, True])
            self.assertEqual(group['quizzes'][1]['chosen'], '호출 수를 늘려 응답 속도를 비교한다.')
            self.assertEqual(group['quizzes'][1]['expected'], '기본 키별 응답을 입력 행과 비교한다.')
            self.assertIn('explain', group['quizzes'][1])
            self.assertNotIn('options', group['quizzes'][0])

    def test_unmatched_personal_fields_and_conflicting_profile_snapshots_are_kept(self):
        _, h = completed_five()
        h['profile']['self']['tech'] = ['Rust 프로젝트 경험']
        h['profile']['job'] = '최근 변경된 업무 설명'
        h['profile']['extendedPersonalInput'] = '사내 문서 대신 공개 샘플만 사용한다.'
        h['assessment']['answers']['legacy-free-text'] = '정답을 모르지만 응답 행을 비교했다.'
        out = roadmap_input.project({'handoff': h})['handoff']
        self.assertEqual(out['profile']['self']['tech'], ['Rust 프로젝트 경험'])
        self.assertEqual(out['profile']['job'], '최근 변경된 업무 설명')
        self.assertEqual(out['profile']['extendedPersonalInput'], h['profile']['extendedPersonalInput'])
        self.assertEqual(out['assessment']['additionalAnswers']['legacy-free-text'], h['assessment']['answers']['legacy-free-text'])

    def test_unanswered_quiz_is_not_marked_incorrect(self):
        saved, h = completed_five()
        key = saved['survey']['groups'][0]['quizzes'][0]['id']
        del h['assessment']['answers'][key]
        out = roadmap_input.project({'handoff': h})
        self.assertIsNone(out['handoff']['assessment']['groups'][0]['quizzes'][0]['correct'])

    def test_projection_is_idempotent_and_legacy_input_is_supported(self):
        _, h = completed_five()
        first = roadmap_input.project({'handoff': h})
        self.assertEqual(roadmap_input.project(first), first)
        legacy = {'handoff': {'goal': 'SQL', 'deepCheck': {'essays': [{'answer': '정합성을 대조한다.'}]},
                              'profile': {'freeText': '직접 적은 업무 맥락'}}}
        self.assertEqual(roadmap_input.project(legacy), legacy)

    def test_token_count_uses_exact_runtime_compact_serialization(self):
        payload = {'목표': 'SQL  내부 공백', 'rows': [{'id': '1', 'hours': 1.5}]}
        actual = json.dumps(payload, ensure_ascii=False, default=str, separators=(',', ':'))
        captured = []
        tokenizer = SimpleNamespace(encode=lambda value, **kw: captured.append(value) or SimpleNamespace(ids=[1, 2]))
        with patch.object(budget, '_tokenizer', return_value=tokenizer):
            self.assertEqual(budget.tokens(payload), 2)
        self.assertEqual(captured, [actual])
        ctx = SimpleNamespace(mode='openai', reasoning={}, meta={})
        with patch.object(runtime.llm, 'chat', return_value={'content': '{}'}) as model:
            runtime.llm_json(ctx, 'system', payload, role='roadmap')
        self.assertEqual(model.call_args.args[1][-1]['content'], actual)


class SkillIdentityTests(unittest.TestCase):
    def test_partial_and_all_stale_fixed_skills_require_reselection(self):
        rows = {'sql': resource('sql', 'SQL'), 'py': resource('py', 'Python')}
        for saved in (['옛 이름', 'Python'], ['옛 이름'], []):
            h = {'goal': 'SQL', 'skillNames': saved, 'skillOrder': saved, 'selectedSkillsFixed': True}
            before = deepcopy(h)
            with patch.object(catalog, 'items', return_value=rows), self.subTest(saved=saved), \
                    self.assertRaisesRegex(llm.LlmError, '다시 선택'):
                rm._catalog_payload('A2', {'handoff': h})
            self.assertEqual(h, before)

    def test_confirmed_order_is_authoritative_and_all_related_fields_follow_it(self):
        names = [f'skill-{i}' for i in range(5)]
        order = list(reversed(names))
        h = {'goal': 'SQL', 'skillNames': names, 'skillOrder': order, 'selectedSkillsFixed': True,
             'focus': names, 'coreSkills': names,
             'skillDetails': [{'name': name, 'application': f'SQL {name}'} for name in names]}
        with patch.object(catalog, 'items', return_value=resources(5)), patch.object(budget, 'tokens', return_value=1):
            out = rm._catalog_payload('A2', {'handoff': h})
        self.assertEqual(out['handoff']['skillOrder'], order)
        self.assertEqual(out['handoff']['coreSkills'], order)
        for key in ('skillNames', 'focus', 'domain'):
            self.assertNotIn(key, out['handoff'])
        self.assertEqual([r['name'] for r in out['handoff']['skillDetails']], order)
        self.assertEqual(out['trackGuidance']['coreSkills'], order)
        self.assertEqual(out['trackGuidance']['maxCoreSkills'], 5)
        self.assertEqual(h['skillNames'], names)

    def test_inconsistent_or_duplicate_fixed_names_are_not_guessed(self):
        for names, order in ((['SQL'], ['Python']), (['SQL', 'SQL'], ['SQL', 'SQL'])):
            with patch.object(catalog, 'items', return_value={'sql': resource('sql')}), self.subTest(order=order), \
                    self.assertRaisesRegex(llm.LlmError, '다시 선택'):
                rm._catalog_payload('A2', {'handoff': {'skillNames': names, 'skillOrder': order, 'selectedSkillsFixed': True}})

    def test_legacy_survivors_and_fallback_clear_stale_related_fields(self):
        rows = {'sql': resource('sql'), 'py': resource('py', 'Python')}
        for names, expected in ((['옛 이름', 'Python', 'SQL'], ['SQL', 'Python']), (['옛 이름'], ['SQL'])):
            h = {'goal': 'SQL', 'skillNames': names, 'skillOrder': ['SQL', '옛 이름', 'Python'],
                 'focus': ['옛 이름', 'SQL', '직접 적은 수행 목표'], 'coreSkills': ['옛 이름'],
                 'skillDetails': [{'name': name, 'application': f'{name} 세부 적용'} for name in names],
                 'skillMaterials': {name: {'course': None} for name in names}}
            before = deepcopy(h)
            with patch.object(catalog, 'items', return_value=rows), patch.object(budget, 'tokens', return_value=1):
                out = rm._catalog_payload('A2', {'handoff': h})
            self.assertEqual(out['handoff']['skillOrder'], expected)
            self.assertEqual(out['handoff']['skillNames'], expected)
            self.assertEqual(out['handoff']['coreSkills'], expected)
            self.assertNotIn('옛 이름', out['handoff']['focus'])
            self.assertIn('직접 적은 수행 목표', out['handoff']['focus'])
            self.assertTrue(all(row['name'] in expected for row in out['handoff']['skillDetails']))
            self.assertEqual(h, before)

    def test_fixed_names_are_checked_before_model_call_in_generation_regeneration_revision(self):
        h = {'goal': 'SQL', 'prefs': {}, 'selectedSkillsFixed': True, 'skillNames': ['옛 이름'], 'skillOrder': ['옛 이름']}
        plan = {'opt': 'A2', 'name': 'Crash', 'hours': 6, 'start': 1, 'acts': []}
        with patch.object(catalog, 'items', return_value={'sql': resource('sql')}), \
                patch.object(catalog, 'skill_names', return_value=['SQL']), patch.object(rm, '_sys', return_value='DB unchanged'), \
                patch.object(runtime, 'llm_json') as model, \
                patch.object(runtime, 'run', side_effect=lambda ctx, name, task, inp, mock, api, **kw: api(None)):
            for mode in ('new', 'again', 'revision'):
                with self.subTest(mode=mode), self.assertRaisesRegex(llm.LlmError, '다시 선택'):
                    if mode == 'revision':
                        rm.revise(SimpleNamespace(mode='openai'), {'pid': 'A2', 'handoff': h, 'plan': plan, 'changes': {}})
                    else:
                        rm.option(SimpleNamespace(mode='openai'), {'pid': 'A2', 'handoff': h, 'previous': {} if mode == 'again' else None})
            model.assert_not_called()

    def test_legacy_v2_all_renamed_names_allow_generation_and_regeneration_without_reusing_old_details(self):
        rows = {'sql': resource('sql', 'SQL 현재 이름')}
        h = {'goal': 'SQL 현재 이름 조회 결과를 검증한다.', 'prefs': {}, 'assessmentGenerationId': 'legacy',
             'courseSkillSelection': True, 'focus': ['SQL 옛 이름'], 'skillNames': ['SQL 옛 이름'],
             'skillOrder': ['SQL 옛 이름'], 'skillDetails': [{'name': 'SQL 옛 이름', 'application': '옛 스킬의 확인되지 않은 적용 범위'}],
             'assessment': {'groups': [{'skill': 'SQL 옛 이름', 'surveys': [{'id': 's1', 'text': '조인 오류를 확인할 수 있다.'}],
                                         'quizzes': []}], 'answers': {'s1': 3}}}
        before = deepcopy(h)
        captured = []

        def response(ctx, system, payload, **kwargs):
            captured.append(payload)
            self.assertEqual(payload['handoff']['skillNames'], ['SQL 현재 이름'])
            self.assertEqual(payload['handoff']['skillOrder'], ['SQL 현재 이름'])
            self.assertEqual(payload['handoff']['skillDetails'], [{'name': 'SQL 현재 이름'}])
            self.assertEqual(payload['handoff']['inferredSkillNames'], ['SQL 현재 이름'])
            self.assertEqual(payload['handoff']['assessment']['skills'], [])
            self.assertEqual(payload['handoff']['assessment']['unmatchedSkills'][0]['priorSkill'], 'SQL 옛 이름')
            self.assertEqual(payload['handoff']['assessment']['unmatchedSkills'][0]['surveys'][0]['selfRating'], 3)
            return {'acts': [{'stage': 2, 'res': 'sql'}],
                    'learningSkills': [{'name': 'SQL 현재 이름', 'application': '조회 결과 대조',
                                        'targetOutcome': '조인 오류 비교표', 'completionCriteria': ['입력 행 비교', '출력 키 대조'],
                                        'coreOutcome': '최소 기능 결과', 'coreCriteria': ['핵심 동작 확인']}]}

        with patch.object(catalog, 'items', return_value=rows), patch.object(catalog, 'skill_names', return_value=['SQL 현재 이름']), \
                patch.object(budget, 'tokens', return_value=1), patch.object(rm, '_sys', return_value='DB unchanged'), \
                patch.object(runtime, 'llm_json', side_effect=response), \
                patch.object(runtime, 'run', side_effect=lambda ctx, name, task, inp, mock, api, **kw: api(None)):
            for pid in ('A1', 'A2', 'A3'):
                for previous in (None, {'acts': [{'res': 'sql'}]}):
                    result = rm.option(SimpleNamespace(mode='openai'), {'pid': pid, 'handoff': h, 'previous': previous})
                    self.assertEqual(result['learningSkills'][0]['name'], 'SQL 현재 이름')
        self.assertEqual(len(captured), 6)
        self.assertEqual(h, before)

    def test_fixed_cached_handoff_without_details_retains_all_confirmed_names(self):
        names = ['SQL', 'Python']
        h = {'goal': 'SQL 조회 API', 'prefs': {}, 'selectedSkillsFixed': True, 'courseSkillSelection': True,
             'skillNames': names, 'skillOrder': list(reversed(names))}
        reply = {'acts': [{'stage': 2, 'res': 'sql'}],
                 'learningSkills': [{'name': name, 'application': '조회 결과를 대조한다.', 'coreOutcome': '최소 기능 결과', 'coreCriteria': ['핵심 동작 확인']} for name in names]}
        with patch.object(catalog, 'items', return_value={'sql': resource('sql'), 'py': resource('py', 'Python')}), \
                patch.object(catalog, 'skill_names', return_value=names), patch.object(budget, 'tokens', return_value=1), \
                patch.object(rm, '_sys', return_value='DB unchanged'), patch.object(runtime, 'llm_json', return_value=reply), \
                patch.object(runtime, 'run', side_effect=lambda ctx, name, task, inp, mock, api, **kw: api(None)):
            result = rm.option(SimpleNamespace(mode='openai'), {'pid': 'A2', 'handoff': h})
        self.assertEqual([row['name'] for row in result['learningSkills']], ['Python', 'SQL'])


class RealTokenizerBudgetTests(unittest.TestCase):
    def setUp(self):
        if not Path(budget.tokenizer_path()).is_file():
            self.skipTest('고정 토크나이저 설치 후 실행하는 실제 토큰 검사')

    def test_five_skill_completed_assessment_all_tracks_keep_useful_candidates_and_input(self):
        saved, h = completed_five()
        before = deepcopy((saved, h))
        with patch.object(catalog, 'items', return_value=resources(5)), patch.object(catalog, 'skill_names', return_value=h['skillNames']):
            for pid in ('A1', 'A2', 'A3'):
                with self.subTest(pid=pid):
                    system = rm.R_SYS.format(id=pid, name='검사 관점', rules=rm.PERSPECTIVE_RULES[pid])
                    out = rm._catalog_payload(pid, {'handoff': h, 'skillTags': h['skillNames']}, system)
                    self.assertLessEqual(budget.tokens(system) + budget.tokens(out) + budget.FRAMING_RESERVE, budget.INPUT_TOKENS)
                    self.assertGreaterEqual(len(out['catalog']), 15)
                    self.assertEqual(out['catalogCounts']['sent'], len(out['catalog']))
                    self.assertTrue(all(count >= 2 for count in out['catalogCounts']['perSkill'].values()))
                    self.assertEqual(out['handoff']['skillOrder'], h['skillOrder'])
                    self.assertEqual(out['handoff']['prefs']['deadlineWeeks'], 12)
                    self.assertNotIn('maxWeeks', out.get('trackGuidance', {}))
        self.assertEqual((saved, h), before)

    def test_oversized_personal_input_fails_without_truncation(self):
        _, h = completed_five()
        h['profile']['self']['profile'] = '제약 문서 전송 금지 및 결과 검증 필요. ' * 12000
        before = deepcopy(h)
        with patch.object(catalog, 'items', return_value=resources(5)), self.assertRaisesRegex(llm.LlmError, '입력량 한도'):
            rm._catalog_payload('A3', {'handoff': h}, 'system')
        self.assertEqual(h, before)

    def test_fixed_five_generation_regeneration_revision_keep_evidence_order_and_required_resources(self):
        saved, h = completed_five()
        before = deepcopy(h)
        names = h['skillOrder']
        rows = resources(5)
        captured = []

        def response(ctx, system, payload, **kwargs):
            captured.append(payload)
            self.assertEqual(kwargs['role'], 'roadmap')
            self.assertEqual(payload['handoff']['skillOrder'], names)
            self.assertEqual([r['name'] for r in payload['handoff']['skillDetails']], names)
            self.assertEqual(len(payload['handoff']['assessment']['skills']), 5)
            self.assertEqual(payload['handoff']['assessment']['skills'][0]['quizzes'][0]['result'], 'correct')
            self.assertEqual(payload['skillTags'], names + ['Docker'])
            self.assertLessEqual(budget.tokens(system) + budget.tokens(payload) + budget.FRAMING_RESERVE, budget.INPUT_TOKENS)
            return {'acts': [{'stage': 2, 'res': '0-29', 'title': 'SQL 결과 검증'}],
                    'learningSkills': [{'name': name, 'application': 'SQL 결과 대조', 'targetOutcome': '오류 재현 보고서',
                                        'completionCriteria': ['입출력 키 대조', '오류 재현 근거'], 'coreOutcome': '최소 기능 결과', 'coreCriteria': ['핵심 동작 확인']} for name in names]}

        with patch.object(catalog, 'items', return_value=rows), patch.object(catalog, 'skill_names', return_value=names + ['Docker']), \
                patch.object(rm, '_sys', return_value='DB system prompt unchanged'), \
                patch.object(runtime, 'llm_json', side_effect=response), \
                patch.object(runtime, 'run', side_effect=lambda ctx, name, task, inp, mock, api, **kw: api(None)):
            for pid in ('A1', 'A2', 'A3'):
                ctx = SimpleNamespace(mode='openai')
                first = rm.option(ctx, {'pid': pid, 'handoff': h})
                again = rm.option(ctx, {'pid': pid, 'handoff': h, 'previous': {'acts': [{'res': '0-29'}]}, 'request': {'wish': '검증 보완'}})
                plan = {'opt': pid, 'name': 'Track', 'hours': 6, 'start': 1,
                        'acts': [{'id': 'old', 'stage': 2, 'title': '기존 자료', 'res': '0-29', 'hours': 4}]}
                rm.revise(ctx, {'pid': pid, 'handoff': h, 'plan': plan, 'changes': {}, 'request': '검증 보완'})
                self.assertEqual([r['name'] for r in first['learningSkills']], names)
                self.assertEqual([r['name'] for r in again['learningSkills']], names)
        self.assertEqual(len(captured), 9)
        for i, payload in enumerate(captured):
            if i % 3:
                self.assertIn('0-29', {row['id'] for row in payload['catalog']})
        self.assertEqual(h, before)

    def test_required_ids_and_each_skill_are_preserved_under_tight_budget(self):
        rows = resources(5)
        required = ['0-29', '4-29']
        selection = candidates.select(rows, [f'skill-{i}' for i in range(5)], ['SQL'], 'A3', required)
        # 문맥을 줄이면 출력·문맥 여유를 먼저 빼고 남는 입력에 맞춘다.
        out = budget.pack(selection, 'system', {'request': '의미 있는 검증 조건을 유지한다.'}, context_limit=19000)
        self.assertTrue(set(required).issubset({r['id'] for r in out['catalog']}))
        self.assertTrue(all(out['catalogCounts']['perSkill'].values()))
        self.assertLessEqual(budget.tokens('system') + budget.tokens(out) + budget.FRAMING_RESERVE,
                             19000 - budget.OUTPUT_RESERVE - budget.CONTEXT_RESERVE)
        self.assertEqual(selection.required, required)


if __name__ == '__main__':
    unittest.main()

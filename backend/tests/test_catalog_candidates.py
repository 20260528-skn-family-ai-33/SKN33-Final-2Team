"""후보 수·근거·안별 정책·전체 입력 보호 회귀. 실제 DB/모델 호출 없음."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import catalog, catalog_budget as budget, catalog_candidates as candidates, llm, track_policy
from app.agents import roadmap as rm
from app.services import drafts


def resource(key, skill='SQL', **changes):
    value = {'id': key, 'title': key, 'type': 'course', 'kind': '강좌', 'provider': 'test',
             'skills': [skill], 'usable': True, 'hours': 4, 'timeStatus': 'confirmed', 'cost': 0,
             'content': '학습목표\nSQL 조인으로 조회 결과를 만든다.',
             'curriculum': {'coverage': 'public_outline', 'items': [{'title': 'SQL 조인 실습'}]}}
    return dict(value, **changes)


def resources(skills=3, count=30):
    return {f'{s}-{i:02}': resource(f'{s}-{i:02}', f'skill-{s}') for s in range(skills) for i in range(count)}


def measured(value):
    """정책 경계용 결정적 길이 계수. 실제 토크나이저 검증은 별도 DB 검사에서 수행."""
    return len(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)) // 4


class CandidateSelectionTests(unittest.TestCase):
    def test_per_skill_twenty_and_fair_union(self):
        rows = resources(5)
        selected = candidates.select(rows, [f'skill-{n}' for n in range(5)], ['SQL'], 'A3')
        self.assertEqual(list(selected.per_skill.values()), [20] * 5)
        self.assertEqual(len(selected.records), 100)
        self.assertEqual({r['skills'][0] for r in selected.records[:5]}, set(selected.skills))

    def test_same_course_across_skills_and_duplicate_provider_title_not_repeated(self):
        first = resource('one', skills=['s1', 's2'], title='SQL 강좌')
        rows = {'one': first, 'two': dict(first, id='two', title=' SQL   강좌 ')}
        selected = candidates.select(rows, ['s1', 's2'], ['SQL'], 'A2')
        self.assertEqual(len(selected.records), 1)

    def test_single_skill_does_not_pad_past_twenty_or_add_unrelated(self):
        rows = resources(2)
        selected = candidates.select(rows, ['skill-0'], ['SQL'], 'A2')
        self.assertEqual(len(selected.records), 20)
        self.assertTrue(all(r['skills'] == ['skill-0'] for r in selected.records))

    def test_free_filters_before_limit(self):
        rows = {str(n): resource(str(n), cost=100) for n in range(35)}
        rows.update({f'free-{n}': resource(f'free-{n}') for n in range(25)})
        rows['unknown'] = resource('unknown', cost=None)
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A1')
        self.assertEqual(len(selected.records), 20)
        self.assertTrue(all(r['cost'] == 0 for r in selected.records))

    def test_fast_prefers_short_but_keeps_relevant_long_course(self):
        rows = {'long': resource('long', hours=40), 'short': resource('short', hours=2),
                'unknown': resource('unknown', hours=None)}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A2')
        self.assertEqual(selected.records[0]['id'], 'short')
        self.assertEqual({r['id'] for r in selected.records}, set(rows))

    def test_challenge_follows_db_practice_policy_and_accepts_longer_courses(self):
        rows = {'a-lecture': resource('a-lecture', content='SQL 조인 이론', curriculum={'items': [{'title': 'SQL 조인 이론'}]}),
                'z-practice': resource('z-practice', difficulty='ADVANCED', hours=120)}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        self.assertEqual([r['id'] for r in selected.records], ['z-practice', 'a-lecture'])

    def test_tag_match_without_title_or_learning_evidence_is_not_padding(self):
        rows = {'wrong': resource('wrong', title='취미 강의', content='꽃꽂이', curriculum={'items': [{'title': '꽃다발'}]}),
                'right': resource('right', title='트랜잭션 복구', content='', curriculum={'items': [{'title': 'SQL 롤백'}]})}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A2')
        self.assertEqual([r['id'] for r in selected.records], ['right'])

    def test_fast_reviews_only_first_three_core_skills(self):
        selected = candidates.select(resources(5), [f'skill-{n}' for n in range(5)], ['SQL'], 'A2')
        self.assertEqual(selected.skills, ['skill-0', 'skill-1', 'skill-2'])
        self.assertEqual(list(selected.per_skill.values()), [20, 20, 20])
        self.assertEqual(len(selected.records), 60)

    def test_fast_excludes_broad_outline_but_challenge_keeps_relevant_course(self):
        rows = {'broad': resource('broad', title='SQL 종합 개발', content='', curriculum={'items':
                    [{'title': 'SQL 조인 구현'}] + [{'title': f'디자인 색상 {n}'} for n in range(5)]}),
                'focused': resource('focused', title='SQL 조인', content='')}
        self.assertEqual([r['id'] for r in candidates.select(rows, ['SQL'], ['SQL'], 'A2').records], ['focused'])
        self.assertIn('broad', {r['id'] for r in candidates.select(rows, ['SQL'], ['SQL'], 'A3').records})
        forced = candidates.select(rows, ['SQL'], ['SQL'], 'A2', required=['broad'])
        self.assertEqual(forced.records[0]['id'], 'broad')

    def test_fast_focus_boundary_and_sparse_outline_are_not_overfiltered(self):
        for count, related, kept in [(6, 2, True), (6, 1, False), (5, 1, True), (0, 0, True)]:
            with self.subTest(count=count, related=related):
                rows = {'r': resource('r', title='SQL', content='', curriculum={'items':
                    [{'title': f'SQL 조회 {n}'} for n in range(related)] +
                    [{'title': f'색상 디자인 {n}'} for n in range(count-related)]})}
                selected = candidates.select(rows, ['SQL'], ['SQL'], 'A2')
                self.assertEqual(bool(selected.records), kept)

    def test_challenge_values_verified_workflow_over_generic_practice(self):
        rows = {'basic': resource('basic', title='SQL 조인 조회', content='', curriculum={'items': [{'title': 'SQL 조인 실습'}]}),
                'project': resource('project', title='SQL 조인', hours=80, content='', curriculum={'items': [
                    {'title': 'SQL 조회 구현'}, {'title': 'SQL 결과 테스트'}, {'title': 'SQL 성능 개선'},
                    {'title': 'SQL 오류 복구'}, {'title': 'SQL 지연 측정과 검증'}, {'title': 'SQL 쿼리 최적화'}]})}
        selected = candidates.select(rows, ['SQL'], ['SQL 조인 조회'], 'A3')
        self.assertEqual(selected.records[0]['id'], 'project')
        self.assertLess(selected.assessments['project']['relevance'], selected.assessments['basic']['relevance'])

    def test_unrelated_practice_and_marketing_do_not_supply_challenge_depth(self):
        rows = {'x': resource('x', title='SQL', content='SQL 구현 테스트 개선 운영 전문가 프로젝트',
                             curriculum={'items': [{'title': 'SQL 이론'}, {'title': '디자인 구현 테스트 개선'},
                                                   {'title': '강의 평가 SQL 만족도 설문'}]})}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        self.assertEqual(selected.assessments['x']['practiceUnits'], 0)
        self.assertEqual(selected.assessments['x']['fit'], 0)

    def test_repeated_outline_does_not_inflate_depth(self):
        rows = {'x': resource('x', content='', curriculum={'items': [{'title': 'SQL 구현 실습'}] * 10})}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        self.assertEqual(selected.assessments['x']['totalUnits'], 1)
        self.assertEqual(selected.assessments['x']['practiceUnits'], 1)

    def test_challenge_difficulty_bonus_requires_multiple_depth_lessons(self):
        outline = {'items': [{'title': 'SQL 실행 계획 설계'}, {'title': 'SQL 부하 테스트'},
                             {'title': 'SQL 병목 원인 분석'}, {'title': 'SQL 성능 최적화'}]}
        rows = {level: resource(level, title='SQL', content='', difficulty=level, curriculum=outline)
                for level in ('BEGINNER', 'INTERMEDIATE', 'ADVANCED')}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        # 같은 제목은 중복 제거되므로 가점을 직접 비교한다.
        scores = selected.assessments
        self.assertGreater(scores['ADVANCED']['fit'], scores['INTERMEDIATE']['fit'])
        self.assertGreater(scores['INTERMEDIATE']['fit'], scores['BEGINNER']['fit'])
        self.assertEqual(selected.records[0]['id'], 'ADVANCED')

    def test_advanced_label_alone_or_intro_does_not_invent_depth(self):
        for outline in ({'items': [{'title': 'SQL 조인 실습'}]}, {'items': []}):
            rows = {level: resource(level, title='SQL', difficulty=level,
                                    content='SQL 아키텍처 설계\nSQL 성능 측정', curriculum=outline)
                    for level in ('BEGINNER', 'ADVANCED')}
            selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
            self.assertEqual(selected.assessments['BEGINNER']['fit'], selected.assessments['ADVANCED']['fit'])

    def test_deep_beginner_outranks_intermediate_follow_along(self):
        rows = {'deep': resource('deep', title='SQL', difficulty='BEGINNER', content='', curriculum={'items': [
                    {'title': 'SQL 조회 구현'}, {'title': 'SQL 성능 측정'},
                    {'title': 'SQL 병목 원인 분석'}, {'title': 'SQL 인덱스 설계'}]}),
                'follow': resource('follow', title='SQL', provider='other', difficulty='INTERMEDIATE',
                                   curriculum={'items': [{'title': f'SQL 조회 구현 {i}'} for i in range(8)]})}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        self.assertEqual(selected.records[0]['id'], 'deep')
        self.assertFalse(selected.assessments['deep']['shallowOutline'])

    def test_shallow_beginner_is_lower_priority_not_excluded(self):
        rows = {'x': resource('x', difficulty='BEGINNER', curriculum={'items': [
            {'title': f'SQL 조인 구현 {i}'} for i in range(6)]})}
        for track in ('A2', 'A3'):
            selected = candidates.select(rows, ['SQL'], ['SQL'], track)
            self.assertEqual([r['id'] for r in selected.records], ['x'])
            self.assertEqual(selected.assessments['x']['shallowOutline'], track == 'A3')
        required = candidates.select(rows, ['SQL'], ['SQL'], 'A3', required=['x'])
        self.assertEqual(required.records[0]['id'], 'x')

    def test_depth_uses_distinct_related_lessons_not_sections_or_marketing(self):
        rows = {'x': resource('x', difficulty='ADVANCED', content='SQL 성능 최적화', curriculum={'items': [
            {'section': 'SQL 아키텍처 설계', 'title': 'SQL 조인 구현'},
            {'title': '색상 배치 설계'}, {'title': 'SQL 최적화 입문'},
            *[{'title': 'SQL 부하 테스트'}] * 5]})}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        self.assertEqual(selected.assessments['x']['depthUnits'], 1)
        self.assertEqual(selected.assessments['x']['depthActions'], ['measure'])

    def test_unknown_difficulty_keeps_real_depth_without_assumed_level(self):
        rows = {level or 'unknown': resource(level or 'unknown', title='SQL', difficulty=level, content='',
                curriculum={'items': [{'title': 'SQL 실행 계획 설계'}, {'title': 'SQL 부하 테스트'}]})
                for level in (None, 'BEGINNER')}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        self.assertEqual(selected.assessments['unknown']['fit'], selected.assessments['BEGINNER']['fit'])
        self.assertIsNone(rows['unknown']['difficulty'])

    def test_challenge_excerpts_prioritize_measured_depth(self):
        rows = {'x': resource('x', content='', curriculum={'items': [
            {'title': 'SQL 기본 구현'}, {'title': 'SQL 성능 측정'}, {'title': 'SQL 장애 원인 분석'}]})}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        self.assertEqual([r[0] for r in candidates.entry(rows['x'], selected)['curriculum']], [1, 2])

    def test_counts_and_lesson_numbers_do_not_supply_goal_relevance(self):
        rows = {'x': resource('x', title='법률', content='', curriculum={'items': [
            {'title': '수업 10-2 법률 모델 설계'}, {'title': '수업 20-2 법률 성능 측정'}]})}
        self.assertFalse(candidates.select(rows, ['SQL'], ['SQL 문서 10건 질문 20개'], 'A3').records)

    def test_generic_check_or_permission_does_not_supply_cloud_depth(self):
        rows = {'x': resource('x', title='API', content='', difficulty='INTERMEDIATE', curriculum={'items': [
            {'title': '도구 점검 및 트러블슈팅'}, {'title': 'PDF 권한 암호 설계'}]})}
        selected = candidates.select(rows, ['SQL'], ['클라우드 API 배포', '동작 점검과 접근 권한'], 'A3')
        self.assertEqual(selected.assessments['x']['depthUnits'], 0)

    def test_shallow_outline_penalty_is_independent_of_difficulty_label(self):
        rows = {level: resource(level, title='SQL', difficulty=level, content='', curriculum={'items': [
            {'title': f'SQL 구현 {n}'} for n in range(6)]}) for level in ('BEGINNER', 'INTERMEDIATE', 'ADVANCED')}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A3')
        self.assertEqual(len({a['score'] for a in selected.assessments.values()}), 1)

    def test_metric_names_with_korean_particles_supply_depth(self):
        rows = {'x': resource('x', title='RAG', skill='RAG', content='', curriculum={'items': [
            {'title': 'Recall과 MRR로 검색 재보기'}, {'title': 'e2e Evaluation - 정확한 답변을 생성했는가?'}]})}
        selected = candidates.select(rows, ['RAG'], ['RAG 검색 답변'], 'A3')
        self.assertEqual(selected.assessments['x']['depthUnits'], 2)

    def test_model_deployment_compound_preserves_rollbacks_and_monitoring(self):
        rows = {'deploy': resource('deploy', title='모델 배포', content='', difficulty='INTERMEDIATE',
                    curriculum={'items': [{'title': title} for title in (
                        '소개', '배포할 모델 준비', '배포 및 모니터링 아키텍처 살펴보기',
                        'GitHub 환경으로 배포 제어', 'GitHub Actions로 모델 배포, 승격 및 롤백',
                        '배포된 모델 모니터링', '요약')]}),
                'unrelated': resource('unrelated', title='모델', content='', difficulty='ADVANCED',
                                     curriculum={'items': [{'title': '법률 추론 모델 설계'}]})}
        selected = candidates.select(rows, ['SQL'], ['모델 배포'], 'A3')
        assessment = selected.assessments['deploy']
        self.assertEqual(assessment['depthUnits'], 3)
        self.assertFalse(assessment['shallowOutline'])
        self.assertEqual(selected.assessments['unrelated']['depthUnits'], 0)
        excerpts = candidates.entry(rows['deploy'], selected)['curriculum']
        self.assertTrue(any('롤백' in text for _, text in excerpts))

    def test_model_deployment_topics_are_not_added_to_other_goals(self):
        topics = candidates.depth_terms(['SQL 조회'])
        self.assertFalse(candidates.matches('모델 배포 승격 롤백', topics))

    def test_cached_depth_respects_goal_vs_context_with_same_words(self):
        rows = {'x': resource('x', title='API', content='', curriculum={'items': [{'title': '권한 암호 설계'}]})}
        before = candidates.select(rows, ['SQL'], ['권한 API', '배포'], 'A3')
        after = candidates.select(rows, ['SQL'], ['API 배포', '권한'], 'A3')
        self.assertEqual(before.assessments['x']['depthUnits'], 1)
        self.assertEqual(after.assessments['x']['depthUnits'], 0)

    def test_section_keyword_does_not_mark_every_lesson_as_related_practice(self):
        rows = {'x': resource('x', title='RAG', skill='RAG', content='', curriculum={'items': [
            {'section': 'RAG 실습', 'title': 'RAG 검색 결과 검증'},
            *[{'section': 'RAG 실습', 'title': f'이미지 색상 {n}'} for n in range(6)]]})}
        fast = candidates.select(rows, ['RAG'], ['RAG'], 'A2')
        self.assertFalse(fast.records)
        self.assertEqual(fast.assessments['x']['relatedUnits'], 1)
        challenge = candidates.select(rows, ['RAG'], ['RAG'], 'A3')
        self.assertEqual(challenge.assessments['x']['practiceUnits'], 1)
        self.assertNotIn('build', challenge.assessments['x']['actions'])
        self.assertEqual([row[0] for row in candidates.entry(rows['x'], challenge)['curriculum']], [0])

    def test_section_alone_is_not_goal_evidence_for_fast_or_challenge(self):
        rows = {'x': resource('x', title='디자인 입문', skill='RAG', content='', curriculum={'items': [
            {'section': 'RAG 실습', 'title': f'색상 조합 {n}'} for n in range(7)]})}
        for track in ('A2', 'A3'):
            self.assertFalse(candidates.select(rows, ['RAG'], ['RAG'], track).records)

    def test_description_only_has_lower_confidence_than_verified_outline(self):
        text = 'SQL 구현 테스트 개선 운영'
        rows = {'outline': resource('outline', content='', curriculum={'items': [{'title': text}]}),
                'intro': resource('intro', content=text, curriculum={'items': []})}
        for track in ('A2', 'A3'):
            selected = candidates.select(rows, ['SQL'], ['SQL'], track)
            self.assertLess(selected.assessments['intro']['fit'], selected.assessments['outline']['fit'])

    def test_weak_book_does_not_receive_an_automatic_front_slot(self):
        rows = {str(n): resource(str(n), title=f'SQL 조인 조회 {n}') for n in range(10)}
        rows['book'] = resource('book', title='일반 자료', type='book', kind='도서', content='SQL', curriculum={'items': []})
        selected = candidates.select(rows, ['SQL'], ['SQL 조인 조회'], 'A2')
        self.assertEqual(selected.records[-1]['id'], 'book')
        required = candidates.select(rows, ['SQL'], ['SQL 조인 조회'], 'A2', required=['book'])
        self.assertEqual(required.records[0]['id'], 'book')

    def test_prerequisite_and_course_evaluation_are_excluded_from_search_and_excerpts(self):
        rows = {'x': resource('x', title='일반 과정', content='', curriculum={'items': [
            {'section': '개요', 'title': '선수지식 Python'},
            {'section': '마무리', 'title': '과정 평가'},
            {'section': '개요', 'title': '참고', 'description': '선수지식 Linux'}]})}
        for track in ('A1', 'A2', 'A3'):
            selected = candidates.select(rows, ['SQL'], ['Python Linux 평가'], track)
            self.assertFalse(selected.records)
            self.assertEqual(candidates.entry(rows['x'], selected)['curriculum'], [])

    def test_goal_profile_cache_is_bounded_and_invalidated_on_catalog_refresh(self):
        rows = {'x': resource('x')}
        for text in ('SQL', '조인', '조회', '결과', '실습', '목표'):
            candidates.select(rows, ['SQL'], [text], 'A2')
        self.assertLessEqual(len(candidates.cached_index(rows)['x']['query_profiles']), 4)
        refreshed = candidates.cached_index(copy.deepcopy(rows))
        self.assertEqual(refreshed['x']['query_profiles'], {})

    def test_challenge_excerpts_include_goal_related_validation_evidence(self):
        rows = {'x': resource('x', content='', curriculum={'items': [
            {'title': 'SQL 조인 개념'}, {'title': 'SQL 조인 평가와 개선'}, {'title': 'SQL 조인 조회 테스트'}]})}
        selected = candidates.select(rows, ['SQL'], ['SQL 조인 조회'], 'A3')
        positions = [r[0] for r in candidates.entry(rows['x'], selected)['curriculum']]
        self.assertEqual(positions, [1, 2])

    def test_fast_relevance_precedes_short_duration(self):
        rows = {'short': resource('short', title='기본 사용법', hours=1, content='', curriculum={'items': []}),
                'long': resource('long', title='SQL 트랜잭션', hours=120)}
        selected = candidates.select(rows, ['SQL'], ['SQL 트랜잭션'], 'A2')
        self.assertEqual(selected.records[0]['id'], 'long')

    def test_prerequisite_block_not_learning_evidence(self):
        lines = candidates.learning_lines('과정소개\n데이터 처리\n학습자의 선수능력\nLinux와 Bash\n학습목표\nSQL 조인')
        self.assertNotIn('Linux와 Bash', lines)
        self.assertIn('SQL 조인', lines)
        rows = {'x': resource('x', content='선수지식\nLinux\n학습목표\nSQL 조인', curriculum={'items': []})}
        selected = candidates.select(rows, ['SQL'], ['Linux'], 'A2')
        self.assertNotIn('Linux', candidates.entry(rows['x'], selected)['content'])

    def test_late_outline_evidence_keeps_position_and_omission(self):
        outline = [{'title': f'기초 {i}'} for i in range(60)] + [{'title': '설명 ' * 100 + '트랜잭션 롤백'}]
        rows = {'x': resource('x', curriculum={'coverage': 'public_outline', 'items': outline})}
        selected = candidates.select(rows, ['SQL'], ['트랜잭션'], 'A2')
        entry = candidates.entry(rows['x'], selected)
        self.assertEqual(entry['curriculum'][0][0], 60)
        self.assertIn('트랜잭션', entry['curriculum'][0][1])
        self.assertEqual(len(entry['curriculum']), 1)

    def test_suspended_and_missing_titles_never_become_evidence(self):
        rows = {'x': resource('x', curriculum={'items': [{'title': 'SQL 제거', 'suspended': True},
                                                        {'title': 'SQL 누락', 'title_missing': True}]})}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A2')
        self.assertEqual(candidates.entry(rows['x'], selected)['curriculum'], [])

    def test_rag_does_not_match_storage(self):
        self.assertEqual(candidates.matches('storage', candidates.query_terms(['RAG'])), 0)

    def test_no_evidence_is_marked_without_invention(self):
        rows = {'x': resource('x', content='', curriculum={'coverage': 'description_only', 'items': []})}
        selected = candidates.select(rows, ['SQL'], ['SQL'], 'A2')
        row = candidates.entry(rows['x'], selected)
        self.assertEqual(row['evidenceStatus'], 'unavailable')
        self.assertEqual(row['curriculum'], [])
        self.assertNotIn('content', row)

    def test_required_survives_dedup_and_rank_and_hints_do_not_bypass_cap(self):
        rows = resources(1)
        rows['last'] = resource('last', 'other')
        selected = candidates.select(rows, ['skill-0'], ['SQL'], 'A2', ['last'], ['0-29'])
        self.assertEqual(selected.records[0]['id'], 'last')
        self.assertEqual(selected.per_skill['skill-0'], 20)
        self.assertEqual(len(selected.records), 21)

    def test_deleted_and_over_limit_required_are_errors(self):
        with self.assertRaises(ValueError):
            candidates.select({}, ['SQL'], ['SQL'], 'A2', ['missing'])
        rows = resources(2)
        with self.assertRaises(ValueError):
            candidates.select(rows, ['skill-0'], ['SQL'], 'A2', list(rows)[:41])

    def test_cache_reuses_snapshot_and_refresh_rebuilds(self):
        rows = resources(1, 1)
        first = candidates.cached_index(rows)
        self.assertIs(candidates.cached_index(rows), first)
        changed = copy.deepcopy(rows)
        changed['0-00']['content'] = '새로운 SQL 설명'
        second = candidates.cached_index(changed)
        self.assertIsNot(first, second)
        self.assertIn('새로운', second['0-00']['description'])


class CandidateBudgetTests(unittest.TestCase):
    def setUp(self):
        self.counter = patch.object(budget, 'tokens', side_effect=measured)
        self.counter.start()
        self.addCleanup(self.counter.stop)

    def selection(self, skills=3, required=None):
        rows = resources(skills)
        return candidates.select(rows, [f'skill-{s}' for s in range(skills)], ['SQL'], 'A3', required)

    def test_default32_and_four_skill40(self):
        for n, expected in [(3, 32), (4, 40), (5, 40)]:
            with self.subTest(skills=n):
                out = budget.pack(self.selection(n))
                self.assertEqual(len(out['catalog']), expected)
                self.assertEqual(len(out['catalogSkillMap']), n)
                self.assertTrue(all(r['curriculum'] for r in out['catalog']))

    def test_full_previous_plan_and_request_reduce_candidates_not_input(self):
        selection = self.selection(4)
        payload = {'previous': {'text': 'x' * 37000}, 'request': {'wish': '유지해 주세요'}}
        out = budget.pack(selection, 'system', payload)
        self.assertLess(len(out['catalog']), 32)
        self.assertEqual(out['previous'], payload['previous'])
        self.assertEqual(out['request'], payload['request'])
        self.assertLessEqual(measured(out) + measured('system') + budget.FRAMING_RESERVE, budget.INPUT_TOKENS)

    def test_required_overflow_fails_instead_of_silent_drop(self):
        selected = self.selection(4, list(resources(4))[:40])
        with self.assertRaises(ValueError):
            budget.pack(selected, payload={'previous': 'x' * 37000})

    def test_required_33_expands_even_with_three_skills(self):
        required = list(resources(3))[:33]
        out = budget.pack(self.selection(3, required))
        self.assertTrue(set(required).issubset({r['id'] for r in out['catalog']}))
        self.assertLessEqual(len(out['catalog']), 40)

    def test_base_prompt_overflow_and_small_context_are_errors(self):
        with self.assertRaises(ValueError):
            budget.pack(self.selection(), system='x' * 45000)
        with self.assertRaises(ValueError):
            budget.pack(self.selection(), context_limit=4096)

    def test_empty_pool_is_not_invented(self):
        selected = candidates.select({}, ['SQL'], ['SQL'], 'A2')
        self.assertEqual(budget.pack(selected)['catalog'], [])

    def test_tokenizer_missing_and_hash_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'tokenizer.json'
            with self.assertRaises(ValueError):
                budget._tokenizer(str(path))
            path.write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                budget._tokenizer(str(path))


class RoadmapIntegrationTests(unittest.TestCase):
    def test_candidate_policy_is_passed_with_db_prompt_and_challenge_has_no_fast_cap(self):
        h = {'goal': 'SQL', 'prefs': {'weeklyHours': 6, 'deadlineWeeks': 12}, 'skillNames': ['skill-0']}
        with patch.object(catalog, 'items', return_value=resources(1)), patch.object(budget, 'tokens', side_effect=measured):
            out = rm._catalog_payload('A3', {'handoff': h}, 'unchanged DB prompt')
        self.assertEqual(out['trackGuidance']['candidatePreference'], track_policy.CANDIDATE_PREFERENCE['A3'])
        self.assertNotIn('maxWeeks', out['trackGuidance'])
        self.assertEqual(out['handoff']['prefs']['deadlineWeeks'], 12)

    def test_fast_guidance_does_not_filter_long_or_unknown_courses_or_mutate_input(self):
        rows = resources(5, 1)
        rows['0-00']['hours'] = 120
        rows['1-00']['hours'] = None
        h = {'goal': 'SQL', 'prefs': {'weeklyHours': 4, 'deadlineWeeks': 12},
             'skillNames': [f'skill-{n}' for n in range(5)]}
        base = {'handoff': h, 'skillTags': h['skillNames']}
        original = copy.deepcopy(base)
        with patch.object(catalog, 'items', return_value=rows), patch.object(budget, 'tokens', side_effect=measured):
            out = rm._catalog_payload('A2', base)
        self.assertEqual(base, original)
        self.assertEqual(out['trackGuidance']['maxWeeks'], 6)
        self.assertEqual(out['handoff']['prefs']['deadlineWeeks'], 6)
        self.assertEqual(out['trackGuidance']['coreSkills'], h['skillNames'][:3])
        self.assertEqual(out['skillTags'], h['skillNames'])
        self.assertEqual(out['handoff']['skillNames'], h['skillNames'][:3])
        self.assertEqual({r['id'] for r in out['catalog']}, {'0-00', '1-00', '2-00'})
        self.assertEqual(next(r['hours'] for r in out['catalog'] if r['id'] == '0-00'), 120)
        self.assertIsNone(next(r['hours'] for r in out['catalog'] if r['id'] == '1-00'))

    def test_shorter_user_deadline_is_kept_as_plan_guidance(self):
        with patch.object(catalog, 'items', return_value=resources(1)), patch.object(budget, 'tokens', side_effect=measured):
            for weeks, expected in [(None, 6), (4, 4), (6, 6), (12, 6)]:
                h = {'goal': 'SQL', 'prefs': {'deadlineWeeks': weeks}, 'skillNames': ['skill-0']}
                out = rm._catalog_payload('A2', {'handoff': h})
                self.assertEqual(out['trackGuidance']['maxWeeks'], expected)

    def test_fast_task_tags_survive_generation_regeneration_and_revision(self):
        skills = ['RESTful API 서버 아키텍처', '웹 프레임워크 (FastAPI/Django)', '클라우드', 'Docker', 'MLOps']
        rows = {str(n): resource(str(n), skill, title=f'SQL API 서버 실습 {n}') for n, skill in enumerate(skills)}
        h = {'goal': 'SQL API 서버 배포', 'prefs': {'weeklyHours': 6, 'deadlineWeeks': 12}, 'skillNames': skills}
        task = {'id': 'docker-task', 'stage': 3, 'title': 'Docker로 모델 배포', 'res': None, 'hours': 2,
                'how': '컨테이너를 배포한다. 응답을 확인한다.', 'skills': ['Docker', 'MLOps']}
        captured = []

        def capture(ctx, system, payload, **kwargs):
            captured.append(payload)
            self.assertEqual(payload['skillTags'], skills)
            self.assertEqual(payload['trackGuidance']['coreSkills'], skills[:3])
            self.assertEqual(payload['trackGuidance']['maxCoreSkills'], 3)
            self.assertEqual(payload['handoff']['prefs']['deadlineWeeks'], 6)
            self.assertEqual({r['id'] for r in payload['catalog']}, {'0', '1', '2'})
            self.assertIn('보조 태그', payload['trackGuidance']['taskSkillNote'])
            return {'acts': [{**task, 'key': task['id']}], 'weeklyHours': 6}

        with patch.object(catalog, 'items', return_value=rows), patch.object(catalog, 'skill_names', return_value=skills), \
                patch.object(budget, 'tokens', side_effect=measured), patch.object(rm, '_sys', return_value='DB prompt unchanged'), \
                patch.object(rm.rt, 'llm_json', side_effect=capture), \
                patch.object(rm.rt, 'run', side_effect=lambda ctx, name, task, inp, mock, api, **kw: api(None)):
            ctx = SimpleNamespace(mode='openai')
            first = rm.option(ctx, {'pid': 'A2', 'handoff': h})
            again = rm.option(ctx, {'pid': 'A2', 'handoff': h, 'previous': {'acts': [task]}, 'request': {'wish': '설명 보완'}})
            plan = {'opt': 'A2', 'name': 'Fast', 'hours': 6, 'start': 1, 'acts': [task]}
            revised = rm.revise(ctx, {'pid': 'A2', 'handoff': h, 'plan': plan, 'changes': {}, 'request': '설명 보완'})
        self.assertEqual(len(captured), 3)
        self.assertEqual(h['skillNames'], skills)
        self.assertEqual(h['prefs']['deadlineWeeks'], 12)
        self.assertEqual(captured[-1]['current']['acts'][0]['skills'], ['Docker', 'MLOps'])
        for out in (first, again, revised):
            self.assertEqual(out['acts'][0]['skills'], ['Docker', 'MLOps'])

    def test_fast_task_tags_still_require_registered_names_and_three_per_task(self):
        with patch.object(catalog, 'skill_names', return_value=['Docker', 'MLOps', 'SQL', 'Python']):
            out = rm.finish_option('A2', {'acts': [{'title': '검증 과제', 'skills': [
                '등록되지 않은 스킬', 'Docker', 'MLOps', 'Docker', 'SQL', 'Python']}]}, 'test')
        self.assertEqual(out['acts'][0]['skills'], ['Docker', 'MLOps', 'SQL'])

    def test_actual_handoff_supplies_canonical_skills_and_changes_cache_key_with_policy(self):
        d = {'goal': 'SQL 조회 개선', 'prefs': {},
             'diag': {'startStage': 1, 'startReason': '기초부터', 'known': [], 'gaps': ['SQL'],
                      'competencies': ['SQL 조회'], 'outcome': '조회 결과', 'resourceIds': []}}
        with patch.object(catalog, 'items', return_value={'sql': resource('sql')}):
            h = drafts.build_handoff(d)
            with patch.object(track_policy, 'VERSION', 'next-policy'):
                changed = drafts.build_handoff(d)
        self.assertEqual(h['skillNames'], ['SQL'])
        self.assertNotEqual(h['key'], changed['key'])

    def test_generation_and_revision_send_bounded_whole_payload(self):
        rows = resources(3)
        h = {'goal': 'SQL', 'prefs': {}, 'skillNames': ['skill-0', 'skill-1', 'skill-2']}
        captured = []

        def capture(ctx, system, payload, **kwargs):
            self.assertEqual(kwargs.get('role'), 'roadmap')
            captured.append((system, payload))
            return {'acts': [{'stage': 2, 'res': payload['catalog'][0]['id'], 'how': '학습 후 확인한다.'}]}

        def run(ctx, name, task, inp, mock, api, **kwargs):
            return api(None)

        with patch.object(catalog, 'items', return_value=rows), patch.object(catalog, 'skill_names', return_value=h['skillNames']), \
                patch.object(budget, 'tokens', side_effect=measured), patch.object(rm, '_sys', return_value='DB system prompt'), \
                patch.object(rm.rt, 'llm_json', side_effect=capture), patch.object(rm.rt, 'run', side_effect=run):
            ctx = SimpleNamespace(mode='openai')
            rm.option(ctx, {'pid': 'A2', 'handoff': h, 'request': {'wish': '유지'}, 'previous': {'acts': [{'res': '0-29'}]}})
            plan = {'opt': 'A2', 'name': 'Fast', 'hours': 4, 'start': 1,
                    'acts': [{'id': 'old', 'stage': 2, 'title': '기존 자료', 'res': '0-29', 'hours': 4}]}
            rm.revise(ctx, {'pid': 'A2', 'handoff': h, 'plan': plan, 'changes': {}, 'request': '수정 요청'})
        self.assertEqual(len(captured), 2)
        self.assertIn('previous', captured[0][1])
        self.assertIn('current', captured[1][1])
        for system, payload in captured:
            self.assertTrue(system.startswith('DB system prompt'))
            self.assertIn('0-29', {r['id'] for r in payload['catalog']})
            self.assertEqual(len(payload['catalog']), 32)
            self.assertLessEqual(measured(system) + measured(payload) + budget.FRAMING_RESERVE, budget.INPUT_TOKENS)

    def test_fast_model_choice_is_not_rejected_by_course_time_limit(self):
        rows = {'long': resource('long', hours=120)}
        h = {'goal': 'SQL', 'prefs': {'weeklyHours': 4}, 'skillNames': ['SQL']}
        with patch.object(catalog, 'items', return_value=rows), patch.object(catalog, 'skill_names', return_value=['SQL']), \
                patch.object(budget, 'tokens', side_effect=measured), patch.object(rm, '_sys', return_value='DB prompt'), \
                patch.object(rm.rt, 'llm_json', return_value={'acts': [{'res': 'long', 'stage': 2}]}), \
                patch.object(rm.rt, 'run', side_effect=lambda ctx, name, task, inp, mock, api, **kw: api(None)):
            out = rm.option(SimpleNamespace(mode='openai'), {'pid': 'A2', 'handoff': h})
        self.assertEqual(out['acts'][0]['res'], 'long')
        self.assertEqual(out['acts'][0]['hours'], 120)

    def test_selected_and_existing_resources_preserved_in_all_tracks(self):
        rows = resources(3)
        rows['chosen'] = resource('chosen', 'other')
        h = {'goal': 'SQL', 'prefs': {}, 'skillNames': ['skill-0', 'skill-1', 'skill-2'],
             'selectedResourceIds': ['chosen']}
        with patch.object(catalog, 'items', return_value=rows), patch.object(budget, 'tokens', side_effect=measured):
            for pid in ('A1', 'A2', 'A3'):
                out = rm._catalog_payload(pid, {'handoff': h}, extra_ids=['0-29'])
                self.assertTrue({'chosen', '0-29'}.issubset({r['id'] for r in out['catalog']}))

    def test_explicit_unknown_or_too_many_skills_fail(self):
        with patch.object(catalog, 'items', return_value=resources(6)):
            for skills in ([], ['unknown'], [f'skill-{n}' for n in range(6)]):
                with self.subTest(skills=skills), self.assertRaises(llm.LlmError):
                    rm._catalog_payload('A2', {'handoff': {'goal': 'SQL', 'prefs': {}, 'skillNames': skills}})


if __name__ == '__main__':
    unittest.main()

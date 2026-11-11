"""#147: 관련성은 공통으로 검사하고 가격·난이도·실제 시간 정책만 코스별로 적용한다."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from app import course_levels
from app.agents.resource_instructions import instructions
from app.agents.resource_recommendations import recommend_from_catalog, recommend_resources
from app.services import resource_rag as rag
from app.services import resource_evidence as evidence


class CoursePolicyTests(unittest.TestCase):
    name = 'SQL 쿼리 튜닝 & 인덱스 최적화'
    goal = 'PostgreSQL 실행계획의 인덱스 스캔 비용을 비교한다'
    lesson = 'PostgreSQL 실행계획의 순차 스캔과 인덱스 스캔 비용을 측정하고 비교하는 실습'

    def test_log_build_and_container_deploy_keep_their_own_stage_in_every_track(self):
        project = {'goal': 'Python으로 로그를 집계하고 Docker로 API를 배포한다'}
        specs = [{'name': name, 'application': '생성된 코스의 별도 예시'} for name in ('Python', 'Docker')]
        for track, level in [('A1', 'BEGINNER'), ('A2', 'BEGINNER'), ('A3', 'ADVANCED')]:
            course = {'id': track, 'learningSkills': specs}
            items = {name: {**self.item(name, level, lesson=lesson), 'skills': [name]} for name, lesson in
                     [('Python', 'Python 로그 파일 읽기와 집계'), ('Docker', 'Docker로 API 배포 실습')]}
            def search(kind, ids, vector, limit, free):
                return [dict(resource_id=rid, similarity=.8, current_cost=0) for rid in ids]
            pools, _ = rag.retrieve(project, {'skills': specs}, items, course,
                                    embed=lambda ts: [[1.] * rag.DIMENSIONS for _ in ts], search=search)
            common = evidence.course_selection(project, {'skills': specs}, course)
            self.assertEqual([evidence._stage(project, s) for s in common['skills']], ['build', 'operate'])
            solo = evidence.course_selection(project, {'skills': specs[:1]}, course)
            self.assertEqual(solo['skills'][0], common['skills'][0])
            self.assertEqual([[c['id'] for c in row['courses']] for row in pools], [['Python'], ['Docker']])

    def test_fixed_application_precedes_course_example_for_stage(self):
        project = {'goal': '서비스 배포'}
        spec = {'name': 'Python', 'application': '운영 모니터링'}
        selection = {'skills': [spec], 'commonApplications': {'Python': '로그 집계 구현'}}
        common = evidence.course_selection(project, selection, {'learningSkills': [spec]})
        self.assertEqual(evidence._stage(project, common['skills'][0]), 'build')

    def test_security_log_analysis_needs_evidence_in_a_learning_unit(self):
        name = 'SQL 기본 문법 & 조인'
        def allowed(goal, table, lesson):
            project = {'goal': goal}
            spec = {'name': name, 'application': goal}
            common = evidence.course_selection(project, {'skills': [spec]}, {'learningSkills': [spec]})
            item = {**self.item('course', lesson=lesson), 'title': table, 'skills': [name]}
            return evidence.course_applicable(evidence.facts(item, project, common), common['skills'][0])
        goal = '계정 권한과 접근 로그의 정상·거절 사례를 SQL로 분류하고 해석한다'
        self.assertFalse(allowed(goal, 'SQL 입문', 'SQL 주문 테이블 조회 실습'))
        self.assertTrue(allowed(goal, 'SQL로 인증 이벤트 분석', 'SQL로 접근 로그의 거절 건수를 집계하는 실습'))
        self.assertTrue(allowed('SQL로 주문 내역을 조회한다', 'SQL 입문', 'SQL 주문 테이블 조회 실습'))

    def test_audit_scope_fills_only_missing_slots_in_model_candidates(self):
        name = 'SQL 기본 문법 & 조인'
        goal = '계정 권한과 접근 로그의 정상·거절 사례를 데이터 분석 기법으로 분류하고 점검 결과를 해석하는 방법을 배우고 싶어요.'
        spec = {'name': name, 'application': goal}
        pre = {'project': {'goal': goal}, 'selection': {'skills': [spec]}}

        def search(kind, ids, vector, limit, free):
            return [dict(resource_id=rid, similarity=.8, current_cost=items[rid]['cost']) for rid in ids]

        def model(ctx, system, payload, role):
            cards = payload['skills'][0]['courses']
            self.assertEqual({row['title'] for row in cards}, expected)
            self.assertEqual(len(cards), len(expected))
            for row in cards:
                self.assertIn(name, row['eligibleSkills'])
                self.assertEqual(row['learningEvidence']['scopeMatch'], row['title'].startswith('직접'))
                if not row['learningEvidence']['scopeMatch']:
                    self.assertIn('접근 로그 분석', row['learningEvidence']['unverifiedTargetTopics'])
            return {'skills': [{'name': name, 'courses': [{'key': cards[0]['choiceKey']}], 'books': []}]}

        for track, level in [('A1', 'BEGINNER'), ('A2', 'INTERMEDIATE'), ('A3', 'ADVANCED')]:
            with self.subTest(track=track):
                items = {rid: {**self.item(rid, level, lesson='SQL 주문 테이블 조회 실습'), 'skills': [name]}
                         for rid in ('기초1', '기초2', '기초3', '이수', '중복', '코스 밖', '태그만')}
                items['중복']['title'] = '기초1'
                items['태그만']['curriculum']['items'][0]['title'] = '사용자 인터뷰 실습'
                if track == 'A1':
                    items['코스 밖']['cost'] = 1000
                else:
                    items['코스 밖']['difficulty'] = 'ADVANCED' if track == 'A2' else 'BEGINNER'
                course = {'id': track, 'learningSkills': [spec]}
                with patch('app.catalog.items', return_value=items), \
                     patch.object(rag, 'cached_vectors', side_effect=lambda ts: [[1.] * rag.DIMENSIONS for _ in ts]), \
                     patch.object(rag, 'search_vectors', side_effect=search), \
                     patch('app.agents.runtime.llm_json', side_effect=model):
                    for expected, completed in [({'기초1', '기초2', '기초3'}, {'이수'}),
                                                ({'기초1', '기초2'}, {'이수', '기초3'})]:
                        result = recommend_from_catalog(Mock(live=True), pre, course, completed=frozenset(completed))
                        self.assertIn('접근 로그 분석', result['skills'][0]['courses'][0]['unverifiedTargetTopics'])
                    for count in range(1, 5):
                        rid = f'직접{count}'
                        items[rid] = {**self.item(rid, level, lesson='SQL로 권한별 접근 로그의 거절 건수를 집계하고 검증하는 실습'),
                                      'skills': [name]}
                        expected = {f'직접{i}' for i in range(1, count + 1)}
                        expected.update(f'기초{i}' for i in range(1, 4 - count))
                        result = recommend_from_catalog(Mock(live=True), pre, course, completed=frozenset({'이수'}))
                        self.assertTrue(result['skills'][0]['selectedCourse'].startswith('직접'))

    def test_cross_skill_key_preserves_other_choices_and_retries_only_empty_skill(self):
        project = {'goal': 'Python으로 로그를 집계하고 Docker로 API를 배포한다'}
        specs = [{'name': n} for n in ('Python', 'Docker')]
        items = {n: {**self.item(n, lesson=lesson), 'skills': [n]} for n, lesson in
                 [('Python', 'Python 로그 집계 실습'), ('Docker', 'Docker API 배포 실습')]}
        pools = [{'name': n, 'courses': [item], 'books': []} for n, item in items.items()]
        for mixed, recovered in [(True, True), (False, True), (False, False)]:
            first = {'skills': [{'name': 'Python', 'courses': [{'key': 'S1-C1'}], 'books': []},
                                {'name': 'Docker', 'courses': ([{'key': 'S2-C1'}] if mixed else []) +
                                 [{'key': 'S1-C1'}], 'books': []}]}
            model = Mock(side_effect=[first, {'skills': [{'name': 'Docker', 'courses':
                         [{'key': 'S2-C1' if recovered else 'S1-C1'}]}]}])
            result = recommend_resources(project, {'skills': specs}, items, model,
                                         course={'id': 'A1', 'learningSkills': specs}, retrieved_pools=pools)
            self.assertEqual([s['selectedCourse'] for s in result['skills']], ['Python', 'Docker' if recovered else None])
            self.assertEqual(model.call_count, 1 if mixed else 2)
            if not mixed:
                retry = model.call_args.args[1]['skills']
                self.assertEqual([(s['name'], [c['choiceKey'] for c in s['courses']]) for s in retry],
                                 [('Docker', ['S2-C1'])])

    def item(self, rid, level='INTERMEDIATE', hours=1, cost=0, lesson=None, **extra):
        return dict(id=rid, title=rid, type='course', usable=True, skills=[self.name],
                    provider='검사용 교육원', difficulty=level, hours=hours, cost=cost,
                    timeStatus='confirmed', estimated=[],
                    curriculum={'items': [{'title': lesson or self.lesson}]}, **extra)

    def retrieve(self, items, track):
        self.queries = []
        self.search_ids = []
        skill = dict(name=self.name, application=self.goal)
        def embed(texts):
            self.queries.extend(texts)
            return [[1.] * rag.DIMENSIONS for _ in texts]
        def search(kind, ids, vector, limit, free):
            self.search_ids.extend(ids)
            return [dict(resource_id=rid, similarity=items[rid].get('retrievalScore', .8),
                         current_cost=items[rid]['cost']) for rid in ids]
        pools, _ = rag.retrieve({'goal': self.goal}, {'skills': [skill]}, items,
                                {'id': track, 'learningSkills': [skill]}, embed=embed, search=search)
        return pools

    def test_eligibility_rejects_price_booleans_and_disallows_low_challenge_levels(self):
        self.assertFalse(course_levels.eligible({'cost': False}, 'A1'))
        for level in ('ADVANCED', 'UPPER_INTERMEDIATE', 'INTERMEDIATE', 'BEGINNER', None):
            row = {'difficulty': level}
            self.assertEqual(course_levels.eligible(row, 'A2'), level not in ('ADVANCED', 'UPPER_INTERMEDIATE'))
            self.assertEqual(course_levels.eligible(row, 'A3'), level in ('ADVANCED', 'UPPER_INTERMEDIATE'))

    def test_search_query_and_search_universe_are_common_but_track_conditions_are_strict(self):
        items = {level: self.item(level, level) for level in
                 ('ADVANCED', 'UPPER_INTERMEDIATE', 'INTERMEDIATE', 'BEGINNER')}
        items['paid'] = self.item('paid', cost=100)
        expected = {'A1': set(items) - {'paid'}, 'A2': {'INTERMEDIATE', 'BEGINNER', 'paid'},
                    'A3': {'ADVANCED', 'UPPER_INTERMEDIATE'}}
        queries = []
        for track in expected:
            with self.subTest(track=track):
                pools = self.retrieve(items, track)
                self.assertEqual({row['id'] for row in pools[0]['courses']}, expected[track])
                self.assertEqual(set(self.search_ids), set(items))
                queries.append(self.queries)
        self.assertEqual(queries, [queries[0]] * 3)

    def test_challenge_uses_six_high_courses_before_any_upper_intermediate(self):
        items = {f'high{i}': self.item(f'high{i}', 'ADVANCED', retrievalScore=.4) for i in range(7)}
        items['upper'] = self.item('upper', 'UPPER_INTERMEDIATE', retrievalScore=.99)
        cards = self.retrieve(items, 'A3')[0]['courses']
        self.assertEqual(len(cards), 6)
        self.assertTrue(all(row['difficulty'] == 'ADVANCED' for row in cards))

    def test_completed_ids_excluded_before_vector_limit_for_all_tracks(self):
        skill = {'name': self.name, 'application': self.goal}
        pre = {'project': {'goal': self.goal}, 'selection': {'skills': [skill]}}
        items = {f'{level}-{i}': self.item(f'{level}-{i}', level)
                 for level in ('INTERMEDIATE', 'ADVANCED') for i in range(7)}
        # 같은 제목이라도 재수강 여부는 ID로만 판단한다.
        for level in ('INTERMEDIATE', 'ADVANCED'):
            items[f'{level}-0']['title'] = items[f'{level}-1']['title']
        completed = frozenset({'INTERMEDIATE-0', 'ADVANCED-0'})

        def search(kind, ids, vector, limit, free):
            self.assertTrue(completed.isdisjoint(ids))
            return [dict(resource_id=rid, similarity=.9, current_cost=0) for rid in ids[:limit]]

        def model(ctx, system, payload, role):
            row, = payload['skills']
            self.assertEqual(len(row['courses']), 6)
            return {'skills': [{'name': row['name'], 'courses': [{'key': row['courses'][0]['choiceKey']}], 'books': []}]}

        with patch('app.catalog.items', return_value=items), \
             patch.object(rag, 'cached_vectors', side_effect=lambda ts: [[1.] * rag.DIMENSIONS for _ in ts]), \
             patch.object(rag, 'search_vectors', side_effect=search), \
             patch('app.agents.runtime.llm_json', side_effect=model) as llm:
            for track in ('A1', 'A2', 'A3'):
                option = {'id': track, 'learningSkills': [skill]}
                result = recommend_from_catalog(Mock(live=True), pre, option, completed=completed)
                matches = {r['resourceId'] for r in result['retrieval']['matches']}
                self.assertEqual(len(matches), 6)
                self.assertTrue(completed.isdisjoint(matches))
                selected = result['skills'][0]['selectedCourse']
                self.assertIn(selected, matches)
                if track == 'A3':
                    self.assertEqual(items[selected]['difficulty'], 'ADVANCED')
            self.assertEqual(llm.call_count, 3)
            empty = recommend_from_catalog(Mock(live=True), pre, option, completed=frozenset(items))
            self.assertIsNone(empty['skills'][0]['selectedCourse'])
            self.assertEqual(llm.call_count, 3)
        self.assertTrue(completed.issubset(items))

    def test_challenge_fills_only_the_shortfall_with_upper_intermediate(self):
        items = {f'high{i}': self.item(f'high{i}', 'ADVANCED') for i in range(2)}
        items.update({f'upper{i}': self.item(f'upper{i}', 'UPPER_INTERMEDIATE') for i in range(6)})
        cards = self.retrieve(items, 'A3')[0]['courses']
        self.assertEqual([row['difficulty'] for row in cards], ['ADVANCED'] * 2 + ['UPPER_INTERMEDIATE'] * 4)

    def test_unrelated_high_courses_and_low_courses_never_fill_a_challenge_shortfall(self):
        items = {f'low{i}': self.item(f'low{i}', 'BEGINNER') for i in range(8)}
        items['wrong'] = self.item('wrong', 'ADVANCED', lesson='사용자 인터뷰 설문지 작성 실습')
        items['upper'] = self.item('upper', 'UPPER_INTERMEDIATE')
        self.assertEqual([r['id'] for r in self.retrieve(items, 'A3')[0]['courses']], ['upper'])

    def test_crash_keeps_the_six_shortest_without_reserving_vector_leaders(self):
        items = {str(i): self.item(str(i), hours=(i + 1) / 10, retrievalScore=.1 + .02 * i)
                 for i in range(30)}
        items['advanced'] = self.item('advanced', 'ADVANCED', hours=.01)
        items['upper'] = self.item('upper', 'UPPER_INTERMEDIATE', hours=.02)
        cards = self.retrieve(items, 'A2')[0]['courses']
        self.assertEqual([row['id'] for row in cards], [str(i) for i in range(6)])

    def test_prerequisite_and_title_only_matches_are_not_learning_evidence(self):
        items = {'valid': self.item('valid')}
        items['title'] = self.item('title', lesson='사용자 인터뷰 실습')
        items['title']['title'] = self.goal
        items['prerequisite'] = self.item('prerequisite')
        items['prerequisite']['curriculum']['items'][0]['section'] = '선수지식'
        self.assertEqual([row['id'] for row in self.retrieve(items, 'A1')[0]['courses']], ['valid'])

    def test_direct_model_payload_filters_forbidden_crash_levels_without_mutation(self):
        items = {'low': self.item('low'), 'high': self.item('high', 'ADVANCED')}
        before = deepcopy(items)
        skill = {'name': self.name, 'application': self.goal}
        captured = {}
        def generate(system, payload):
            captured.update(payload)
            return {'skills': [{'name': self.name, 'courses': [{'key': payload['skills'][0]['courses'][0]['choiceKey']}], 'books': []}]}
        result = recommend_resources({'goal': self.goal}, {'skills': [skill]}, items, generate,
                                     course={'id': 'A2', 'learningSkills': [skill]})
        self.assertEqual([r['title'] for r in captured['skills'][0]['courses']], ['low'])
        self.assertEqual(result['skills'][0]['selectedCourse'], 'low')
        self.assertEqual(items, before)

    def test_instructions_state_the_same_strict_policies(self):
        self.assertIn('cost=0', instructions('A1'))
        self.assertIn('ADVANCED(상)·UPPER_INTERMEDIATE(중상) 강좌는 제외', instructions('A2'))
        self.assertIn('중·하 강좌는 제외', instructions('A3'))

    def test_rejected_learning_evidence_keeps_the_reason_without_calling_a_model(self):
        row = self.item('wrong', lesson='PostgreSQL 서버 설치 안내')
        skill = {'name': self.name, 'application': self.goal}
        generate = Mock()
        result = recommend_resources({'goal': self.goal}, {'skills': [skill]}, {'wrong': row}, generate,
                                     course={'id': 'A2', 'learningSkills': [skill]},
                                     retrieved_pools=[{'name': self.name, 'application': self.goal,
                                                       'courses': [row], 'books': []}])
        generate.assert_not_called()
        self.assertEqual(result['skills'][0]['courses'], [])
        self.assertNotEqual(result['skills'][0]['courseDiagnostic']['reason'], 'no_candidates')

    def test_actual_domain_lesson_words_survive_without_conjoining_taxonomy_alternatives(self):
        for name, goal, lesson, expected_stack in (
            ('클라우드 컴퓨팅 (AWS/Azure)', '두 가용 영역과 로드밸런서로 고가용성을 구성한다',
             'Multi-AZ의 장애 조치 테스트와 부하 분산 구성', set()),
            ('머신러닝 프레임워크 (PyTorch/TensorFlow)', 'PyTorch 사전학습 모델로 전이학습을 구현한다',
             'torchvision 사전학습 백본을 동결하고 분류 헤드를 미세조정하는 실습', {'pytorch'}),
            ('데이터 웨어하우스 & OLAP', '고객 차원과 팩트 테이블을 설계한다',
             '차원표의 대리 키와 사실표의 주문 키를 연결하는 실습', set()),
        ):
            with self.subTest(name=name):
                skill = {'name': name, 'application': goal}
                project = {'goal': goal, 'desiredCompetencies': name}
                common = evidence.course_selection(project, {'skills': [skill]}, {'learningSkills': [skill]})
                row = dict(id='actual', title=name, skills=[name], type='course', usable=True,
                           cost=0, difficulty='INTERMEDIATE', hours=1,
                           curriculum={'items': [{'title': lesson}]})
                info = evidence.facts(row, project, common)
                self.assertEqual(set(info['suitability'][name]['requiredStack']), expected_stack)
                self.assertTrue(evidence.course_applicable(info, common['skills'][0]))
                row['curriculum'] = {'items': [{'title': '강사 소개와 교육 과정 평가'}]}
                self.assertFalse(evidence.course_applicable(evidence.facts(row, project, common), common['skills'][0]))

    def test_entra_mfa_does_not_teach_service_account_role_scope_by_product_name(self):
        name = '클라우드 IAM & 접근 제어'
        goal = '클라우드 서비스 계정의 역할과 허용 범위를 설정한다'
        skill = {'name': name, 'application': goal}
        project = {'goal': goal}
        common = evidence.course_selection(project, {'skills': [skill]}, {'learningSkills': [skill]})
        mfa = dict(id='mfa', type='course', usable=True, title='Microsoft Entra ID에서 인증 방법 관리 및 구현',
                   skills=[name], cost=0, difficulty='INTERMEDIATE', hours=.5,
                   content='조건부 액세스 정책을 사용하여 다단계 인증을 구성합니다.',
                   curriculum={'items': [{'title': 'Microsoft Entra ID에서 다단계 인증 구성'},
                                         {'title': 'Microsoft Entra ID에서 셀프 서비스 암호 재설정 구성'}]})
        roles = {**mfa, 'id': 'roles', 'title': '서비스 주체의 역할 기반 리소스 접근',
                 'curriculum': {'items': [{'title': '서비스 계정에 역할을 할당하고 리소스 권한 범위를 구성하는 실습'}]}}
        self.assertFalse(evidence.course_applicable(evidence.facts(mfa, project, common), common['skills'][0]))
        self.assertTrue(evidence.course_applicable(evidence.facts(roles, project, common), common['skills'][0]))

    def test_explicit_airflow_and_redis_goals_are_not_replaced_by_other_products(self):
        for name, goal, wanted_title, wanted_lesson, wrong_title, wrong_lesson in (
            ('ETL & 데이터 파이프라인', '수집·변환·적재를 Airflow DAG로 실행한다',
             'Airflow 배치 의존성 실습', 'Airflow DAG의 태스크 의존성과 재시도 실행 결과를 검증한다',
             'Databricks 데이터 파이프라인', 'Lakeflow 데이터 파이프라인의 파일 수집·변환·적재와 재시도 정책을 구현한다'),
            ('대용량 트래픽 처리 & 캐싱', 'Redis TTL 캐시를 적용하고 DB 부하를 확인한다',
             'Redis 조회 캐싱', 'TTL 만료와 캐시 무효화를 적용해 DB 조회 횟수를 비교하는 실습',
             '실전 Django 최적화', 'Django ORM 인덱스와 DB 잠금 전략을 구현하고 트래픽 처리 성능을 검증한다'),
        ):
            with self.subTest(name=name):
                skill = {'name': name, 'application': goal}
                project = {'goal': goal}
                common = evidence.course_selection(project, {'skills': [skill]}, {'learningSkills': [skill]})
                base = dict(id='actual',type='course',usable=True,skills=[name],cost=0,
                            difficulty='ADVANCED',hours=1)
                wanted = {**base,'title':wanted_title,'curriculum':{'items':[{'title':wanted_lesson}]}}
                other = {**base,'title':wrong_title,'curriculum':{'items':[{'title':wrong_lesson}]}}
                self.assertTrue(evidence.course_applicable(evidence.facts(wanted,project,common),common['skills'][0]))
                self.assertFalse(evidence.course_applicable(evidence.facts(other,project,common),common['skills'][0]))
                if name.startswith('ETL'):
                    # 사용자 목표가 도구를 지정하지 않은 일반 파이프라인이면 해당 구현을 허용한다.
                    generic = {'goal':'데이터 파이프라인을 구현한다'}
                    generated = {'name': name, 'application': 'Airflow DAG로 작업을 실행한다'}
                    generic_selection = evidence.course_selection(generic,{'skills':[generated]},{'learningSkills':[generated]})
                    self.assertTrue(evidence.course_applicable(evidence.facts(other,generic,generic_selection),generic_selection['skills'][0]))

    def test_six_grounded_transfer_labs_precede_a_concept_only_candidate_in_final_payload(self):
        name = '머신러닝 프레임워크 (PyTorch/TensorFlow)'
        goal = 'PyTorch 사전학습 분류기의 헤드를 바꾸어 전이학습한다'
        skill = {'name':name,'application':goal}
        items = {}
        for index in range(6):
            rid = f'lab{index}'
            items[rid] = dict(id=rid,title=f'PyTorch 전이학습 실험 {index}',provider='교육원',
                             type='course',usable=True,skills=[name],cost=0,hours=2,difficulty='ADVANCED',
                             curriculum={'items':[{'title':f'PyTorch 분류 헤드 {index}를 학습하고 정확도·학습률을 측정 비교 검증하는 실습'}]})
        items['concept'] = {**items['lab0'],'id':'concept','title':'언어 모델 기초',
                            'curriculum':{'items':[{'title':'PyTorch 전이학습, 미세조정 개념'}]}}
        pools,_ = rag.retrieve({'goal':goal},{'skills':[skill]},items,{'id':'A3','learningSkills':[skill]},
                               embed=lambda texts:[[1.]*rag.DIMENSIONS for _ in texts],
                               search=lambda kind,ids,*args:[dict(resource_id=rid,similarity=.99 if rid=='concept' else .5,current_cost=0) for rid in ids])
        self.assertEqual({row['id'] for row in pools[0]['courses']},{f'lab{i}' for i in range(6)})

    def test_crash_keeps_delivered_valid_model_choices_when_no_old_suitable_bundle_exists(self):
        for name, goal, lesson in (
            ('SQL', 'SQL 로그 집계 프로그램을 구현한다', 'SQL GROUP BY 집계 원리'),
            ('머신러닝 모델링 & 학습 알고리즘', '머신러닝 이상 탐지를 구현한다', '머신러닝 분류 모델과 평가 지표의 원리'),
        ):
            with self.subTest(skill=name):
                skill = {'name':name,'application':goal}
                selection = {'skills':[skill]}
                project = {'goal':goal}
                option = {'id':'A2','learningSkills':[skill]}
                common = evidence.course_selection(project,selection,option)
                base = dict(type='course',usable=True,skills=[name],cost=0,difficulty='INTERMEDIATE',
                            timeStatus='confirmed',estimated=[],provider='검증 교육원')
                items = {rid:{**base,'id':rid,'title':rid,'hours':hours,
                              'curriculum':{'items':[{'title':lesson}]}}
                         for rid,hours in (('concept-short',1),('concept-long',2))}
                items['not-chosen'] = {**base,'id':'not-chosen','title':'not-chosen','hours':.5,
                                      'curriculum':{'items':[{'title':name+' 구현 실습'}]}}
                for rid in ('concept-short','concept-long'):
                    info = evidence.facts(items[rid],project,common)
                    self.assertTrue(evidence.course_applicable(info,common['skills'][0]))
                    self.assertFalse(info['suitability'][name]['suitable'])
                def generate(system,payload):
                    cards = {row['title']:row for row in payload['skills'][0]['courses']}
                    self.assertTrue(all(name in cards[rid]['eligibleSkills'] for rid in items))
                    return {'skills':[{'name':name,'courses':[{'key':cards[rid]['choiceKey']}
                                         for rid in ('concept-long','concept-short')],'books':[]}]}
                before = deepcopy(items)
                result = recommend_resources(project,selection,items,generate,course=option,
                    retrieved_pools=[{'name':name,'courses':list(items.values()),'books':[]}])['skills'][0]
                self.assertEqual([row['id'] for row in result['courses']],['concept-short','concept-long'])
                self.assertEqual(result['selectedCourse'],'concept-short')
                self.assertNotIn('not-chosen',[row['id'] for row in result['courses']])
                self.assertEqual(items,before)

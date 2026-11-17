import copy
import unittest
from unittest.mock import Mock
from app.agents.resource_recommendations import RecommendationError, candidate_pools, recommend_resources, validate_choices

class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.project = {'goal': '수질 데이터 분석', 'projectSummary': None, 'desiredCompetencies': '전처리'}
        self.selection = {'skills': [{'name': '분석', 'application': '분석 구현'}]}
        self.items = {f'{kind}{i}': {'id': f'{kind}{i}', 'title': f'자료 {i}', 'type': kind,
                      'usable': True, 'skills': ['분석'], 'cost': i, 'content': '목차 근거'}
                      for kind in ('course', 'book') for i in range(4)}
    def raw(self):
        return {'skills': [dict(name='분석', **{kind: [{'id': f'{prefix}{i}', 'why': '프로젝트 관련 자료', 'knowledge': '데이터 처리 지식'} for i in range(3)]
                            for kind, prefix in [('courses', 'course'), ('books', 'book')]})]}
    def recommend(self, raw=None, items=None):
        return recommend_resources(self.project, self.selection, self.items if items is None else items, lambda *_: self.raw() if raw is None else raw)
    def test_only_current_course_policy_reaches_model_without_input_or_source_changes(self):
        from app.agents.resource_instructions import instructions
        for course in ('A1','A2','A3'):
            before=copy.deepcopy((self.project,self.selection,self.items))
            model=Mock(return_value={'skills':[{'name':'분석','courses':[],'books':[]}]})
            recommend_resources(self.project,self.selection,self.items,model,course={'id':course})
            system,payload=model.call_args.args
            self.assertEqual(system,instructions({'id':course}))
            expected={'project','skills','bookCatalog','learnerKnowledge','hrContext','course'}
            if course=='A2':expected.add('crashStudyPlan')
            self.assertEqual(set(payload),expected)
            self.assertEqual(payload['course']['id'],course)
            for other,label in (('A1','Free'),('A2','Crash'),('A3','Challenge')):
                self.assertEqual(('[현재 코스 · '+label+']') in system,course==other)
            self.assertEqual((self.project,self.selection,self.items),before)

    def test_instruction_output_and_diagnostic_schemas_are_preserved(self):
        import json
        from app.agents.resource_instructions import COMMON
        schema=json.loads(COMMON.split('JSON: ',1)[1])
        self.assertEqual(set(schema),{'skills'})
        self.assertEqual(set(schema['skills'][0]),{'name','courses','books'})
        self.assertEqual(set(schema['skills'][0]['courses'][0]),{'key'})
        diagnostic=json.loads(COMMON.split('courseDiagnostic 형식: ',1)[1].splitlines()[0])
        self.assertEqual(set(diagnostic),{'reason','detail'})
        self.assertEqual(set(diagnostic['reason'].split('|')),{'no_candidates','insufficient_evidence','stack_mismatch','scope_gap','longer_for_coverage'})
        book_diagnostic = json.loads(COMMON.split('bookDiagnostic 형식: ', 1)[1].splitlines()[0])
        self.assertEqual(set(book_diagnostic['reason'].split('|')), {'no_candidates', 'insufficient_evidence', 'scope_gap'})

    def test_only_exact_goal_duplicate_is_removed_from_model_copy(self):
        from unittest.mock import patch
        for desired in ('수질 데이터 분석', '  수질 데이터 분석  ', '수질 데이터 분석 심화', '수질  데이터 분석', None):
            with self.subTest(desired=desired):
                project=dict(self.project,desiredCompetencies=desired)
                before=copy.deepcopy((project,self.selection,self.items))
                model=Mock(return_value={'skills':[{'name':'분석','courses':[],'books':[]}]})
                with patch('app.agents.resource_recommendations.candidate_pools', wraps=candidate_pools) as search:
                    result=recommend_resources(project,self.selection,self.items,model)
                system,payload=model.call_args.args
                self.assertEqual(search.call_args.args[0]['desiredCompetencies'],desired)
                self.assertEqual(payload['project']['goal'],project['goal'])
                if isinstance(desired,str) and desired.strip()==project['goal'].strip():
                    self.assertNotIn('desiredCompetencies',payload['project'])
                else:
                    self.assertIn('desiredCompetencies',payload['project'])
                    self.assertEqual(payload['project']['desiredCompetencies'],desired)
                self.assertIn('미제공 시 goal 기준',system)
                self.assertEqual((project,self.selection,self.items),before)
                self.assertEqual(result['skills'][0]['name'],'분석')
                self.assertEqual(result['skills'][0]['courses'],[])
                self.assertEqual(result['skills'][0]['books'],[])

    def test_candidate_snapshot_matches_initial_model_input(self):
        for i in range(4, 8):
            self.items[f'course{i}'] = dict(self.items['course0'], id=f'course{i}', title=f'자료 {i}', cost=i)
        model = Mock(return_value=self.raw())
        row = recommend_resources(self.project, self.selection, self.items, model)['skills'][0]
        prompt_courses = model.call_args_list[0].args[1]['skills'][0]['courses']
        candidates = row['modelCourseCandidates']
        self.assertEqual(len(candidates), 6)
        self.assertEqual([c['title'] for c in candidates], [c['title'] for c in prompt_courses])
        self.assertEqual([c['id'] for c in candidates if c['recommended']], [c['id'] for c in row['courses']])

    def test_top_recommendation_and_one_book_default(self):
        row=self.recommend()['skills'][0]
        self.assertEqual(row['selectedCourse'],'course0')
        self.assertEqual(row['selectedBooks'],['book0'])
        self.assertEqual([r['aiRecommended'] for r in row['courses']],[True,False,False])

    def test_zero_budget_keeps_reference_books_optional_and_selects_only_free_defaults(self):
        books = [dict(self.items['book0'], id=rid, cost=cost) for rid, cost in
                 [('paid', 22000), ('unknown', None), ('free', 0)]]
        for budget, expected in [(0, ['free']), ('', ['paid'])]:
            for candidates in (books, books[:2]):
                project = dict(self.project, details={'budget': budget})
                raw = {'skills': [{'name': '분석', 'courses': [], 'books': [{'id': b['id']} for b in candidates]}]}
                row, = recommend_resources(project, self.selection, {b['id']: b for b in candidates},
                                           lambda *_: raw, course={'id': 'A3'})['skills']
                self.assertEqual([b['id'] for b in row['books']], [b['id'] for b in candidates])
                self.assertEqual(row['selectedBooks'], [] if budget == 0 and len(candidates) == 2 else expected)
    def test_unrelated_and_unusable_resources_filtered_before_limit(self):
        items={f'bad{i}':dict(self.items['course0'],id=f'bad{i}',title='AAA',skills=['다른스킬']) for i in range(30)}
        items['free']=dict(self.items['course0'],id='free',title='ZZZ')
        items['deleted']=dict(self.items['book0'],id='deleted',usable=False)
        pool=candidate_pools(self.project,self.selection,items,limit=1)[0]
        self.assertEqual([r['id'] for r in pool['courses']],['free'])
        self.assertEqual(pool['books'],[])
    def test_missing_resources_remain_empty_without_model_call(self):
        model=Mock()
        result=recommend_resources(self.project,self.selection,{},model)
        self.assertEqual(result['skills'][0]['selectedBooks'],[])
        self.assertIsNone(result['skills'][0]['selectedCourse'])
        model.assert_not_called()
        self.assertEqual(result['skills'][0]['modelBookCounts'], {'candidates': 0, 'recommended': 0})
    def test_fewer_than_three_resources_not_padded(self):
        raw=self.raw();raw['skills'][0]['books']=raw['skills'][0]['books'][:1]
        result=self.recommend(raw)
        self.assertEqual(len(result['skills'][0]['books']),1)

    def test_book_diagnostic_keeps_empty_choices_and_distinguishes_missing_candidates(self):
        scope = {'reason': 'scope_gap', 'detail': '시각화 소개는 있지만 전처리 근거가 부족합니다.'}
        raw = {'skills': [{'name': '분석', 'courses': [], 'books': [], 'bookDiagnostic': scope}]}
        output = self.recommend(raw)['skills'][0]
        self.assertEqual(output['bookDiagnostic'], scope)
        self.assertEqual((output['books'], output['selectedBooks']), ([], []))
        self.assertEqual(output['modelBookCounts'], {'candidates': 4, 'recommended': 0})
        self.assertEqual(output['courseDiagnostic']['reason'], 'insufficient_evidence')
        del raw['skills'][0]['bookDiagnostic']
        self.assertEqual(self.recommend(raw)['skills'][0]['bookDiagnostic']['reason'], 'insufficient_evidence')
        no_books = {key: value for key, value in self.items.items() if value['type'] == 'course'}
        self.assertEqual(self.recommend(raw, no_books)['skills'][0]['bookDiagnostic']['reason'], 'no_candidates')

    def test_invalid_book_diagnostics_fall_back_to_server_guidance(self):
        # 도서 후보가 있는데 no_candidates라고 하거나 형식이 틀려도 추천 전체를 실패시키지 않는다.
        for reason, detail in (('no_candidates', '사유'), ('stack_mismatch', '사유'), ('scope_gap', '  ')):
            raw = {'skills': [{'name': '분석', 'courses': [], 'books': [],
                              'bookDiagnostic': {'reason': reason, 'detail': detail}}]}
            with self.subTest(reason=reason, detail=detail), \
                    self.assertLogs('app.agents.resource_recommendations', 'WARNING'):
                self.assertEqual(self.recommend(raw)['skills'][0]['bookDiagnostic']['reason'], 'insufficient_evidence')
        raw = {'skills': [{'name': '분석', 'courses': [], 'books': [],
                          'bookDiagnostic': {'reason': 'scope_gap', 'detail': 'x' * 241}}]}
        self.assertEqual(self.recommend(raw)['skills'][0]['bookDiagnostic'],
                         {'reason': 'scope_gap', 'detail': 'x' * 239 + '…'})

    def test_display_diagnostic_uses_supplied_titles_even_for_unselected_candidates(self):
        detail = 'S1-C1의 범위가 좁고 S1-C2에는 실습이 있습니다. S1-C10의 근거는 확인이 필요합니다.'
        book_detail = 'B1은 원리를 다룹니다.'
        raw = {'skills': [{'name': '분석', 'courses': [{'key': 'S1-C2'}], 'books': [],
                          'courseDiagnostic': {'reason': 'scope_gap', 'detail': detail},
                          'bookDiagnostic': {'reason': 'scope_gap', 'detail': book_detail}}]}
        result = self.recommend(raw)['skills'][0]
        self.assertEqual(result['selectedCourse'], 'course1')
        self.assertEqual(result['selectedBooks'], [])
        self.assertEqual(result['courseDiagnostic'], {
            'reason': 'scope_gap', 'detail': detail,
            'displayDetail': '「자료 0」의 범위가 좁고 「자료 1」에는 실습이 있습니다. 비교 후보의 근거는 확인이 필요합니다.'})
        self.assertEqual(result['bookDiagnostic']['displayDetail'], '「자료 0」은 원리를 다룹니다.')
        self.assertNotIn('displayDetail', raw['skills'][0]['courseDiagnostic'])

    def test_display_diagnostic_shortens_only_titles_to_fit_240_characters(self):
        items = copy.deepcopy(self.items)
        items['course0']['title'] = 'A 과정 ' * 20
        items['course1']['title'] = 'B 강좌 ' * 20
        ending = ' 두 강좌 모두 입력 검증을 다루지만 복구 절차는 확인되지 않습니다.'
        detail = 'S1-C1 및 S1-C2' + ('가' * 175) + ending
        result = self.recommend({'skills': [{'name': '분석', 'courses': [], 'books': [],
            'courseDiagnostic': {'reason': 'scope_gap', 'detail': detail}}]}, items)['skills'][0]['courseDiagnostic']
        self.assertEqual(result['detail'], detail)
        display = result['displayDetail']
        self.assertLessEqual(len(display), 240)
        self.assertTrue(display.startswith('「A 과정 '))
        self.assertIn(' 및 「B 강좌 ', display)
        self.assertEqual(display.count('…'), 2)
        self.assertTrue(display.endswith(('가' * 175) + ending))

    def test_display_diagnostic_falls_back_when_neutral_book_labels_exceed_budget(self):
        detail = 'B1 ' + '가' * 237
        result = self.recommend({'skills': [{'name': '분석', 'courses': [], 'books': [],
            'bookDiagnostic': {'reason': 'scope_gap', 'detail': detail}}]})['skills'][0]
        self.assertEqual(result['bookDiagnostic'], {'reason': 'scope_gap', 'detail': detail})

    def test_wrong_type_unknown_duplicate_and_more_than_three_rejected(self):
        bad=[]
        raw=self.raw();raw['skills'][0]['courses'][0]['id']='book0';bad.append(raw)
        raw=self.raw();raw['skills'][0]['courses'][0]['id']='invented';bad.append(raw)
        raw=self.raw();raw['skills'][0]['courses'][1]=copy.deepcopy(raw['skills'][0]['courses'][0]);bad.append(raw)
        raw=self.raw();raw['skills'][0]['courses'].append({'id':'course3','why':'이유','knowledge':'지식'});bad.append(raw)
        for raw in bad:
            with self.subTest(raw=raw),self.assertRaises(RecommendationError):self.recommend(raw)
    def test_course_one_and_book_max_three_validation(self):
        result=self.recommend()
        validate_choices(result,{'분석':{'course':'course0','books':['book0','book1','book2']}})
        for course,books in [(['course0','course1'],[]),('course0',['book0']*2),('course0',['book0','book1','book2','book3']),('course0',['unknown'])]:
            with self.subTest(course=course,books=books),self.assertRaises(RecommendationError):
                validate_choices(result,{'분석':{'course':course,'books':books}})
    def test_raw_document_and_personal_data_not_added_to_model_payload(self):
        project=dict(self.project,rawText='원문',profile={'name':'개인정보'})
        model=Mock(return_value=self.raw())
        recommend_resources(project,self.selection,self.items,model)
        payload=model.call_args.args[1]
        self.assertNotIn('rawText',payload['project'])
        self.assertNotIn('profile',payload['project'])

    def test_null_curriculum_items_still_allows_recommendation(self):
        items=copy.deepcopy(self.items)
        for row in items.values(): row['curriculum']={'items':None}
        model=Mock(return_value=self.raw())
        result=recommend_resources(self.project,self.selection,items,model)
        self.assertEqual(len(result['skills'][0]['courses']),3)
        self.assertEqual(model.call_args.args[1]['skills'][0]['courses'][0]['outline'],[])

    def test_short_reference_keys_map_only_to_their_skill_and_kind(self):
        def model(_, payload):
            rows=payload['skills'][0]
            return {'skills':[dict(name='분석',**{key:[{'key':row['choiceKey'],'why':'이유','knowledge':'지식'} for row in rows[key][:3]] for key in ('courses','books')})]}
        result=recommend_resources(self.project,self.selection,self.items,model)
        self.assertEqual(result['skills'][0]['courses'][0]['id'],'course0')
        raw=self.raw();raw['skills'][0]['courses'][0]={'key':'S1-B1','why':'이유','knowledge':'지식'}
        with self.assertRaises(RecommendationError):self.recommend(raw)

    def test_wrapped_answer_envelope_and_positional_name_recovery(self):
        # 1) {"answer": {"skills": [...]}, "type": "agent"}
        wrapped_dict = {'answer': self.raw(), 'type': 'agent'}
        res1 = self.recommend(wrapped_dict)
        self.assertEqual(res1['skills'][0]['name'], '분석')

        # 2) {"answer": "{\"skills\": [...]}"}
        import json
        wrapped_str = {'answer': json.dumps(self.raw())}
        res2 = self.recommend(wrapped_str)
        self.assertEqual(res2['skills'][0]['name'], '분석')

        # 3) 파인튜닝 모델이 행의 name 을 누락한 경우 pools 에서 복구
        no_name = copy.deepcopy(self.raw())
        no_name['skills'][0].pop('name', None)
        res3 = self.recommend(no_name)
        self.assertEqual(res3['skills'][0]['name'], '분석')

    def test_multi_row_positional_name_recovery_when_all_names_omitted(self):
        # 3개 스킬 선정 환경에서 모델이 모든 행의 name 을 누락한 경우 위치 복구 검증
        project = {'goal': '수질 데이터 분석', 'projectSummary': None, 'desiredCompetencies': '전처리'}
        selection = {'skills': [
            {'name': '분석', 'application': '분석 구현'},
            {'name': '시각화', 'application': '차트 구현'},
            {'name': '머신러닝', 'application': '모델링'},
        ]}
        items = {
            'course0': {'id': 'course0', 'title': '강좌 0', 'type': 'course', 'usable': True, 'skills': ['분석', '시각화', '머신러닝'], 'cost': 0, 'content': '분석 내용'},
            'book0': {'id': 'book0', 'title': '도서 0', 'type': 'book', 'usable': True, 'skills': ['분석', '시각화', '머신러닝'], 'cost': 0, 'content': '도서 내용'},
        }
        # 모델 출력이 3개 행 모두 name 을 생략한 경우 (모든 행이 올바른 순서의 스킬명으로 복구되어야 함)
        raw_multi = {'skills': [
            {'courses': [{'id': 'course0', 'why': '분석 자료', 'knowledge': '분석 지식'}], 'books': []},
            {'courses': [{'id': 'course0', 'why': '시각화 자료', 'knowledge': '시각화 지식'}], 'books': []},
            {'courses': [{'id': 'course0', 'why': '머신러닝 자료', 'knowledge': '머신러닝 지식'}], 'books': []},
        ]}
        res = recommend_resources(project, selection, items, lambda *_: raw_multi)
        self.assertEqual([s['name'] for s in res['skills']], ['분석', '시각화', '머신러닝'])

        # 부분 누락(1개만 name 있고 나머지는 누락)인 경우 모호하므로 거부되는지 검증
        partial_missing = {'skills': [
            {'name': '분석', 'courses': [{'id': 'course0', 'why': '분석 자료', 'knowledge': '분석 지식'}], 'books': []},
            {'courses': [{'id': 'course0', 'why': '시각화 자료', 'knowledge': '시각화 지식'}], 'books': []},
            {'courses': [{'id': 'course0', 'why': '머신러닝 자료', 'knowledge': '머신러닝 지식'}], 'books': []},
        ]}
        with self.assertRaises(RecommendationError):
            recommend_resources(project, selection, items, lambda *_: partial_missing)

    def test_issue_310_crash_extra_prompt_skill_repairs_once_and_preserves_empty_diagnostics(self):
        from app.agents import resource_instructions

        self.assertNotIn('프로젝트 목표·기획서 요약(없을 수 있음)', resource_instructions.COMMON)
        self.assertNotIn('프로젝트 목표·기획서 요약(없을 수 있음)', resource_instructions.instructions({'id': 'A2'}))

        s1 = 'RAG & 생성형 AI 에이전트'
        s2 = '자연어 처리(NLP) & LLM 기초'
        s3 = 'ETL & 데이터 파이프라인'
        project = {
            'goal': 'SECRET_GOAL_TEXT_310 RAG 질의응답과 ETL 파이프라인 구축',
            'projectSummary': None,
            'desiredCompetencies': 'RAG 검색·LLM 프롬프트·ETL 적재',
            'selectedSkills': [s1, s2, s3],
        }
        selection = {'skills': [
            {'name': s1, 'application': 'RAG 검색 증강 에이전트 구현'},
            {'name': s2, 'application': 'NLP 토큰화 임베딩 프롬프트 엔지니어링 실습'},
            {'name': s3, 'application': 'ETL 문서 수집 정제 임베딩 색인 파이프라인 구현'},
        ]}
        items = {
            'c1': {'id': 'c1', 'title': 'RAG 에이전트 실습', 'type': 'course', 'usable': True, 'skills': [s1], 'cost': 0,
                   'hours': 4, 'timeStatus': 'confirmed', 'difficulty': 'INTERMEDIATE',
                   'content': 'RAG 검색 증강 에이전트 구현 실습',
                   'curriculum': {'items': [{'title': 'RAG 검색 증강 에이전트 구현'}]}},
            'c2': {'id': 'c2', 'title': 'NLP LLM 기초', 'type': 'course', 'usable': True, 'skills': [s2], 'cost': 0,
                   'hours': 6, 'timeStatus': 'confirmed', 'difficulty': 'INTERMEDIATE',
                   'content': 'NLP 토큰화 임베딩 프롬프트 엔지니어링 실습',
                   'curriculum': {'items': [{'title': 'NLP 토큰화 임베딩 프롬프트 엔지니어링 실습'}]}},
            'c3': {'id': 'c3', 'title': 'ETL 파이프라인', 'type': 'course', 'usable': True, 'skills': [s3], 'cost': 0,
                   'hours': 5, 'timeStatus': 'confirmed', 'difficulty': 'INTERMEDIATE',
                   'content': 'ETL 문서 수집 정제 임베딩 색인 파이프라인 구현',
                   'curriculum': {'items': [{'title': 'ETL 문서 수집 정제 임베딩 색인 파이프라인'}]}},
            'b1': {'id': 'b1', 'title': '도서 1', 'type': 'book', 'usable': True, 'skills': [s1], 'cost': 0, 'content': 'RAG 안내'},
            'b2': {'id': 'b2', 'title': '도서 2', 'type': 'book', 'usable': True, 'skills': [s1], 'cost': 0, 'content': '에이전트 안내'},
            'b3': {'id': 'b3', 'title': '도서 3', 'type': 'book', 'usable': True, 'skills': [s2], 'cost': 0, 'content': 'NLP LLM 안내'},
        }
        etl_detail = '제공된 ETL 후보들의 목차·설명만으로는 문서 수집·정제·임베딩→색인 파이프라인 실습이 확인되지 않아 근거 부족으로 추천하지 않았습니다.'
        repaired_skills = [
            {'name': s1, 'courses': [{'key': 'S1-C1'}], 'books': []},
            {'name': s2, 'courses': [], 'books': [{'key': 'B3'}],
             'courseDiagnostic': {'reason': 'longer_for_coverage', 'detail': '기본안 S2-C1은 구체적 실습 단원이 부족해 제외했습니다.'}},
            {'name': s3, 'courses': [], 'books': [],
             'courseDiagnostic': {'reason': 'insufficient_evidence', 'detail': etl_detail}},
        ]
        bad_with_extra = {'skills': [
            *copy.deepcopy(repaired_skills),
            {'name': '프로젝트 목표·기획서 요약(없을 수 있음)', 'courses': [], 'books': []},
        ]}
        model = Mock(side_effect=[bad_with_extra, {'skills': repaired_skills}])

        with self.assertLogs('app.agents.resource_recommendations', 'WARNING') as logs:
            result = recommend_resources(project, selection, items, model, course={'id': 'A2', 'name': 'Crash Course'})

        self.assertEqual(model.call_count, 2)
        second_system = model.call_args_list[1].args[0]
        self.assertIn('[출력 스킬 교정]', second_system)
        for name in (s1, s2, s3):
            self.assertIn(name, second_system)
        self.assertTrue(any('expected_count=3 actual_count=4' in m and 'unexpected_count=1' in m for m in logs.output))
        self.assertTrue(all('SECRET_GOAL_TEXT_310' not in m and '프로젝트 목표·기획서 요약(없을 수 있음)' not in m for m in logs.output))

        self.assertEqual([row['name'] for row in result['skills']], [s1, s2, s3])
        self.assertEqual(result['skills'][0]['selectedCourse'], 'c1')
        self.assertEqual(result['skills'][1]['selectedBooks'], ['b3'])
        self.assertIn('courseDiagnostic', result['skills'][1])
        self.assertEqual(result['skills'][2]['courses'], [])
        self.assertEqual(result['skills'][2]['books'], [])
        self.assertEqual(result['skills'][2]['courseDiagnostic'], {'reason': 'insufficient_evidence', 'detail': etl_detail})

    def test_skill_contract_violations_never_silently_truncate_or_pad_and_stop_after_one_repair(self):
        project = {'goal': 'SECRET_GOAL_TEXT 분석과 시각화 모델링', 'projectSummary': None, 'desiredCompetencies': None}
        selection = {'skills': [
            {'name': '분석', 'application': '데이터 분석'},
            {'name': '시각화', 'application': '차트 시각화'},
            {'name': '머신러닝', 'application': '예측 모델링'},
        ]}
        items = {
            'c0': {'id': 'c0', 'title': '통합 강좌', 'type': 'course', 'usable': True, 'skills': ['분석', '시각화', '머신러닝'], 'cost': 0,
                   'hours': 4, 'timeStatus': 'confirmed', 'difficulty': 'INTERMEDIATE',
                   'content': '데이터 분석 차트 시각화 예측 모델링 실습',
                   'curriculum': {'items': [{'title': '데이터 분석 차트 시각화 예측 모델링 실습'}]}},
        }
        valid_a = {'name': '분석', 'courses': [{'key': 'S1-C1'}], 'books': []}
        valid_b = {'name': '시각화', 'courses': [], 'books': []}
        valid_c = {'name': '머신러닝', 'courses': [], 'books': []}
        cases = [
            ('extra_fake', {'skills': [valid_a, valid_b, valid_c, {'name': '프로젝트 목표·기획서 요약(없을 수 있음)', 'courses': [], 'books': []}]}, '스킬별 추천 결과 수가 일치하지 않습니다.'),
            ('missing_one', {'skills': [valid_a, valid_b]}, '스킬별 추천 결과 수가 일치하지 않습니다.'),
            ('duplicate_skill', {'skills': [valid_a, copy.deepcopy(valid_a), valid_c]}, '추천 스킬이 입력과 다르거나 중복되었습니다.'),
            ('mismatched_name', {'skills': [valid_a, valid_b, {'name': '없는스킬', 'courses': [], 'books': []}]}, '추천 스킬이 입력과 다르거나 중복되었습니다.'),
            ('missing_skills_key', {}, '스킬별 추천 결과 수가 일치하지 않습니다.'),
            ('non_list_skills', {'skills': 'bad'}, '스킬별 추천 결과 수가 일치하지 않습니다.'),
            ('non_dict_elements', {'skills': ['분석', '시각화', '머신러닝']}, '추천 스킬이 입력과 다르거나 중복되었습니다.'),
        ]
        for label, bad_response, expected_message in cases:
            with self.subTest(case=label):
                model = Mock(return_value=bad_response)
                with self.assertLogs('app.agents.resource_recommendations', 'WARNING') as logs:
                    with self.assertRaises(RecommendationError) as caught:
                        recommend_resources(project, selection, items, model, course={'id': 'A2'})
                self.assertEqual(str(caught.exception), expected_message)
                self.assertEqual(model.call_count, 2)
                self.assertEqual(len(logs.output), 2)
                self.assertTrue(all('SECRET_GOAL_TEXT' not in m for m in logs.output))


class PeriodCandidateTests(unittest.TestCase):
    def test_all_courses_keep_long_and_short_candidates_without_mutating_hours(self):
        items={key:{'id':key,'title':key,'type':'course','usable':True,'skills':['SQL'],'hours':hours,'cost':0} for key,hours in [('long',72),('short',16)]}
        for course in ('A1','A2','A3'):
            pools=candidate_pools({'details':{'weeks':8,'hours':4},'selectedCourse':{'id':course}}, {'skills':[{'name':'SQL'}]},items)
            self.assertEqual({row['id'] for row in pools[0]['courses']},{'long','short'})
        self.assertEqual(items['long']['hours'],72)

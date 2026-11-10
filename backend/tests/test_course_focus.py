import unittest
from unittest.mock import Mock

from app import course_levels

from app.agents.resource_recommendations import recommend_resources
from app.services import resource_evidence, resource_rag as rag


class InputCaptured(Exception):
    pass


class CourseFocusTests(unittest.TestCase):
    name = '컴퓨터 비전(CV) 모델링'
    target = '차선 영상을 세그멘테이션하고 픽셀 마스크를 생성한다'

    def assert_delivered(self, name, goal, examples, expected):
        spec = {'name': name, 'application': goal}
        project = {'goal': goal}
        selection = {'skills': [spec], 'commonApplications': {name: goal}}
        for track, level in [('A1', 'BEGINNER'), ('A2', 'INTERMEDIATE'), ('A3', 'ADVANCED')]:
            with self.subTest(track=track, goal=goal):
                items = {key: dict(id=key, title=key, provider='교육원', type='course', usable=True,
                                   skills=[name], difficulty=level, hours=1, cost=0, content=intro,
                                   curriculum={'items': [{'title': unit} for unit in units]})
                         for key, (intro, units) in examples.items()}
                course = {'id': track, 'learningSkills': [spec]}
                pools, _ = rag.retrieve(project, selection, items, course,
                    embed=lambda texts: [[1.] * rag.DIMENSIONS for _ in texts],
                    search=lambda kind, ids, *args: [dict(resource_id=i, similarity=.8, current_cost=0) for i in ids])
                self.assertEqual({row['id'] for row in pools[0]['courses']}, set(expected))
                model = Mock(return_value={'skills': [{'name': name, 'courses': [], 'books': []}]})
                recommend_resources(project, selection, items, model, course=course, retrieved_pools=pools)
                cards = {c['title']: c for c in model.call_args.args[1]['skills'][0]['courses']}
                self.assertEqual(set(cards), set(expected))
                for key, proof in expected.items():
                    self.assertIn(proof, ' '.join([cards[key]['content'], *(u['title'] for u in cards[key]['outline'])]))

    def test_nosql_does_not_inherit_sql_engine_or_join_requirements(self):
        unit = 'MongoDB 문서 조회 실습'
        examples = {'mongo': ('', [unit]), 'comparison': ('', [unit, 'MySQL 테이블과 비교']),
                    'wrong-tag': ('', ['MySQL에서 테이블 두 개를 조인하는 실습'])}
        self.assert_delivered('NoSQL & 분산 DB', 'PostgreSQL 조인과 MongoDB 문서 조회를 구현한다',
                              examples, {'mongo': unit, 'comparison': unit})

    def test_nosql_storage_lessons_need_database_evidence(self):
        examples = {
            'cosmos': ('', ['Azure Cosmos DB 컨테이너 쿼리 실습']),
            'redis': ('', ['Redis 키-값 저장소 쿼리 실습']),
            'Azure Cosmos DB 입문': ('', ['컨테이너의 항목을 조회하는 실습']),
            'data-model': ('문서형 데이터베이스에서 데이터를 조회하는 실습', []),
            'direct-query': ('', ['Azure Cosmos DB에서 쿼리를 작성하는 실습']),
            'commands': ('', ['Redis GET/SET으로 데이터를 조회하는 실습']),
            'relational': ('', ['MySQL 테이블 조인 쿼리 실습']),
            'css': ('', ['CSS 컨테이너 쿼리 실습']),
            'Azure Cosmos DB for PostgreSQL': ('', ['PostgreSQL 테이블 조인 쿼리 실습']),
            'Redis 기초': ('', ['채팅 메시지 Pub/Sub 구현 실습']),
            'files': ('', ['팀 문서 저장소 파일 검색 실습']),
            'prerequisite': ('선수지식: Redis 키-값 저장소 쿼리 실습', ['웹 페이지 구현']),
        }
        self.assert_delivered('NoSQL & 분산 DB', '문서 저장소 조회를 구현한다', examples, {
            'cosmos': examples['cosmos'][1][0], 'redis': examples['redis'][1][0],
            'Azure Cosmos DB 입문': examples['Azure Cosmos DB 입문'][1][0], 'data-model': examples['data-model'][0],
            'direct-query': examples['direct-query'][1][0], 'commands': examples['commands'][1][0],
        })

    def test_description_keeps_the_same_airflow_evidence_with_another_sentence(self):
        proof = 'Airflow DAG의 태스크 의존성과 스케줄을 다룹니다.'
        self.assert_delivered('ETL & 데이터 파이프라인', 'Airflow DAG를 구현한다', {
            'one': (proof, []), 'two': ('실무 데이터를 다룹니다. ' + proof, []),
            'separate': ('Airflow를 다룹니다. 별도의 웹 서버 스케줄을 소개합니다.', []),
            'prereq': ('선수지식: ' + proof, []), 'inline-prereq': ('과정 안내입니다. 선수지식: ' + proof, []),
            'question': ('Q. ' + proof, []),
            'continued-prereq': ('자료를 배포합니다. 선수지식:\n' + proof, []),
            'restart': ('선수지식: Python 문법. 학습 목표: ' + proof, []),
        }, {'one': proof, 'two': proof, 'restart': proof})

    def test_joint_sql_and_nosql_goal_keeps_each_skills_courses(self):
        sql = 'SQL 기본 문법 & 조인'
        nosql = 'NoSQL & 분산 DB'
        goals = {sql: 'PostgreSQL 조인 쿼리를 구현한다', nosql: 'MongoDB 문서 조회를 구현한다'}
        skills = [dict(name=name, application=goal) for name, goal in goals.items()]
        project = {'goal': 'PostgreSQL 조인 쿼리를 구현하고 MongoDB 문서 조회를 구현한다'}
        for track, level in [('A1', 'BEGINNER'), ('A2', 'INTERMEDIATE'), ('A3', 'ADVANCED')]:
            items = {key: dict(id=key, title=key, type='course', skills=[name], usable=True, difficulty=level,
                               cost=0, hours=1, curriculum={'items': [{'title': unit} for unit in units]})
                     for key, name, units in [
                         ('pg', sql, ['PostgreSQL 테이블 조인 결과 검증 실습']),
                         ('other-engine', sql, ['MySQL 테이블 조인 결과 검증 실습']),
                         ('mongo', nosql, ['MongoDB 문서 조회 실습', 'MySQL 테이블과 비교'])]}
            for applications in [goals, {}]:
                with self.subTest(track=track, has_saved_scope=bool(applications)):
                    pools, _ = rag.retrieve(project, {'skills': skills, 'commonApplications': applications}, items,
                        {'id': track, 'learningSkills': skills}, embed=lambda texts: [[1.] * rag.DIMENSIONS for _ in texts],
                        search=lambda kind, ids, *args: [dict(resource_id=i, current_cost=0, similarity=.8) for i in ids])
                    self.assertEqual({p['name']: [r['id'] for r in p['courses']] for p in pools},
                                     {sql: ['pg'], nosql: ['mongo']})

    def test_korean_particles_and_line_wrapping_preserve_nlp_evidence(self):
        for goal in ('LLM 응답 품질 평가', 'LLM 응답\n품질 평가'):
            plain = 'BLEU, ROUGE 지표 실습'
            attached = 'BLEU와 ROUGE로 번역 품질 측정'
            self.assert_delivered('자연어 처리(NLP) & LLM 기초', goal, {
                'plain': ('', [plain]), 'attached': ('', [attached]),
                'different': ('', ['ROUGER 도구로 길이 측정']), 'qa': ('', ['Q. BLEU로 어떻게 평가하나요?']),
                'LLM 운영': ('', ['STORAGE 디스크 성능 평가 실습']),
                'rag-eval': ('', ['RAG를 평가하는 실습']),
            }, {'plain': plain, 'attached': attached, 'rag-eval': 'RAG를 평가하는 실습'})

    def test_nlp_evaluation_handoff_uses_skill_intent_and_not_inference_token_budget(self):
        name = '자연어 처리(NLP) & LLM 기초'
        application = 'LLM 답변의 근거성과 정답 일치를 평가한다'
        project = {'goal': 'LLM 운영 지표를 설계한다', 'projectSummary': '입력 최대 6,144토큰, 출력 최대 512토큰'}
        spec = {'name': name, 'application': '코스에서 생성한 개별 예시'}
        selection = {'skills': [spec], 'commonApplications': {name: application}}
        for track, level in [('A1','BEGINNER'), ('A2','INTERMEDIATE'), ('A3','ADVANCED')]:
            units = {'eval':['토큰화 소개', 'RAGAS faithfulness 지표로 답변의 근거성을 평가하는 실습'],
                     'token':['토크나이저로 문장을 서브워드 토큰으로 분절하는 실습'],
                     'qa':['Q. RAG 평가 방법은 무엇인가요?']}
            items = {k: dict(id=k, type='course', usable=True, title=k, provider='기관', skills=[name], cost=0,
                             difficulty=level, hours=1, curriculum={'items':[{'title':u} for u in lessons]})
                     for k, lessons in units.items()}
            embed = Mock(return_value=[[1.] * rag.DIMENSIONS])
            def search(kind, ids, vector, limit, free):
                return [dict(resource_id=k, similarity=.8, current_cost=0) for k in ids]
            option = {'id':track, 'learningSkills':[spec]}
            pools,_ = rag.retrieve(project,selection,items,option,embed=embed,search=search)
            self.assertIn(application, embed.call_args.args[0][0])
            self.assertNotIn('코스에서 생성한 개별 예시', embed.call_args.args[0][0])
            model = Mock(return_value={'skills':[{'name':name,'courses':[],'books':[]}]})
            recommend_resources(project,selection,items,model,course=option,retrieved_pools=pools)
            cards = model.call_args.args[1]['skills'][0]['courses']
            self.assertEqual([c['title'] for c in cards], ['eval'])
            self.assertEqual(cards[0]['outline'][0]['title'], units['eval'][1])
        from app.services import course_focus
        self.assertTrue(course_focus.requested(name, '한국어 토큰화와 문장 분절을 실습한다'))

    def test_task_evidence_for_metrics_and_event_pipeline(self):
        cases = [
            ('탐색적 데이터 분석(EDA) & 전처리', '모델 예측 지표를 구간별 비교한다',
             '판다스 그룹별 집계 실습', '기초 통계: 결측치 대체 실습'),
            ('ETL & 데이터 파이프라인', '이벤트 측정값 집계와 원천·적재 결과를 검증한다',
             '원천과 마트의 행 수를 대조하는 실습', 'LLM 채팅 응답 스트리밍 구현'),
        ]
        for name, goal, good, bad in cases:
            project = {'goal':goal}
            spec = {'name':name,'application':goal}
            option = {'id':'A3','learningSkills':[spec]}
            common = resource_evidence.course_selection(project,{'skills':[spec]},option)
            for title, expected in ((good,True),(bad,False)):
                item = dict(id='one',type='course',usable=True,title=name,skills=[name],cost=0,difficulty='ADVANCED',
                            curriculum={'items':[{'title':title}]})
                info=resource_evidence.facts(item,project,common)
                self.assertEqual(resource_evidence.course_applicable(info,common['skills'][0]),expected,(name,title))

    def test_reviewed_level_follows_the_course_across_skill_tags(self):
        levels = ['ADVANCED', 'UPPER_INTERMEDIATE', 'INTERMEDIATE', 'BEGINNER']
        for tag in ('SQL', 'Python'):
            records = [{'difficulty': level, 'skills': [tag]} for level in levels]
            self.assertEqual([course_levels.preference(r, 'A3') for r in records], [0, 1, 2, 3])
            self.assertEqual([course_levels.preference(r, 'A2') for r in records], [1, 1, 0, 0])
            self.assertEqual([course_levels.preference(r, 'A1') for r in records], [0, 0, 0, 0])
        self.assertEqual(course_levels.classify('UPPER_INTERMEDIATE', '', {})[0], 'UPPER_INTERMEDIATE')

    def test_django_rest_component_and_operation_are_practical_evidence(self):
        name = '웹 프레임워크 (FastAPI/Django)'
        goal = 'Django로 REST API를 구현한다'
        skill = {'name': name, 'application': goal}
        rows = {}
        for key, title, section, unit in [
            ('api', '상품 가져오기', '파일 요청', 'Django REST Framework의 MultiPartParser로 CSV 요청을 받고 잘못된 파일을 거절한다.'),
            ('foundation', '장고 첫걸음', 'Django', '장고 라우팅 구성과 웹 화면 만들기'),
            ('prereq', 'FastAPI 자료 업로드', '선수지식', 'Django REST Framework의 APIView로 파일 수신과 검증'),
        ]:
            rows[key] = dict(id=key,title=title,type='course',usable=True,cost=0,skills=[name],hours=1,
                             curriculum={'items':[{'section':section,'title':unit}]})
        pools,_=rag.retrieve({'goal':goal},{'skills':[skill]},rows,{'id':'A1','learningSkills':[skill]},
                             embed=lambda texts:[[1.]*rag.DIMENSIONS for _ in texts],
                             search=lambda kind,ids,*args:[dict(resource_id=i,similarity=.8,current_cost=0) for i in ids])
        courses=pools[0]['courses']
        self.assertEqual(courses[0]['id'],'api')
        self.assertNotIn('prereq',[r['id'] for r in courses])

    def test_same_goal_and_skill_share_search_then_rank_by_course(self):
        name = 'SQL 쿼리 튜닝 & 인덱스 최적화'
        goal = 'PostgreSQL 실행계획을 읽고 인덱스 적용 전후의 스캔 비용을 비교한다'
        lessons = 'PostgreSQL 실행계획에서 인덱스 스캔과 순차 스캔의 비용을 측정하는 실습'
        items = {rid: dict(id=rid, type='course', usable=True, skills=[name], title=rid, cost=cost,
                           difficulty=level, hours=minutes/60, timeStatus='confirmed',
                           curriculum={'items':[{'title':unit}]})
                 for rid, cost, level, minutes, unit in [
                     ('short',100,'BEGINNER',55,lessons), ('free',0,'INTERMEDIATE',130,lessons),
                     ('deep',200,'ADVANCED',420,lessons+' 및 실행계획 최적화 검증'),
                     ('irrelevant',0,'ADVANCED',5,'사용자 인터뷰 설문지 작성'),
                     ('other-engine',0,'ADVANCED',10,lessons.replace('PostgreSQL', 'MySQL'))]}
        items['other-engine']['curriculum']['items'].append({'title':'MySQL, Oracle, PostgreSQL 설계 철학 비교'})
        def search(kind, ids, vector, limit, free):
            return [dict(resource_id=i,similarity=.8,current_cost=items[i]['cost']) for i in ids]
        queries = []
        for track, first in [('A1','free'),('A2','short'),('A3','deep')]:
            with self.subTest(track=track):
                skill = dict(name=name, application=track, coreOutcome='쿼리 병목',
                             coreCriteria=['조인, 스캔, 행 수, 비용 중 필요한 근거'],followUpScope=[])
                embed = Mock(return_value=[[1.] * rag.DIMENSIONS])
                lookup = Mock(side_effect=search)
                pools,_ = rag.retrieve({'goal':goal},{'skills':[skill]},items,
                                        {'id':track,'learningSkills':[skill]},embed=embed,search=lookup)
                queries.append(embed.call_args.args[0])
                self.assertEqual(set(lookup.call_args.args[1]),set(items))
                ids = [r['id'] for r in pools[0]['courses']]
                self.assertEqual(ids[0],first)
                self.assertNotIn('irrelevant',ids)
                self.assertNotIn('other-engine',ids)
        self.assertEqual(queries, [queries[0]] * 3)

    def setUp(self):
        self.items = {}
        for prefix, lesson, minutes, count in [
            ('detect', '객체 탐지 실습에서 경계 상자와 클래스 점수를 계산한다.', 15, 20),
            ('mask', '영상 분할 모델을 구현하고 픽셀 마스크를 생성한다.', 60, 6),
        ]:
            for i in range(count):
                rid = f'{prefix}{i:02}'
                self.items[rid] = dict(id=rid, title=rid, type='course', usable=True, cost=0,
                                       skills=[self.name], difficulty='BEGINNER', hours=minutes / 60,
                                       timeStatus='confirmed', curriculum={'items':[{'title':lesson}]})
        self.project = {'goal':self.target}
        self.skill = dict(name=self.name, application=self.target, coreOutcome=self.target,
                          coreCriteria=[self.target], followUpScope=['객체 탐지와 바운딩 박스'])

    def search(self, kind, ids, vector, limit, free):
        return [dict(resource_id=rid, similarity=.9 if rid.startswith('detect') else .65,
                     current_cost=self.items[rid]['cost']) for rid in sorted(ids)[:limit]]

    def retrieve(self, track='A2', search=None):
        selection = {'skills':[self.skill]}
        course = {'id':track,'learningSkills':[self.skill]}
        pools,_ = rag.retrieve(self.project, selection, self.items, course,
                               embed=lambda texts: [[1.0]*rag.DIMENSIONS for _ in texts],
                               search=search or self.search)
        return selection, course, pools

    def test_model_request_rescues_six_grounded_masks_and_ignores_deferred_detection(self):
        selection, course, pools = self.retrieve()
        def capture(_, payload):
            cards=payload['skills'][0]['courses']
            self.assertEqual({c['title'] for c in cards}, {f'mask{i:02}' for i in range(6)})
            self.assertTrue(all(any('마스크' in u['title'] for u in c['outline']) for c in cards))
            raise InputCaptured()
        with self.assertRaises(InputCaptured):
            recommend_resources(self.project, selection, self.items, capture, course=course, retrieved_pools=pools)

    def test_prerequisites_and_paid_free_cards_cannot_rescue_a_course(self):
        self.items['mask00']['cost']=10000
        self.items['mask01']['curriculum']={'items':[{'title':'선수지식', 'description':'영상 분할과 픽셀 마스크'},
                                                    {'title':'자원 관리'}]}
        _,_,pools=self.retrieve('A1')
        ids={r['id'] for r in pools[0]['courses']}
        self.assertEqual({rid for rid in ids if rid.startswith('mask')},{f'mask{i:02}' for i in range(2,6)})

    def test_free_checks_live_price_and_cannot_select_records_without_vectors(self):
        def lookup(kind, ids, vector, limit, free):
            return [dict(r, current_cost=100) if r['resource_id']=='mask00' else r
                    for r in self.search(kind, ids, vector, limit, free) if r['resource_id']!='mask01']
        _,_,pools=self.retrieve('A1', lookup)
        ids={r['id'] for r in pools[0]['courses']}
        self.assertFalse({'mask00', 'mask01'} & ids)
        self.assertTrue({'mask02', 'mask03', 'mask04', 'mask05'} <= ids)

    def test_skill_tag_alone_does_not_enable_additional_search(self):
        self.skill={'name':self.name,'application':'개인 프로젝트 실습'}
        search=Mock(side_effect=self.search)
        self.retrieve(search=search)
        self.assertEqual(search.call_count,1)

    def test_republished_course_uses_one_slot_per_provider(self):
        for i in range(7):
            rid=f'mask{i:02}'
            self.items[rid]=dict(self.items['mask00'],id=rid,provider='교육원',
                                 title='차선 영상 분할' if i<2 else f'분할 실습 {i}')
        self.items['mask07']=dict(self.items['mask00'],id='mask07',provider='다른 교육원')
        for track in ('A1','A2'):
            with self.subTest(track=track):
                _,_,pools=self.retrieve(track)
                courses=pools[0]['courses']
                keys={(c['provider'],c['title']) for c in courses}
                self.assertEqual(len(courses),6)
                self.assertEqual(len(keys),6)
                self.assertTrue(all(c['id'].startswith('mask') for c in courses))

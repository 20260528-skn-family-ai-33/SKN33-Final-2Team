"""세 코스의 관련 단원 전달, 심화 근거, 제외 단원과 기존 계약을 확인한다."""
from copy import deepcopy
import unittest
from app.agents.resource_recommendations import recommend_resources
from app.services import resource_evidence as evidence


def resource(items):
    return {'id':'sql','type':'course','title':'SQL 과정','skills':['SQL'],'usable':True,
            'hours':2,'cost':0,'content':'SQL 학습','curriculum':{'items':items}}


class ResourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.project={'goal':'SQL 조인 결과의 정합성 검증'}
        self.skill={'name':'SQL','application':'조인 결과 검증'}
        self.selection={'skills':[self.skill]}

    def test_free_and_challenge_receive_late_relevant_units_instead_of_first_three(self):
        row=resource([{'title':f'과정 안내 {i}'} for i in range(6)]+[{'title':'SQL 조인 결과 검증'}])
        original=deepcopy(row)
        def generate(system,payload):
            units=payload['skills'][0]['courses'][0]['outline']
            self.assertEqual(units[0]['index'],6)
            self.assertEqual(units[0]['title'],'SQL 조인 결과 검증')
            self.assertLessEqual(len(units),3)
            return {'skills':[{'name':'SQL','courses':[{'key':'S1-C1'}],'books':[]}]}
        for pid in ('A1','A2','A3'):
            active=dict(row,difficulty='ADVANCED' if pid=='A3' else 'INTERMEDIATE')
            pools=[{'name':'SQL','application':self.skill['application'],'courses':[active],'books':[]}]
            result=recommend_resources(self.project,self.selection,{'sql':active},generate,course={'id':pid},retrieved_pools=pools)
            self.assertEqual(result['skills'][0]['selectedCourse'],'sql')
        self.assertEqual(row,original)

    def test_challenge_depth_is_relevant_to_the_skill_not_unrelated_advanced_words(self):
        row=resource([{'title':'SQL 소개'},{'title':'SQL 결과 정합성 검증과 실행 계획 비교'},
                      {'title':'이미지 분류 모델 성능 평가 및 최적화'},{'title':'SQL 조인 실행'}])
        self.skill.update(targetOutcome='조인 대안 비교',completionCriteria=['SQL 실행 결과 비교','정합성 검증'])
        outline=evidence.outline(row,self.project,self.selection,self.skill,{'id':'A3'})
        self.assertEqual(outline[0]['index'],1)
        self.assertNotIn(2,[unit['index'] for unit in outline])

    def test_prerequisites_admin_rows_missing_titles_and_suspended_units_are_not_used(self):
        row=resource([{'section':'선수지식','title':'SQL 조인'},{'title':'SQL 조인', 'suspended':True},
                      {'title':'SQL 조인','title_missing':True},{'title':'강의 평가 SQL'}, {'title':'SQL 결과 검증'}])
        outline=evidence.outline(row,self.project,self.selection,self.skill,{'id':'A1'})
        self.assertEqual([unit['index'] for unit in outline],[4])

    def test_no_relevant_units_is_empty_without_fabricated_or_introductory_fallback(self):
        row=resource([{'title':'과정 소개'},{'title':'강사 소개'}])
        self.assertEqual(evidence.outline(row,self.project,self.selection,self.skill),[])

    def test_course_scope_and_depth_reach_model_without_repeated_old_activity_payload(self):
        row=dict(resource([{'title':'SQL 조인 결과 검증'}]),difficulty='ADVANCED')
        target={'name':'SQL','application':'조인 정합성 검증','targetOutcome':'SQL 대안 비교',
                'completionCriteria':['동일 결과 확인','실행 계획 비교']}
        course={'id':'A3','name':'Challenge','scope':'SQL 결과 검증','learningSkills':[target],
                'acts':[{'how':'이전 계획 본문 '*10000}],'promptProvenance':{'storedPromptHash':'old'},'optionId':'saved-id'}
        original=deepcopy(course)
        def generate(system,payload):
            self.assertEqual(payload['course']['scope'],course['scope'])
            self.assertEqual(payload['course']['learningSkills'],[target])
            self.assertNotIn('acts',payload['course'])
            self.assertNotIn('promptProvenance',payload['course'])
            self.assertNotIn('optionId',payload['course'])
            return {'skills':[{'name':'SQL','courses':[{'key':'S1-C1'}],'books':[]}]}
        result=recommend_resources(self.project,self.selection,{'sql':row},generate,course=course)
        self.assertEqual(result['skills'][0]['selectedCourse'],'sql')
        self.assertEqual(course,original)

    def test_text_search_outline_is_not_filled_by_three_image_search_implementations(self):
        project={'goal':'공개 문서와 질의를 검색하는 RAG'}
        skill={'name':'자연어 처리(NLP) & LLM 기초','application':'문서와 질의의 임베딩 및 유사도 검색 결과를 구현으로 확인'}
        row=resource([{'title':f'{name} 기반 이미지 검색 구현'} for name in ('GPT','BLIP','LLaVA')]
                     +[{'title':'임베딩 모델 이론'},{'title':'PDF QA 시스템 만들기'},{'title':'RAG 성능 평가 방법'}])
        row['skills']=[skill['name']]
        units=evidence.outline(row,project,{'skills':[skill]},skill,{'id':'A2'})
        self.assertIn(3,[unit['index'] for unit in units])
        self.assertIn(4,[unit['index'] for unit in units])
        self.assertLessEqual(sum('이미지' in unit['title'] for unit in units),1)

    def test_log_parsing_precedes_generic_implementation_and_validation_words(self):
        project={'goal':'운영 로그·배치 결과로 실패 재현 스크립트 자동화'}
        skill={'name':'Python 프로그래밍 & 비동기 I/O','application':'Python으로 로그를 파싱하고 실패 조건을 추출해 결과를 생성·검증'}
        row=resource([{'title':'NumPy 결과 생성 구현 비교 검증'},{'title':'머신러닝 모델 처리 결과 검증'},
                      {'title':'로그 파일 파싱과 실패 조건 추출'},{'title':'logging과 batch 파일 읽기'}])
        row['skills']=[skill['name']]
        units=evidence.outline(row,project,{'skills':[skill]},skill,{'id':'A3'})
        self.assertEqual(units[0]['index'],2)
        self.assertIn(3,[unit['index'] for unit in units])

    def test_related_seventh_course_can_enter_free_pool_without_price_or_time_bias(self):
        from unittest.mock import Mock
        from app.services import resource_rag as rag
        rows={str(i):dict(resource([{'title':'SQL 기본 문법'}]),id=str(i),retrievalScore=.9-i*.002) for i in range(20)}
        rows['6']['curriculum']={'items':[{'title':'SQL 조인 결과 정합성 검증'}]}
        self.skill['application']='조인 결과 정합성 검증'
        search=Mock(side_effect=lambda kind,ids,vector,limit,free:[{'resource_id':str(i),'similarity':.9-i*.002,'current_cost':0} for i in range(limit)])
        pools,_=rag.retrieve(self.project,self.selection,rows,{'id':'A1'},
                            embed=lambda texts:[[1.]+[0.]*(rag.DIMENSIONS-1) for _ in texts],search=search)
        self.assertEqual(search.call_args.args[3],20)
        self.assertEqual([row['id'] for row in pools[0]['courses']], ['6'])

    def test_challenge_prefers_grounded_comparison_within_the_allowed_difficulty(self):
        rows={'basic':resource([{'title':'SQL 조인 실행'}]),
              'deep':resource([{'title':'SQL 조인 결과 검증과 실행 계획 비교'}]),
              'unrelated':resource([{'title':'이미지 분류 성능 최적화'}])}
        for key,row in rows.items():row.update(id=key,retrievalScore=.8,hours=2,difficulty='ADVANCED')
        self.skill.update(targetOutcome='SQL 조인 대안 비교',completionCriteria=['SQL 결과 검증','실행 계획 비교'])
        result=evidence.rank_applicable(list(rows.values()),self.project,self.selection,self.skill,{'id':'A3'},limit=6,sources=rows,cache={})
        self.assertEqual(result[0]['id'],'deep')

    def test_stage_stack_and_target_scope_beat_boilerplate_in_both_tracks(self):
        cases = (
            ('ETL & 데이터 파이프라인', 'dbt로 데이터 변환 구현',
             'dbt 증분 모델로 데이터 변환을 구현하고 재처리 결과를 검증',
             'ETL 데이터 파이프라인 단계별 정리'),
            ('SQL', 'SQL 조인 결과 정합성 검증', 'SQL 조인 실행과 결과 정합성 검증',
             'SQL 단계별 정리와 기본 문법 소개'),
            ('RAG', '문서 검색 RAG 챗봇 구현', 'PDF 문서 검색 RAG 챗봇 구현과 결과 평가',
             '이미지 검색 RAG 앱 구현 및 단계별 정리'),
            ('클라우드', 'AWS에서 쿠버네티스 배포', 'AWS EKS 쿠버네티스 배포와 롤백 검증',
             'Azure 쿠버네티스 배포 단계별 정리와 설정 비교'),
            ('자연어 처리(NLP) & LLM 기초', 'NLP 토큰화 원리 이해', 'NLP 토큰화 원리와 서브워드 방식 비교',
             '회귀 통계와 신뢰구간의 단계별 정리'),
        )
        for name, target, actual, generic in cases:
            with self.subTest(name=name):
                skill = {'name': name, 'application': target, 'targetOutcome': target + ' 단계별 정리'}
                selection = {'skills': [skill]}
                project = {'goal': target}
                boilerplate = dict(resource([{'title': generic}] * 12), id='generic', title=f'{name} 고급',
                                   skills=[name], retrievalScore=.93, difficulty='ADVANCED')
                substantive = dict(resource([{'title': '과정 안내'}]), id='actual', title=f'{name} 자료',
                                   skills=[name], retrievalScore=.74, difficulty='ADVANCED',
                                   content='과정 안내\n' + '일반 수강 안내. ' * 80 + '\n' + actual)
                sources = {row['id']: row for row in (boilerplate, substantive)}
                for track in ('A1', 'A3'):
                    ranked = evidence.rank_applicable(list(sources.values()), project, selection, skill, track,
                                                      limit=2, sources=sources, cache={})
                    self.assertEqual(ranked[0]['id'], 'actual')
                    def generate(_, payload):
                        card = payload['skills'][0]['courses'][0]
                        self.assertIn(actual, card['content'])
                        self.assertTrue(card['learningEvidence']['suitable'])
                        return {'skills': [{'name': name, 'courses': [{'key': card['choiceKey']}], 'books': []}]}
                    pools = [{'name': name, 'courses': ranked, 'books': []}]
                    recommend_resources(project, selection, sources, generate, course={'id': track}, retrieved_pools=pools)

    def test_async_cancellation_target_outweighs_general_python_and_exam_material(self):
        name = 'Python 프로그래밍 & 비동기 I/O'
        skill = {'name': name, 'application': 'Python 비동기 I/O와 작업 취소·오류 처리'}
        project, selection = {'goal': '작업 스케줄러 개선'}, {'skills': [skill]}
        rows = {str(i): dict(resource([{'title': 'Python 문법과 예외 처리'}]), id=str(i), skills=[name],
                             title=f'Python 기초 {i}', retrievalScore=.99 - i * .005) for i in range(8)}
        rows['8'] = dict(resource([{'title': 'Asyncio 코루틴 작업 취소 실습'}]), id='8', title='Python 동시성',
                         skills=[name], retrievalScore=.7)
        for row in rows.values():
            row['difficulty'] = 'ADVANCED'
        ranked = evidence.rank_applicable(list(rows.values()), project, selection, skill, 'A3', limit=6,
                                          sources=rows, cache={})
        self.assertEqual(ranked[0]['id'], '8')
        generic = evidence.facts(rows['0'], project, selection)
        self.assertFalse(generic['scopeEvidence'][name])
        self.assertEqual(generic['suitability'][name]['requiredStage'], 'build')

    def test_workload_specific_async_comparison_preserves_actual_context_and_short_plan(self):
        from app.services import crash_courses
        name = 'Python 프로그래밍 & 비동기 I/O'
        skill = {'name': name, 'application': 'Python 비동기 I/O와 작업 취소·오류 처리'}
        project, selection = {'goal': '작업 스케줄러 개선'}, {'skills': [skill]}
        description = '멀티스레딩과 병렬성으로 실행 효율을 높이는 방법을 다루는 과정입니다.'
        topics = ['AsyncIO 동작 개요', 'I/O Bound(2) - threading vs asyncio vs multiprocessing']
        short = dict(resource([{'title': title} for title in topics]), id='short', skills=[name],
                     title='Python 동시성', hours=7.85, content=description + '\n파이썬 실전 문법')
        long = dict(resource([{'title': 'Python asyncio 작업 취소 실습'}]), id='long', skills=[name], hours=21.68)
        intro = dict(short, curriculum={'items': [{'title': topics[0]}]})
        facts = evidence.facts(short, project, selection)
        self.assertTrue(evidence.suitable(facts, name))
        self.assertFalse(evidence.suitable(evidence.facts(intro, project, selection), name))
        self.assertIn(description, evidence.description_excerpt(facts, project, skill))
        self.assertEqual(evidence.outline(short, project, selection, skill, 'A2', info=facts)[0]['title'], topics[1])
        plan = crash_courses.study_plan([{'name': name, 'courses': [long, short]}], project, selection,
                                        {'short': 'S1-C1', 'long': 'S1-C2'}, cache={})
        self.assertEqual(plan['uniqueHours'], 7.85)
        self.assertEqual(plan['skills'][0]['singleSwapExtraHours'], {'S1-C2': 13.83})

    def test_dbt_section_supplies_topic_but_the_unit_supplies_design_or_practice(self):
        name = 'ETL & 데이터 파이프라인'
        skill = {'name': name, 'application': 'dbt 모델·품질 테스트·증분 변환·재처리를 설계'}
        selection, project = {'skills': [skill]}, {'goal': '이벤트 데이터 파이프라인'}
        row = dict(resource([{'section': 'Airflow 데이터 파이프라인', 'title': 'Airflow DAG 설계'},
                             {'section': 'dbt resources', 'title': 'Model compile and run'},
                             {'section': 'dbt resources', 'title': 'Data Quality test'},
                             {'section': 'dbt materializations', 'title': 'Incremental materialization - design1'}]),
                   skills=[name], title='데이터 엔지니어링', content='Source, Seed, Model, Test를 직접 다루는 dbt hands-on')
        facts = evidence.facts(row, project, selection)
        self.assertTrue(evidence.suitable(facts, name))
        self.assertEqual(facts['suitability'][name]['unitIndices'], [3])
        for track in ('A1', 'A2', 'A3'):
            excerpts = evidence.outline(row, project, selection, skill, track, info=facts)
            self.assertEqual({x['index'] for x in excerpts}, {1, 2, 3})
        row['curriculum']['items'][3]['title'] = 'Incremental materialization 개념 소개'
        self.assertFalse(evidence.suitable(evidence.facts(row, project, selection), name))

    def test_linux_security_uses_platform_specific_evidence_and_concurrency_uses_real_controls(self):
        security = {'name': '시스템 & OS 보안 강화', 'application': 'Linux 권한·서비스 격리·OS 보안 강화'}
        concurrency = {'name': '멀티스레딩 & 비동기 동시성', 'application': '스레드 동기화·비동기 실행과 경쟁 상태 제어'}
        selection, project = {'skills': [security, concurrency]}, {'goal': 'POSIX 수집 데몬 구현'}
        windows = dict(resource([{'title': 'Windows AI 에이전트 격리 검증'}]), skills=[security['name']], title='Windows 보안')
        linux = dict(resource([{'title': 'setuid 프로세스 권한 제어 실습'}]), skills=[security['name']], title='OS 보안')
        async_course = dict(resource([{'title': 'Thread(4) - Lock, Deadlock'},
                                      {'title': 'I/O Bound - threading vs asyncio vs multiprocessing'}]),
                            skills=[concurrency['name']], title='Concurrent workloads')
        self.assertFalse(evidence.suitable(evidence.facts(windows, project, selection), security['name']))
        linux_info = evidence.facts(linux, project, selection)
        self.assertTrue(evidence.suitable(linux_info, security['name']))
        self.assertEqual(linux_info['suitability'][security['name']]['unverifiedTargetTopics'], ['Linux 서비스 격리'])
        self.assertTrue(evidence.suitable(evidence.facts(async_course, project, selection), concurrency['name']))
        self.assertIn(0, {x['index'] for x in evidence.outline(async_course, project, selection, concurrency, 'A2')})

    def test_topic_mentions_in_outline_are_separate_from_real_description_evidence(self):
        genuine = dict(resource([{'title': '과정 안내'}]), content='소개\nSQL 조인 실행과 결과 검증')
        misleading = dict(resource([{'title': '과정 안내'}]), id='prereq',
                          content='과정 안내\n선수지식\nSQL 조인 실행과 결과 검증')
        selection = self.selection
        facts = evidence.facts(genuine, self.project, selection)
        prereq = evidence.facts(misleading, self.project, selection)
        self.assertTrue(evidence.suitable(facts, 'SQL'))
        self.assertFalse(evidence.suitable(prereq, 'SQL'))
        self.assertEqual(evidence.outline(genuine, self.project, selection, self.skill, 'A1'), [])
        self.assertIn('SQL 조인 실행과 결과 검증', evidence.description_excerpt(facts, self.project, self.skill))

    def test_description_keeps_current_learning_after_other_course_comparison(self):
        skill = {'name': 'Docker 컨테이너 가상화', 'application': 'Docker Security와 Logging 학습'}
        project = {'goal': skill['application']}
        comparison = '기존 다른 강의에서 다루지 않았던 Docker Security와 Logging'
        offered = f'본 과정에서는 {comparison} 등과 같은 다양한 요소에 대해서도 학습할 수 있습니다.'
        for text, expected in (
            (offered, offered),
            ('이 강좌에서는 Docker Security와 Logging을 다루지 않습니다.', ''),
            (f'{comparison}은 이 과정에서도 다루지 않습니다.', ''),
            ('이전 강의에서는 Docker Security를 다루지 않았습니다. 이번 강의에서 Docker Logging을 배웁니다.',
             '이번 강의에서 Docker Logging을 배웁니다.'),
        ):
            with self.subTest(text=text):
                course = dict(resource([]), skills=[skill['name']], content=text)
                info = evidence.facts(course, project, {'skills': [skill]})
                self.assertEqual(evidence.description_excerpt(info, project, skill), expected)

    def test_unrelated_exclusion_does_not_erase_a_lesson_title_or_description(self):
        practice = 'SQL 조인 결과의 정합성을 검증하는 실습'
        excluded = '이 차시에서는 권한 관리를 다루지 않습니다.'
        for title, description in ((practice, excluded), (excluded, practice)):
            with self.subTest(title=title):
                course = resource([{'title': title, 'description': description}])
                self.assertEqual([text for _, _, text in evidence.learning_rows(course)], [practice.casefold()])
                info = evidence.facts(course, self.project, self.selection)
                self.assertTrue(evidence.course_applicable(info, self.skill))


if __name__=='__main__':
    unittest.main()

"""Crash 속성 강좌·관련성·공통 스킬 근거 및 다른 코스 보존. 모델·DB 호출 없음."""
import copy
import unittest
from unittest.mock import Mock, patch

from app.agents.resource_recommendations import recommend_resources
from app.services import crash_courses as crash, resource_rag as rag


def course(key, hours=2, **changes):
    return dict({'id': key, 'type': 'course', 'title': f'SQL 조회 {key}', 'usable': True,
                 'skills': ['SQL'], 'hours': hours, 'timeStatus': 'confirmed', 'estimated': [],
                 'cost': 0, 'difficulty': 'INTERMEDIATE', 'content': '학습목표\nSQL 조인 조회',
                 'curriculum': {'items': [{'title': 'SQL 조인 실습'}]}, 'retrievalScore': .8}, **changes)


class CrashCourseTests(unittest.TestCase):
    def setUp(self):
        self.project = {'goal': 'SQL 조회 구현', 'details': {'hours': 4, 'weeks': 6}}
        self.selection = {'skills': [{'name': 'SQL', 'application': 'SQL 조회'}]}

    def rank(self, rows):
        return crash.rank(rows, self.project, self.selection, self.selection['skills'][0])

    def test_short_course_precedes_long_in_same_relevance_window(self):
        result = self.rank([course('long', 20, retrievalScore=.88), course('short', 2, retrievalScore=.81)])
        self.assertEqual([r['id'] for r in result], ['short', 'long'])

    def test_large_vector_gap_cannot_exclude_the_shorter_essential_match(self):
        result = self.rank([course('related', 12, retrievalScore=.9), course('far', .1, retrievalScore=.5)])
        self.assertEqual([r['id'] for r in result], ['far', 'related'])

    def test_same_course_can_cover_two_skills_only_with_learning_evidence(self):
        self.selection['skills'].append({'name': 'Python', 'application': 'Python으로 SQL 연동'})
        shared = course('shared', 3, skills=['SQL', 'Python'], content='학습목표\nSQL 조회를 Python으로 연동한다.')
        result = self.rank([course('single', 2), shared])
        self.assertEqual(result[0]['id'], 'shared')
        self.assertEqual(crash.facts(shared, self.project, self.selection)['supported'], ['SQL', 'Python'])
        self.assertEqual(shared['hours'], 3)

    def test_tags_alone_do_not_give_multi_skill_efficiency_bonus(self):
        self.selection['skills'].append({'name': 'Python'})
        shared = course('tag-only', 3, skills=['SQL', 'Python'])
        self.assertEqual(self.rank([shared, course('single', 2)])[0]['id'], 'single')
        self.assertEqual(crash.facts(shared, self.project, self.selection)['supported'], ['SQL'])

    def test_goal_words_alone_cannot_replace_evidence_for_current_skill(self):
        self.selection = {'skills': [{'name': 'Python 프로그래밍 & 비동기 I/O'}]}
        self.project['goal'] = 'Python RAG 검색 챗봇'
        broad = course('no-python', .2, skills=['Python 프로그래밍 & 비동기 I/O'], title='RAG 검색 챗봇',
                       content='RAG 검색 챗봇', curriculum={'items': []})
        actual = course('python', 2, skills=['Python 프로그래밍 & 비동기 I/O'], title='Python RAG 검색 챗봇',
                        curriculum={'items': [{'title': 'Python API 응답을 파싱하고 RAG 문서로 변환하는 실습'}]})
        self.assertEqual(self.rank([broad, actual])[0]['id'], 'python')

    def test_project_scope_precedes_duration_when_both_teach_the_skill(self):
        self.project['goal'] = 'Python 데이터 분석 자동화'
        self.selection = {'skills': [{'name': 'Python 프로그래밍 & 비동기 I/O'}]}
        narrow = course('bot', .5, skills=['Python 프로그래밍 & 비동기 I/O'], title='Python 디스코드 봇',
                        content='Python으로 디스코드 봇 작성', curriculum={'items': []})
        applied = course('data', 2, skills=['Python 프로그래밍 & 비동기 I/O'], title='Python 데이터 분석 자동화',
                         curriculum={'items': [{'title': 'Python pandas 데이터 프레임 분석 자동화 실습'}]})
        self.assertEqual(self.rank([narrow, applied])[0]['id'], 'data')

    def test_explicit_fastapi_goal_is_not_replaced_by_shorter_node_course(self):
        self.project['goal'] = 'FastAPI 웹 API 서버 구현과 요청 검증'
        self.selection = {'skills': [{'name': 'RESTful API 서버 아키텍처'}]}
        node = course('node', 1, skills=['RESTful API 서버 아키텍처'], title='NodeJS API 서버 요청 검증',
                      curriculum={'items': [{'title': 'NodeJS REST API 요청 검증 구현 실습'}]})
        fastapi = course('fastapi', 4, skills=['RESTful API 서버 아키텍처'], title='FastAPI API 서버 요청 검증',
                         curriculum={'items': [{'title': 'FastAPI REST API 요청 검증 구현 실습'}]})
        self.assertEqual(self.rank([node, fastapi])[0]['id'], 'fastapi')

    def test_prerequisites_are_not_counted_as_shared_learning(self):
        self.selection['skills'].append({'name': 'Python'})
        shared = course('pre', 3, skills=['SQL', 'Python'],
                        content='학습목표\nSQL 조회\n선수지식\nPython',
                        curriculum={'items': [{'title': 'SQL 조회', 'description': 'SQL 실습\n선수지식\nPython'},
                                              {'section': '선수지식', 'title': 'Python'}]})
        self.assertEqual(crash.facts(shared, self.project, self.selection)['supported'], ['SQL'])

    def test_missing_invalid_and_estimated_hours_never_become_confirmed_shortcuts(self):
        for value in (None, 0, -1, True, float('nan'), float('inf')):
            with self.subTest(hours=value):
                self.assertEqual(self.rank([course('unknown', value), course('known', 4)])[0]['id'], 'known')
        estimated = course('estimated', .2, estimated=['hours'], timeStatus='estimated')
        self.assertEqual(self.rank([estimated, course('known', 4)])[0]['id'], 'known')

    def test_ranking_does_not_mutate_source_values(self):
        rows = [course('long', 12), course('short', 2)]
        before = copy.deepcopy(rows)
        self.rank(rows)
        self.assertEqual(rows, before)

    def test_general_word_coverage_does_not_outweigh_a_short_grounded_course(self):
        self.project['goal'] = '운영 로그 배치 실패 재현 시나리오 스크립트 자동화'
        self.selection = {'skills': [{'name': '리눅스 환경 및 Bash 스크립팅', 'application': 'Bash 반복 실행'}]}
        long = course('broad', 22, skills=['리눅스 환경 및 Bash 스크립팅'], title='Linux 종합 과정',
                      content=self.project['goal']+' Linux Bash')
        short = course('focused', 1.5, skills=['리눅스 환경 및 Bash 스크립팅'], title='Linux Bash 실행', content='Linux Bash 실행')
        self.assertEqual(self.rank([long, short])[0]['id'], 'focused')

    def test_blog_and_login_are_not_operational_log_learning(self):
        self.project['goal']='운영 로그로 배치 실패를 재현하는 Python 스크립트'
        self.selection={'skills':[{'name':'Python','application':'로그 파싱과 실패 검증'}]}
        blog=course('blog',.2,skills=['Python'],title='Python 블로그 자동화',
                    content='Python 셀레니움으로 블로그 이웃 추출과 로그인 자동화 프로그램 개발',curriculum={'items':[]})
        applied=course('logs',3,skills=['Python'],title='Python 로그 파싱',content='Python 로그 파일 파싱과 pytest 테스트')
        self.assertFalse(crash.facts(blog,self.project,self.selection)['scopeEvidence']['Python'])
        self.assertTrue(crash.facts(applied,self.project,self.selection)['scopeEvidence']['Python'])
        self.assertEqual(self.rank([blog,applied])[0]['id'],'logs')

    def test_twenty_course_reviews_are_shared_before_cutting_each_skill_to_six(self):
        items={str(i):course(str(i),1+i,retrievalScore=.9) for i in range(20)}
        common=course('common',3,skills=['SQL','Python'],content='SQL Python 연동')
        py=course('py',15,skills=['Python'],content='Python 실습')
        items.update(common=common,py=py)
        selection={'skills':[{'name':'SQL'},{'name':'Python'}]}
        def search(kind,ids,vector,limit,free):
            chosen=([str(i) for i in range(19)]+['common']) if '0' in ids else ['py']
            return [{'resource_id':key,'similarity':.9,'current_cost':0} for key in chosen]
        pools,_=rag.retrieve(self.project,selection,items,{'id':'A2'},
                            embed=lambda texts:[[1.]+[0.]*(rag.DIMENSIONS-1) for _ in texts],search=search)
        self.assertEqual([p['courses'][0]['id'] for p in pools],['common','common'])
        self.assertTrue(all(len(p['courses'])<=6 for p in pools))

    def test_etl_support_does_not_come_from_data_word_alone(self):
        self.selection = {'skills': [{'name': 'ETL & 데이터 파이프라인'}]}
        unrelated = course('data', .5, skills=['ETL & 데이터 파이프라인'], title='데이터 시각화', content='데이터를 그래프로 표현')
        pipeline = course('pipeline', 2, skills=['ETL & 데이터 파이프라인'], title='ETL 데이터 적재', content='ETL 파이프라인 구성')
        self.assertEqual(self.rank([unrelated, pipeline])[0]['id'], 'pipeline')

    def test_short_slate_keeps_six_shortest_matches_without_long_semantic_reservations(self):
        rows=[course(str(i), 20-i, retrievalScore=.9-i*.002) for i in range(20)]
        result=crash.rank(rows,self.project,self.selection,self.selection['skills'][0],limit=6)
        self.assertEqual([r['id'] for r in result],['19','18','17','16','15','14'])
        self.assertEqual(len(result),6)

    def test_shared_alignment_does_not_restore_global_word_coverage_priority(self):
        self.project['goal']='로그 실패 재현 시나리오 자동화'
        selection={'skills':[{'name':'SQL'},{'name':'Python'}]}
        broad=course('long',20,skills=['SQL','Python'],content=self.project['goal']+' SQL Python')
        short=course('short',3,skills=['SQL','Python'],content='SQL Python 로그 파싱')
        pools=[{'name':s['name'],'courses':[broad,short],'books':[]} for s in selection['skills']]
        self.assertEqual([p['courses'][0]['id'] for p in crash.align_shared_courses(pools,self.project,selection)],['short','short'])

    def test_shared_course_is_reused_if_it_reduces_unique_learning_time(self):
        selection = {'skills': [{'name': 'SQL'}, {'name': 'Python'}]}
        common = course('common', 3, skills=['SQL', 'Python'], content='SQL 조회와 Python 실습')
        pools = [{'name': 'SQL', 'courses': [course('sql', 2), common], 'books': []},
                 {'name': 'Python', 'courses': [course('py', 2, skills=['Python'], content='Python SQL 조회'), common], 'books': []}]
        before = copy.deepcopy(pools)
        result = crash.align_shared_courses(pools, self.project, selection)
        self.assertEqual([r['courses'][0]['id'] for r in result], ['common', 'common'])
        self.assertEqual(pools, before)

    def test_shared_course_is_not_forced_if_two_short_courses_are_faster(self):
        selection = {'skills': [{'name': 'SQL'}, {'name': 'Python'}]}
        common = course('common', 8, skills=['SQL', 'Python'], content='SQL 조회와 Python 실습')
        pools = [{'name': 'SQL', 'courses': [course('sql', 2), common], 'books': []},
                 {'name': 'Python', 'courses': [course('py', 2, skills=['Python'], content='Python SQL 조회'), common], 'books': []}]
        result = crash.align_shared_courses(pools, self.project, selection)
        self.assertEqual([r['courses'][0]['id'] for r in result], ['sql', 'py'])

    def test_scoped_courses_review_twenty_and_equal_free_evidence_keeps_vector_order(self):
        items = {str(i): course(str(i), 20 - i) for i in range(20)}
        search = Mock(side_effect=lambda kind, ids, vector, limit, free:
                      [{'resource_id': str(i), 'similarity': .9 - i * .002, 'current_cost': 0} for i in range(limit)])
        embed = lambda texts: [[1.0] + [0.0] * (rag.DIMENSIONS - 1) for _ in texts]
        pools, meta = rag.retrieve(self.project, self.selection, items, {'id': 'A2'}, embed=embed, search=search)
        self.assertEqual(search.call_args.args[3], 20)
        self.assertEqual([r['id'] for r in pools[0]['courses']], ['19', '18', '17', '16', '15', '14'])
        self.assertEqual(meta['version'], rag.version_for('A2'))
        free, meta = rag.retrieve(self.project, self.selection, items, {'id': 'A1'}, embed=embed, search=search)
        self.assertEqual(search.call_args.args[3], 20)
        self.assertEqual([r['id'] for r in free[0]['courses']], ['0', '1', '2', '3', '4', '5'])
        self.assertEqual(meta['version'], rag.VERSION)

    def test_main_no_period_cap_policy_preserves_long_courses_in_the_review_pool(self):
        items = {'long': course('long', 100), 'short': course('short', 2)}
        search = Mock(return_value=[{'resource_id': 'short', 'similarity': .8, 'current_cost': 0}])
        rag.retrieve(self.project, self.selection, items, {'id': 'A2'},
                     embed=lambda _: [[1.0] + [0.0] * (rag.DIMENSIONS - 1)], search=search)
        self.assertEqual(set(search.call_args.args[1]), {'long','short'})

    def test_late_relevant_outline_reaches_model_and_selected_cards_are_sorted(self):
        rows = [course('long', 12), course('short', 2, curriculum={'items': [
            {'title': f'안내 {i}'} for i in range(5)] + [{'title': 'SQL 조인 실습'}]})]
        pools = [{'name': 'SQL', 'application': 'SQL 조회', 'courses': rows, 'books': []}]

        def generate(system, payload):
            self.assertIn('중복 제외 학습시간이 가장 짧은 조합', system)
            self.assertIn('목표에 명시된 기술을 다른 기술로 대체하지', system)
            short=next(row for row in payload['skills'][0]['courses'] if row['title'].endswith('short'))
            self.assertEqual(short['outline'][0]['index'], 5)
            return {'skills': [{'name': 'SQL', 'courses': [{'key': 'S1-C1'}, {'key': 'S1-C2'}], 'books': []}]}

        result = recommend_resources(self.project, self.selection, {r['id']: r for r in rows}, generate,
                                     course={'id': 'A2'}, retrieved_pools=pools)['skills'][0]
        self.assertEqual([r['id'] for r in result['courses']], ['short', 'long'])
        self.assertEqual(result['selectedCourse'], 'short')
        self.assertTrue(result['courses'][0]['aiRecommended'])
        self.assertFalse(result['courses'][1]['aiRecommended'])

    def test_short_common_course_is_shared_before_model_and_shown_in_total_time_plan(self):
        selection={'skills':[{'name':'SQL','application':'SQL 조회'},{'name':'Python','application':'Python SQL 연동'}]}
        common=course('shared',3,skills=['SQL','Python'],content='SQL 조회와 Python 연동 실습')
        long=course('long',11,skills=['Python'],content='Python SQL 연동 실습')
        rows=[course('sql',1),common,long];items={r['id']:r for r in rows}
        pools=[{'name':'SQL','courses':rows[:2],'books':[]},{'name':'Python','courses':[long],'books':[]}]
        original=copy.deepcopy(pools)
        def generate(system,payload):
            plan=payload['crashStudyPlan']
            self.assertEqual(plan['uniqueCourses'],1)
            self.assertEqual(plan['uniqueHours'],3)
            self.assertEqual(len({p['key'] for p in plan['skills']}),1)
            self.assertIn('같은 choiceKey는 한 번만 합산',system)
            return {'skills':[{'name':p['name'],'courses':[{'key':p['key']}],'books':[]} for p in plan['skills']]}
        result=recommend_resources(self.project,selection,items,generate,course={'id':'A2'},retrieved_pools=pools)
        self.assertEqual([p['selectedCourse'] for p in result['skills']],['shared','shared'])
        shared=result['skills'][1]['courses'][0]
        self.assertTrue(shared['sharedCandidate'])
        self.assertNotIn('retrievalScore',shared)
        self.assertEqual(pools,original)

    def test_tag_only_candidate_is_not_added_to_another_skills_short_slate(self):
        selection={'skills':[{'name':'SQL'},{'name':'Python'}]}
        tagged=course('tagged',1,skills=['SQL','Python'],content='SQL 조회')
        local=course('python',3,skills=['Python'],content='Python 실습')
        pools=[{'name':'SQL','courses':[tagged],'books':[]},{'name':'Python','courses':[local],'books':[]}]
        result=crash.share_candidates(pools,self.project,selection,{r['id']:r for r in (tagged,local)},cache={})
        self.assertEqual([r['id'] for r in result[1]['courses']],['python'])

    def test_model_choice_is_not_replaced_by_an_unchosen_short_course(self):
        rows=[course('long',12),course('short',2)]
        def generate(system,payload):
            chosen=next(row for row in payload['skills'][0]['courses'] if row['title'].endswith('long'))
            plan = payload['crashStudyPlan']
            self.assertEqual(plan['uniqueHours'], 2)
            self.assertEqual(plan['skills'][0]['singleSwapExtraHours'][chosen['choiceKey']], 10)
            self.assertIn('longer_for_coverage', system)
            return {'skills':[{'name':'SQL','courses':[{'key':chosen['choiceKey']}],'books':[]}]}
        result=recommend_resources(self.project,self.selection,{r['id']:r for r in rows},generate,
                                   course={'id':'A2'},retrieved_pools=[{'name':'SQL','courses':rows,'books':[]}])
        self.assertEqual(result['skills'][0]['selectedCourse'],'long')

    def test_crash_single_swap_comparison_keeps_shared_course_and_omits_unknown_delta(self):
        selection = {'skills': [{'name': 'SQL'}, {'name': 'Python'}]}
        shared = course('shared', 3, skills=['SQL', 'Python'], content='SQL 조회와 Python 연동 실습')
        alternative = course('sql', 2)
        unknown = course('unknown', None)
        pools = [{'name': 'SQL', 'courses': [alternative, shared, unknown]}, {'name': 'Python', 'courses': [shared]}]
        plan = crash.study_plan(pools, self.project, selection, {'shared': 'S1-C1', 'sql': 'S1-C2', 'unknown': 'S1-C3'}, cache={})
        self.assertEqual(plan['uniqueHours'], 3)
        self.assertEqual(plan['skills'][0]['singleSwapExtraHours'], {'S1-C2': 2})

    def test_partial_async_course_is_not_the_default_when_a_complete_course_exists(self):
        name = 'Python 프로그래밍 & 비동기 I/O'
        project = {'goal': 'Python 비동기 API 수집기 구현'}
        selection = {'skills': [{'name': name, 'application': 'asyncio로 외부 API 호출을 병렬 처리하는 수집기 구현',
                                 'completionCriteria': ['asyncio로 동시 요청 구현', '타임아웃·취소 처리']}]}
        generic = course('generic', 3, skills=[name], title='파이썬 기초 다지기',
                         content='학습목표\n파이썬 문법과 함수, 예외 처리를 실습한다.\n비동기는 개념만 소개한다.',
                         curriculum={'items': [{'title': '파이썬 함수 실습'}, {'title': '파이썬 예외 처리 실습'},
                                               {'title': '비동기 개요'}]})
        focused = course('focused', 10, skills=[name], title='asyncio 실전',
                         content='학습목표\nasyncio로 동시 요청과 취소를 구현한다.',
                         curriculum={'items': [{'title': 'asyncio.gather로 동시 요청 구현'},
                                               {'title': '타임아웃과 작업 취소 처리'}]})
        cache = {}
        plan = crash.study_plan([{'name': name, 'courses': [generic, focused]}], project, selection,
                                {'generic': 'S1-C1', 'focused': 'S1-C2'}, cache=cache)
        self.assertEqual(crash.target_gaps(cache['generic'], name), ['비동기 I/O'])
        self.assertEqual(crash.target_gaps(cache['focused'], name), [])
        self.assertEqual(plan['skills'][0]['key'], 'S1-C2')
        self.assertEqual(plan['uniqueHours'], 10)
        # 일부 대상만 다루는 강좌도 적합 후보로 남아 모델이 보조 강좌로 고를 수 있다.
        self.assertTrue(crash.suitable(cache['generic'], name))

    def test_partial_dbt_course_reports_missing_targets_and_yields_to_complete_course(self):
        name = 'ETL & 데이터 파이프라인'
        project = {'goal': 'dbt 기반 데이터 파이프라인 구축'}
        selection = {'skills': [{'name': name, 'application': 'dbt로 증분 모델과 품질 테스트를 구현',
                                 'completionCriteria': ['dbt 증분 모델 구현', 'dbt 테스트로 품질 검증']}]}
        partial = course('partial', 2, skills=[name], title='dbt 시작하기', content='학습목표\ndbt 설치와 첫 모델 실행을 실습한다.',
                         curriculum={'items': [{'section': 'dbt 시작', 'title': 'dbt 설치와 첫 모델 실행 실습'}]})
        full = course('full', 9, skills=[name], title='dbt 실무', content='학습목표\ndbt 모델, 테스트, 증분 처리를 구현한다.',
                      curriculum={'items': [{'section': 'dbt 모델', 'title': 'dbt 모델 실습'},
                                            {'section': 'dbt 테스트', 'title': 'dbt 테스트로 품질 검증 실습'},
                                            {'section': 'dbt 증분', 'title': 'dbt 증분 모델 구현'}]})
        cache = {}
        chosen = crash.shortest_bundle([{'name': name, 'courses': [partial, full]}], project, selection, cache)
        self.assertEqual(crash.target_gaps(cache['partial'], name), ['dbt 품질 테스트', 'dbt 증분 처리'])
        self.assertEqual(chosen[name]['id'], 'full')
        plan = crash.study_plan([{'name': name, 'courses': [partial, full]}], project, selection,
                                {'partial': 'S1-C1', 'full': 'S1-C2'}, cache=cache)
        self.assertEqual(plan['skills'][0]['key'], 'S1-C2')
        # 세부 대상을 빠뜨리는 짧은 강좌를 시간 절감 교체안(-7시간)으로 보여 주지 않는다.
        self.assertEqual(plan['skills'][0]['singleSwapExtraHours'], {})
        # 'dbt로'처럼 조사가 붙은 영문 기술어만 있어도 세부 대상을 찾는다.
        particle = {'skills': [{'name': name, 'application': 'dbt로 증분 처리와 품질 테스트를 구현'}]}
        info = crash.facts(partial, project, particle)
        self.assertEqual(crash.target_gaps(info, name), ['dbt 품질 테스트', 'dbt 증분 처리'])
        # 완전한 후보가 없으면 일부 대상 강좌를 기본안으로 두고 부족한 대상을 모델 입력에 표시한다.
        plan = crash.study_plan([{'name': name, 'courses': [partial]}], project, selection, {'partial': 'S1-C1'}, cache=cache)
        self.assertEqual(plan['skills'][0]['unverifiedTargetTopics'], ['dbt 품질 테스트', 'dbt 증분 처리'])

    def test_single_swap_lists_only_suitable_alternatives(self):
        ok = course('ok', 5, title='SQL 조인 실습', content='학습목표\nSQL 조인 조회를 실습한다.')
        intro = course('intro', 1, title='SQL 소개', content='학습목표\nSQL이 무엇인지 소개한다.',
                       curriculum={'items': [{'title': 'SQL 개요 소개'}]})
        plan = crash.study_plan([{'name': 'SQL', 'courses': [ok, intro]}], self.project, self.selection,
                                {'ok': 'S1-C1', 'intro': 'S1-C2'}, cache={})
        self.assertEqual(plan['skills'][0]['key'], 'S1-C1')
        self.assertEqual(plan['skills'][0]['singleSwapExtraHours'], {})

    def test_model_empty_choice_is_preserved_with_diagnostic_and_no_invented_duration(self):
        row = course('short', 2)
        pools = [{'name': 'SQL', 'courses': [row], 'books': []}]

        def generate(_, payload):
            self.assertEqual(payload['crashStudyPlan']['uniqueHours'], 2)
            return {'skills': [{'name': 'SQL', 'courses': [], 'books': []}]}

        result = recommend_resources(self.project, self.selection, {'short': row}, generate,
                                     course={'id': 'A2'}, retrieved_pools=pools)['skills'][0]
        self.assertIsNone(result['selectedCourse'])
        self.assertEqual(result['courses'], [])
        self.assertEqual(result['courseDiagnostic']['reason'], 'insufficient_evidence')

    def test_missing_skill_coverage_cannot_form_a_confirmed_shared_plan(self):
        selection = {'skills': [{'name': 'SQL'}, {'name': 'Python'}]}
        shared = course('tagged', 1, skills=['SQL', 'Python'], content='SQL 조인 실습')
        pools = [{'name': 'SQL', 'courses': [shared], 'books': []},
                 {'name': 'Python', 'courses': [], 'books': []}]
        self.assertIsNone(crash.study_plan(pools, self.project, selection, {'tagged': 'S1-C1'}, cache={}))

    def test_only_hour_estimate_flags_change_time_certainty(self):
        row = course('short', 2, estimated=['format', 'stage'])
        plan = crash.study_plan([{'name': 'SQL', 'courses': [row]}], self.project, self.selection,
                                {'short': 'S1-C1'}, cache={})
        self.assertEqual((plan['timeStatus'], plan['uniqueHours']), ('confirmed', 2))
        row['timeStatus'] = 'unknown'
        plan = crash.study_plan([{'name': 'SQL', 'courses': [row]}], self.project, self.selection,
                                {'short': 'S1-C1'}, cache={})
        self.assertEqual((plan['timeStatus'], plan['uniqueHours']), ('unknown', None))

    def test_main_fixed_five_skills_are_preserved_in_the_short_shared_plan(self):
        names=['SQL','Python','Docker','RAG','ETL']
        selection={'skills':[{'name':name} for name in names]}
        common=course('common',3,skills=names,content='SQL Python Docker RAG ETL 실습')
        pools=[{'name':name,'courses':[course(name,2,skills=[name],content=name+' 실습'),common],'books':[]} for name in names]
        cache={}
        aligned=crash.align_shared_courses(pools,self.project,selection,cache)
        self.assertEqual([pool['name'] for pool in aligned],names)
        self.assertEqual([pool['courses'][0]['id'] for pool in aligned],['common']*5)
        plan=crash.study_plan(aligned,self.project,selection,{'common':'S1-C2'},cache=cache)
        self.assertEqual([row['name'] for row in plan['skills']],names)
        self.assertEqual(plan['uniqueHours'],3)

    def test_estimated_study_plan_does_not_claim_a_confirmed_short_total(self):
        row=course('estimate',.5,estimated=['hours'])
        pools=[{'name':'SQL','courses':[row],'books':[]}]
        plan=crash.study_plan(pools,self.project,self.selection,{'estimate':'S1-C1'},cache={})
        self.assertFalse(plan['hoursConfirmed'])
        self.assertIsNone(plan['uniqueHours'])

    def test_only_crash_recommendation_cache_version_changes(self):
        self.assertEqual(rag.version_for('A1'), rag.VERSION)
        self.assertEqual(rag.version_for('A3'), rag.VERSION)
        self.assertEqual(rag.version_for(None), rag.VERSION)
        self.assertNotEqual(rag.version_for('A2'), rag.VERSION)

    def test_old_recommendation_caches_keep_saved_choices_without_mutating_saved_data(self):
        from app.routers import preassessment
        from app.services import drafts
        source = {'generationId': 'g', 'selection': self.selection, 'skillOrder': ['SQL'],
                  'resourceChoices': {'SQL': {'enabled': True}}, 'courseRecommendations': {}}
        for pid in ('A1', 'A2', 'A3'):
            source['courseRecommendations'][pid] = {'recommendations': {
                'id': pid, 'retrieval': {'version': 'resource-pgvector-rag/v13-book-minimum-three'},
                'skills': [{'name': 'SQL', 'courses': [{'id': 'c', 'cost': 0}], 'books': []}]},
                'resourceChoices': {'SQL': {'course': 'c', 'books': [], 'enabled': True}},
                'durationEstimates': {'SQL': {'weeks': 2}}}
        original = copy.deepcopy(source)
        for pid in ('A1', 'A2', 'A3'):
            draft = {'chosen': pid, 'gen': {'options': {pid: {}}}}
            with patch.object(preassessment, 'recommendation_context', return_value=source), \
                    patch.object(drafts, '_row', return_value={'draft_choices': {'draft': draft}}), \
                    patch('app.catalog.items', return_value={'c': {'type': 'course', 'cost': 0, 'usable': True}}):
                scoped = preassessment.course_context(None, 1, 'project', pid, completed=frozenset())
            self.assertEqual(scoped['recommendations'], original['courseRecommendations'][pid]['recommendations'])
            self.assertEqual(scoped['resourceChoices'], original['courseRecommendations'][pid]['resourceChoices'])
            self.assertEqual(scoped['durationEstimates'], {'SQL': {'weeks': 2}})
        self.assertEqual(source, original)


if __name__ == '__main__':
    unittest.main()

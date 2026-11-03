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
            pools=[{'name':'SQL','application':self.skill['application'],'courses':[row],'books':[]}]
            result=recommend_resources(self.project,self.selection,{'sql':row},generate,course={'id':pid},retrieved_pools=pools)
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
        row=resource([{'title':'SQL 결과 검증'}])
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
        self.assertEqual(len(pools[0]['courses']),6)
        self.assertEqual(pools[0]['courses'][0]['id'],'6')

    def test_challenge_prefers_grounded_comparison_evidence_without_a_difficulty_quota(self):
        rows={'basic':resource([{'title':'SQL 조인 실행'}]),
              'deep':resource([{'title':'SQL 조인 결과 검증과 실행 계획 비교'}]),
              'unrelated':resource([{'title':'이미지 분류 성능 최적화'}])}
        for key,row in rows.items():row.update(id=key,retrievalScore=.8,hours=2)
        self.skill.update(targetOutcome='SQL 조인 대안 비교',completionCriteria=['SQL 결과 검증','실행 계획 비교'])
        result=evidence.rank_applicable(list(rows.values()),self.project,self.selection,self.skill,{'id':'A3'},limit=6,sources=rows,cache={})
        self.assertEqual(result[0]['id'],'deep')


if __name__=='__main__':
    unittest.main()

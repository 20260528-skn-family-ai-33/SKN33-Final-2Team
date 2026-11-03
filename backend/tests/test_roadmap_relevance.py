"""프로젝트 활용 범위 검색과 새 Challenge 응답의 도달 수준 계약."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch
from types import SimpleNamespace
from app.agents import roadmap
from app.services import course_skills
from app.services.planning_handoff import build_handoff


class RoadmapRelevanceTests(TestCase):
    def test_candidate_search_receives_only_active_skill_applications(self):
        handoff={'goal':'집계 API','focus':['SQL'],'skillNames':['SQL','운영'],'excludedSkills':['운영'],
            'skillDetails':[{'name':'SQL','application':'다중 테이블 조인 결과의 정합성 검증'},
                            {'name':'운영','application':'제외한 서버 운영'}]}
        original=deepcopy(handoff)
        selection=SimpleNamespace()
        with patch.object(roadmap.catalog,'roadmap_selection',return_value=selection) as select, patch.object(roadmap.catalog_budget,'pack',return_value={}), patch.object(roadmap,'_cat',return_value={}):
            roadmap._catalog_payload('A1',{'handoff':handoff})
        texts=select.call_args.args[0]
        self.assertIn('다중 테이블 조인 결과의 정합성 검증',texts)
        self.assertNotIn('제외한 서버 운영',texts)
        self.assertEqual(handoff,original)

    def test_handoff_preserves_personal_project_requirements_and_invalidates_on_change(self):
        saved={'completed':True,'generationId':'g','project':{'goal':'조회 API','projectSummary':'집계 서비스',
            'desiredCompetencies':'조인 정합성 검증','details':{'etc':'실시간 배포는 제외'}},
            'selection':{'skills':[{'name':'SQL','application':'조인 검증'}]},'survey':{'groups':[]},'answers':{}}
        handoff=build_handoff(saved,{}, {})
        self.assertEqual(handoff['desiredCompetencies'],'조인 정합성 검증')
        self.assertEqual(handoff['details'],{'etc':'실시간 배포는 제외'})
        old_key=handoff['key']
        saved['project']['details']['etc']='배치 처리만'
        self.assertNotEqual(old_key,build_handoff(saved,{}, {})['key'])
        self.assertEqual(handoff['details']['etc'],'실시간 배포는 제외')

    def test_new_challenge_requires_concrete_outcome_and_distinct_criteria(self):
        base={'name':'SQL','application':'조인 결과 검증'}
        for row in [base,dict(base,targetOutcome='쿼리 비교'),dict(base,targetOutcome='쿼리 비교',completionCriteria=['동일 결과 확인','동일 결과 확인'])]:
            with self.subTest(row=row),self.assertRaises(ValueError):
                course_skills.validate_recommendations([row],{'SQL'},'A3',require_depth=True)
        valid=dict(base,targetOutcome='조인 대안 비교 쿼리와 실행 결과',completionCriteria=['동일 입력의 결과 정합성 확인','실행 계획 차이와 선택 근거 기록'])
        self.assertEqual(course_skills.validate_recommendations([valid],{'SQL'},'A3',require_depth=True),[valid])

    def test_legacy_options_and_free_crash_contract_remain_compatible(self):
        row={'name':'SQL','application':'집계 쿼리 작성'}
        for course in ['A1','A2']:
            self.assertEqual(course_skills.validate_recommendations([row],{'SQL'},course,require_depth=True),[row])
        self.assertEqual(course_skills.validate_recommendations([row],{'SQL'},'A3'),[row])
        self.assertEqual(course_skills.selected({'learningSkills':[row]})[0]['application'],row['application'])

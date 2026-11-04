import unittest
from copy import deepcopy
from unittest.mock import Mock,patch
from app.learner_knowledge import from_profile,hr_context,exclusion
from app.agents.resource_recommendations import candidate_pools,recommend_from_catalog
from app.agents.skill_selection import select_skills
from app.agents.survey_generation import profile_input
from app.services.planning_handoff import build_handoff

class LearnerKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.person={'department':'개발부','grade':'대리','position':'개발자','education':['컴퓨터 전공'],'self':{'tech':['Python 2년'],'certs':['SQLD (2019-09-06 취득)']}}
        self.knowledge=from_profile(self.person)
    def test_known_intro_excluded_but_new_advanced_application_retained(self):
        for title in ['Python 입문','파이썬 기초 문법']:
            self.assertIsNotNone(exclusion({'type':'course','title':title},self.knowledge))
        for title in ['Python 비동기 입문','Python 실무 데이터 분석','Java 입문','JavaScript 입문']:
            self.assertIsNone(exclusion({'type':'course','title':title},self.knowledge))
        self.assertIsNone(exclusion({'type':'course','title':'Python 입문'},self.knowledge,'Python 기초부터 복습'))
    def test_owned_cert_does_not_imply_sql_mastery(self):
        self.assertIsNotNone(exclusion({'type':'cert','title':'SQL 개발자','certShort':'SQLD'},self.knowledge))
        self.assertIsNone(exclusion({'type':'course','title':'SQL 입문'},self.knowledge))
    def test_filter_before_candidate_limit_keeps_new_material(self):
        project={'goal':'API 구현','learnerKnowledge':self.knowledge}
        selection={'skills':[{'name':'Python'}]}
        items={key:{'id':key,'title':title,'type':'course','usable':True,'skills':['Python'],'cost':0} for key,title in [('old','Python 입문'),('new','Python 비동기 입문')]}
        result=candidate_pools(project,selection,items,limit=1)
        self.assertEqual([row['id'] for row in result[0]['courses']],['new'])
    def test_personnel_context_is_passed_without_identifiers_or_evaluations(self):
        value=profile_input({'dept':'개발부','grade':'대리','position':'개발자','jobFamily':'기술','education':['컴퓨터 전공'],'name':'비공개','code':'secret','evals':[{'score':'90'}]})
        self.assertEqual(value['grade'],'대리');self.assertEqual(value['position'],'개발자')
        context=hr_context(value)
        self.assertEqual(context['department'],'개발부')
        self.assertNotIn('name',context);self.assertNotIn('code',context);self.assertNotIn('evals',context)
    def test_skill_model_receives_knowledge_and_hr(self):
        project={'goal':'API 구현','learnerKnowledge':self.knowledge,'hrContext':hr_context(self.person)}
        model=Mock(return_value={'skills':[{'name':'Python','reason':'비동기 적용 필요','application':'비동기 API 구현'}]})
        select_skills(project,['Python'],model)
        system,payload=model.call_args.args
        self.assertIn('설치·문법 입문·기초 따라하기의 기본 재추천 금지',system)
        self.assertEqual(payload['learnerKnowledge'],self.knowledge)
        self.assertEqual(payload['hrContext']['grade'],'대리')
    def test_resource_model_and_rag_share_knowledge(self):
        pre={'project':{'goal':'API'},'selection':{'skills':[{'name':'Python'}]},'profile':self.person}
        ctx=Mock(live=True)
        with patch('app.catalog.items',return_value={}),patch('app.services.resource_rag.retrieve',return_value=([],{})) as retrieval,patch('app.agents.resource_recommendations.recommend_resources',return_value={'skills':[]}) as model:
            recommend_from_catalog(ctx,pre)
        self.assertEqual(retrieval.call_args.args[0]['learnerKnowledge'],self.knowledge)
        self.assertEqual(model.call_args.args[0]['learnerKnowledge'],self.knowledge)
    def test_handoff_keeps_known_technology_and_certificates(self):
        saved={'completed':True,'profile':self.person,'selection':{'skills':[{'name':'Python','application':'비동기'}]},'project':{'goal':'API'},'survey':{'groups':[]},'answers':{},'generationId':'g'}
        value=build_handoff(saved,{}, {})
        self.assertEqual(value['known'],['Python 2년'])
        self.assertEqual(value['learnerKnowledge']['certifications'],self.knowledge['certifications'])
    def test_empty_profile_does_not_exclude_materials(self):
        self.assertIsNone(exclusion({'type':'course','title':'Python 입문'},from_profile({})))

    def test_main_candidate_selection_is_preserved_while_repeated_intro_is_removed(self):
        from app.agents import roadmap
        from app.catalog_candidates import Selection
        rows=[{'id':'old','type':'course','title':'Python 입문'},
              {'id':'new','type':'course','title':'Python 비동기 입문'}]
        selection=Selection(rows,['Python'],[],['old'],{},[],{})
        handoff={'goal':'비동기 API 구현','learnerKnowledge':self.knowledge}
        with patch.object(roadmap.catalog,'roadmap_selection',return_value=selection),patch.object(roadmap.catalog_budget,'pack',side_effect=lambda selected,system,payload,limit: (selected,payload)):
            filtered,payload=roadmap._catalog_payload('A3',{'handoff':handoff})
        self.assertEqual([row['id'] for row in filtered.records],['new'])
        self.assertEqual(filtered.required,[])
        self.assertEqual(selection.records,rows)
        self.assertEqual(selection.required,['old'])
        self.assertEqual(payload['learnerExclusions'][0]['id'],'old')

    def test_model_cannot_restore_excluded_intro_in_returned_plan(self):
        from app.agents import roadmap
        from app.llm import LlmError
        handoff={'goal':'비동기 API 구현','learnerKnowledge':self.knowledge}
        with patch.object(roadmap,'_res',return_value={'type':'course','title':'Python 입문'}):
            with self.assertRaises(LlmError):
                roadmap._validate_learning_acts({'acts':[{'res':'old'}]},handoff)

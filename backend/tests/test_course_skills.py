import copy
import unittest
from unittest.mock import Mock, patch
from app.services import course_skills as skills
from app.services.course_recommendations import scope_view, merge_scope
from app.services.planning_handoff import build_handoff
from app.errors import ApiError


class CourseSkillsTests(unittest.TestCase):
    def setUp(self):
        from contextlib import nullcontext
        guard = patch.object(skills, 'generation_guard', side_effect=lambda *args: nullcontext())
        guard.start(); self.addCleanup(guard.stop)

    def option(self):
        return {'id':'A1','learningSkills':[{'name':'S','application':'검색 구성'},{'name':'T','application':'근거 검증'}]}

    def test_only_known_unique_skills_with_nonempty_application_allowed(self):
        good=self.option()['learningSkills']
        self.assertEqual(skills.validate_recommendations(good,{'S','T'},'A1'),good)
        for rows in ([],good+[good[0]],[{'name':'other','application':'검증'}],[{'name':'S','application':''}]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):skills.validate_recommendations(rows,{'S','T'},'A1')
        with self.assertRaises(ValueError):skills.validate_recommendations([{'name':n,'application':'검증'} for n in 'STUV'],set('STUV'),'A2')

    def test_selection_reorders_and_excludes_without_rewriting_recommendation(self):
        option=self.option();original=copy.deepcopy(option)
        option['learningSkillSelection']=[{'name':'T','enabled':True},{'name':'S','enabled':False}]
        self.assertEqual([row['name'] for row in skills.selected(option)],['T','S'])
        self.assertFalse(skills.selected(option)[1]['enabled'])
        self.assertEqual(option['learningSkills'],original['learningSkills'])
        for selection in ([{'name':'S','enabled':True}],[{'name':'S','enabled':False},{'name':'T','enabled':False}],[{'name':'S','enabled':1},{'name':'T','enabled':True}]):
            with self.subTest(selection=selection),self.assertRaises(ValueError):skills.selected(dict(option,learningSkillSelection=selection))

    def test_course_scopes_use_their_own_recommendation_and_selection(self):
        base={'selection':{'skills':[{'name':'legacy'}]},'skillOrder':['legacy'],'resourceChoices':{'S':{'enabled':False}}}
        a=self.option();a['learningSkillSelection']=[{'name':'T','enabled':True},{'name':'S','enabled':False}]
        b={'learningSkills':[{'name':'S','application':'성능 측정'}]}
        first=scope_view(base,'A1',a);second=scope_view(base,'A3',b)
        self.assertEqual(first['skillOrder'],['T']);self.assertEqual(second['skillOrder'],['S'])
        self.assertEqual(second['selection']['skills'][0]['application'],'성능 측정')
        first['recommendations']={'id':'first'}
        cached=merge_scope(base,first)
        self.assertEqual(scope_view(cached,'A1',a)['recommendations'],{'id':'first'})
        changed=self.option();changed['learningSkills'][0]['application']='다른 검색 구현'
        self.assertIsNone(scope_view(cached,'A1',changed)['recommendations'])
        self.assertEqual(base['skillOrder'],['legacy'])

    def test_material_order_follows_option_drag_order_while_cache_is_retained(self):
        option=self.option();base={}
        scoped=scope_view(base,'A1',option);scoped['recommendations']={'id':'keep'}
        saved=merge_scope(base,scoped)
        option['learningSkillSelection']=[{'name':'T','enabled':True},{'name':'S','enabled':True}]
        result=scope_view(saved,'A1',option)
        self.assertEqual(result['skillOrder'],['T','S']);self.assertEqual(result['recommendations']['id'],'keep')

    def test_handoff_no_longer_requires_resource_recommendations(self):
        saved={'completed':True,'generationId':'g','selection':{'skills':[{'name':'S','application':'구성'}]},'survey':{'groups':[]},'answers':{},'project':{'goal':'목표'}}
        result=build_handoff(saved,{},{});
        self.assertTrue(result['courseSkillSelection']);self.assertEqual(result['skillNames'],['S']);self.assertEqual(result['resourceHints'],[])

    def test_skill_save_preserves_other_courses_and_old_versions(self):
        from app.services import drafts
        old=self.option();current=self.option();current['learningSkills'][0]['application']='새 구성'
        other={'id':'A3','learningSkills':[{'name':'S','application':'측정'}]}
        w={'draft':{'chosen':'A1','gen':{'options':{'A1':current,'A3':other},'hist':{'A1':[old,current]},'cur':{'A1':1}}},'draftPlan':{'opt':'A1'}}
        before=copy.deepcopy(w)
        def mutate(employee,project,fn):fn(Mock(),w);return w
        selection=[{'name':'T','enabled':True},{'name':'S','enabled':False}]
        with patch.object(drafts,'_mutate',side_effect=mutate),patch.object(drafts,'present',side_effect=lambda value,*_:value):
            skills.save(1,'project','A1',skills.recommendation_key(current),selection)
            self.assertEqual(w['draft']['gen']['hist']['A1'][0],before['draft']['gen']['hist']['A1'][0])
            self.assertEqual(w['draft']['gen']['options']['A3'],before['draft']['gen']['options']['A3'])
            self.assertEqual(current['learningSkillSelection'],selection)
            with self.assertRaises(ApiError):skills.save(1,'project','A1','old-key',selection)

    def test_generation_attaches_track_specific_skills_and_sends_previous_skills(self):
        from types import SimpleNamespace
        from app.agents import roadmap
        h={'assessmentGenerationId':'g','focus':['S','T'],'skillNames':['S','T'],'skillOrder':['S','T'],'skillDetails':[{'name':'S'},{'name':'T'}]}
        previous={'learningSkills':[{'name':'S','application':'기존 학습'}]}
        captured=[]
        def payload(pid,value,system,*args):
            self.assertIn('로드맵별 지식·역량 추천',system)
            self.assertEqual(value['previousLearningSkills'],previous['learningSkills'])
            return value
        def generate(ctx,system,value,**kwargs):
            captured.append(value)
            return {'learningSkills':[{'name':'T','application':'심화 검증','targetOutcome':'검색 대안 비교 결과물','completionCriteria':['동일 질의로 결과 정합성 확인','대안별 차이와 선택 근거 기록']}]}
        with patch.object(roadmap,'_sys',return_value='main Track prompt'),patch.object(roadmap,'_catalog_payload',side_effect=payload),patch.object(roadmap.catalog,'skill_names',return_value=['S','T']),patch.object(roadmap.rt,'llm_json',side_effect=generate),patch.object(roadmap,'finish_option',return_value={'id':'A3','acts':[]}),patch.object(roadmap.rt,'run',side_effect=lambda ctx,name,task,inp,mock,api,**kw:api(None)):
            result=roadmap.option(SimpleNamespace(mode='openai'),{'pid':'A3','handoff':h,'previousDef':previous})
        self.assertEqual(result['learningSkills'][0]['application'],'심화 검증')
        self.assertEqual(len(result['learningSkills'][0]['completionCriteria']),2)
        self.assertEqual(result['learningSkillsKey'],skills.recommendation_key(result))
        self.assertNotIn('courseSkillSelection',h)

    def test_initial_recommendation_is_generated_once_and_preserves_existing_plan(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from app import db
        from app.agents import runtime
        from app.services import drafts
        from app.routers import preassessment
        option={'id':'A1','name':'Free','reason':'무료 중심','acts':[{'id':'a','title':'기존 활동'}]}
        w={'draft':{'gen':{'options':{'A1':option}}}}
        pre={'generationId':'g','selection':{'skills':[{'name':'S','application':'검색'}]},'project':{'goal':'검색 구현','desiredCompetencies':'검색 결과 검증','details':{'etc':'운영 배포 제외'}}}
        before=copy.deepcopy(option)
        def mutate(employee,project,fn):fn(Mock(),w);return w
        with patch.object(db,'tx',side_effect=lambda:nullcontext(Mock())),patch.object(preassessment,'recommendation_context',return_value=pre),patch.object(drafts,'_row',return_value={'draft_choices':w}),patch.object(drafts,'_wrap',side_effect=lambda value:value),patch.object(drafts,'_mutate',side_effect=mutate),patch.object(drafts,'present',side_effect=lambda value,*_:value),patch.object(runtime,'context',return_value=SimpleNamespace(live=True)),patch.object(runtime,'llm_json',return_value={'learningSkills':[{'name':'S','application':'무료 도구 기반 검색 구성'}]}) as generate:
            skills.initialize(1,'project','A1')
            skills.initialize(1,'project','A1')
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[2]['handoff']['desiredCompetencies'],'검색 결과 검증')
        self.assertEqual(generate.call_args.args[2]['handoff']['details'],{'etc':'운영 배포 제외'})
        self.assertEqual(option['acts'],before['acts'])
        self.assertEqual(option['reason'],before['reason'])
        self.assertEqual(option['learningSkills'][0]['name'],'S')

    def test_initial_recommendation_does_not_overwrite_changed_plan(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from app import db
        from app.agents import runtime
        from app.services import drafts
        from app.routers import preassessment
        option={'id':'A1','acts':[{'title':'기존'}]};w={'draft':{'gen':{'options':{'A1':option}}}}
        pre={'generationId':'g','selection':{'skills':[{'name':'S'}]},'project':{'goal':'검색'}}
        def mutate(employee,project,fn):
            option['acts']=[{'title':'변경된 계획'}]
            fn(Mock(),w)
            return w
        with patch.object(db,'tx',side_effect=lambda:nullcontext(Mock())),patch.object(preassessment,'recommendation_context',return_value=pre),patch.object(drafts,'_row',return_value={'draft_choices':w}),patch.object(drafts,'_wrap',side_effect=lambda value:value),patch.object(drafts,'_mutate',side_effect=mutate),patch.object(runtime,'context',return_value=SimpleNamespace(live=True)),patch.object(runtime,'llm_json',return_value={'learningSkills':[{'name':'S','application':'검색 구성'}]}):
            with self.assertRaises(ApiError):skills.initialize(1,'project','A1')
        self.assertNotIn('learningSkills',option)

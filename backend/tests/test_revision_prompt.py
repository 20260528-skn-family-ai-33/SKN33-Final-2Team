import json
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from app.agents import roadmap
from app.agents.roadmap_revision import revision, MARKER


class RevisionPromptTests(TestCase):
    def test_schema_preserves_revision_fields_and_activity_identifiers(self):
        for course in ('A1','A2','A3'):
            text=revision(course)
            schema=json.loads(text.split('JSON 형식 예: ',1)[1])
            self.assertEqual(set(schema),{'summary','notes','displayTitle','tagline','reason','pros','cons','weeklyHours','acts'})
            self.assertTrue(all('key' in act for act in schema['acts']))
            self.assertEqual(text.count(MARKER),1)

    def test_db_routing_does_not_append_free_policy_again_to_integrated_revision(self):
        for course in ('A1','A2','A3'):
            full='### GENERATION\nunchanged generation\n### REVISION\n'+revision(course)
            with patch.object(roadmap.db,'all_',return_value=[{'system_prompt':full}]):
                self.assertEqual(roadmap._sys(course,roadmap.REV_SYS),revision(course))

    def test_effective_revision_keeps_key_skill_done_and_source_without_duplicate_guidance(self):
        for course in ('A1','A2','A3'):
            for current_skills in (False,True):
                with self.subTest(course=course,current_skills=current_skills):
                    act={'id':'retained','stage':3,'title':'기존 과제','res':None,'hours':4,'how':'기존 설명','done':True,'skill':'SQL','skills':['SQL']}
                    definition={'learningSkills':[{'name':'SQL','application':'대조'}]}
                    if current_skills:definition['learningReport']={'skillOrder':['SQL']}
                    inp={'pid':course,'plan':{'opt':course,'name':'코스','hours':4,'start':1,'acts':[act],'def':definition},
                         'handoff':{'goal':'SQL 검증','startStage':1,'prefs':{'weeklyHours':6}},'changes':{'weeklyHours':6},'request':'시간 조정'}
                    before=deepcopy(inp);captured={}
                    def model(ctx,system,payload,**kw):
                        captured.update(system=system,payload=payload)
                        return {'acts':[],'summary':'시간 조정','notes':[]}
                    with patch.object(roadmap,'_sys',return_value=revision(course)),patch.object(roadmap.catalog,'skill_names',return_value=['SQL']),\
                         patch.object(roadmap,'_catalog_payload',side_effect=lambda pid,payload,*args:deepcopy(payload)),\
                         patch.object(roadmap.rt,'llm_json',side_effect=model),patch.object(roadmap,'_validate_learning_acts'),\
                         patch.object(roadmap,'finish_option',side_effect=lambda pid,raw,*args,**kw:deepcopy(raw)),\
                         patch('app.services.material_plan.rebuild_revision',side_effect=lambda option,*args:option),\
                         patch.object(roadmap.rt,'run',side_effect=lambda ctx,name,task,data,mock,api,**kw:api(None)):
                        roadmap.revise(SimpleNamespace(mode='openai'),inp)
                    self.assertEqual(captured['system'],revision(course))
                    current=captured['payload']['current'];sent=current['acts'][0]
                    for key in ('stage','title','res','hours','how','done','skill','skills'):self.assertEqual(sent[key],act[key])
                    self.assertEqual(sent['key'],'retained')
                    self.assertEqual('skillOrder' in current,current_skills)
                    self.assertEqual(captured['payload']['changes'],{'weeklyHours':6})
                    self.assertEqual(inp,before)

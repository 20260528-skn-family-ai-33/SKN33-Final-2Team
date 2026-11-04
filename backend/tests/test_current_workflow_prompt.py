from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from app import llm
from app.errors import cause
from app.agents import roadmap as rm

class CurrentWorkflowPromptTests(TestCase):
    def generate(self, depth=True, system='DB 기존 시스템 프롬프트'):
        handoff={'goal':'SQL 집계 검증','assessmentGenerationId':'g','selectedSkillsFixed':True,'skillNames':['SQL'],'skillOrder':['SQL'],'skillDetails':[{'name':'SQL','application':'집계 검증'}]}
        learning={'name':'SQL','application':'설계 검증'}
        if depth:learning.update(targetOutcome='집계 쿼리 비교 보고서',completionCriteria=['정합성 확인','대안 비교'])
        captured={}
        def model(ctx,system,payload,**kw):captured.update(system=system,payload=payload);return {'acts':[],'learningSkills':[learning]}
        with patch.object(rm,'_sys',return_value=system), patch.object(rm.catalog,'skill_names',return_value=['SQL']), patch.object(rm,'_catalog_payload',side_effect=lambda pid,payload,*args:deepcopy(payload)), patch.object(rm.rt,'llm_json',side_effect=model), patch.object(rm,'_validate_learning_acts'), patch.object(rm,'finish_option',return_value={'acts':[]}), patch.object(rm.rt,'run',side_effect=lambda ctx,name,task,inp,mock,api,**kw:api(None)):
            result=rm.option(SimpleNamespace(mode='openai'),{'pid':'A3','handoff':handoff})
        return result,captured
    def test_fixed_flow_explicit_schema_and_depth_targets_reach_model(self):
        result,captured=self.generate()
        self.assertIn('현재 실행 단계',captured['system']);self.assertIn('completionCriteria',captured['system'])
        self.assertIn('기간 상한을 적용하지 않는다',captured['system']);self.assertNotIn('최대 3개',captured['system'].split('[현재 실행 단계')[0])
        self.assertEqual(result['learningSkills'][0]['targetOutcome'],'집계 쿼리 비교 보고서')
        self.assertEqual(result['learningSkills'][0]['application'],'집계 검증')
    def test_missing_depth_still_fails_instead_of_inventing_fields(self):
        with self.assertRaises(llm.LlmError):self.generate(False)
    def test_contract_failure_is_format_error_not_unknown_provider_failure(self):
        self.assertEqual(cause('Challenge 추천에는 구체적인 산출물과 완료 기준 2~4개가 필요해요.')['kind'],'format')

    def test_integrated_generation_contract_is_not_followed_by_duplicate_policies(self):
        system='[통합 생성 계약 roadmap-generation/v1]\n전체 계약'
        _,captured=self.generate(system=system)
        self.assertEqual(captured['system'],system)

    def test_integrated_free_prompt_does_not_receive_another_free_override(self):
        text='[통합 생성 계약 roadmap-generation/v1]\n무료 정책'
        full='### GENERATION\n'+text+'\n### REVISION\n기존 수정 지침'
        with patch.object(rm.db,'all_',return_value=[{'system_prompt':full}]):
            self.assertTrue(rm._sys('A1',rm.R_SYS).startswith(text))
            self.assertNotIn('최신 Free Course 정책',rm._sys('A1',rm.R_SYS))
            self.assertIn('최신 Free Course 정책',rm._sys('A1',rm.REV_SYS))

    def test_integrated_prompt_schemas_keep_track_specific_output_contract(self):
        import json
        from app.agents.roadmap_generation import generation
        for course in ('A1','A2','A3'):
            text=generation(course)
            schema=json.loads(text.split('JSON 형식 예: ',1)[1])
            self.assertTrue({'displayTitle','tagline','reason','pros','cons','scope','weeklyHours','acts','learningSkills'} <= set(schema))
            self.assertEqual('targetOutcome' in schema['learningSkills'][0],course=='A3')
            self.assertEqual('completionCriteria' in schema['learningSkills'][0],course=='A3')
            self.assertEqual(text.count('[통합 생성 계약 roadmap-generation/v1]'),1)

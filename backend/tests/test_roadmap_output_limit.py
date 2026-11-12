"""실제 모델 호출 없이 제공자별 출력 상한과 문맥 설정 검증."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch
from app import llm,catalog_budget as budget

class RoadmapOutputLimitTests(TestCase):
    def test_openai_roadmap_caps_completion_only_for_roadmap_role(self):
        reply={'choices':[{'message':{'content':'{}'}}]}
        with patch.object(llm,'openai',return_value=reply) as call,patch.object(llm,'S',replace(llm.S,openai_key='mock',openai_reasoning=None)):
            llm.chat('openai',[{'role':'user','content':'mock'}],role='roadmap')
            self.assertEqual(call.call_args.args[1]['max_completion_tokens'],7000)
            llm.chat('openai',[{'role':'user','content':'mock'}])
            self.assertNotIn('max_completion_tokens',call.call_args.args[1])

    def test_ollama_roadmap_sets_prediction_cap_and_default_context(self):
        for configured,expected in ((0,20480),(16384,16384),(32768,32768)):
            with self.subTest(configured=configured),patch.object(llm,'ollama',return_value={'message':{'content':'{}'}}) as call,patch.object(llm,'S',replace(llm.S,ollama_num_ctx=configured)):
                llm.chat('ollama',[{'role':'user','content':'mock'}],role='roadmap')
                options=call.call_args.args[1]['options']
                self.assertEqual(options['num_predict'],7000)
                self.assertEqual(options['num_ctx'],expected)
                llm.chat('ollama',[{'role':'user','content':'mock'}])
                self.assertNotIn('num_predict',call.call_args.args[1].get('options',{}))

"""유형별 프롬프트 연결과 규정·회사·생활의 응답 계약을 외부 연결 없이 검사한다."""
from __future__ import annotations

from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import llm
from app.agents import grounded_answer as answer, runtime as rt


class KnowledgePromptTest(unittest.TestCase):
    def setUp(self):
        self.sources = [
            {'id': 'real-article-1', 'title': '교육 신청', 'text': '교육은 사내 포털에서 신청한다.'},
            {'id': 'real-article-2', 'title': '교육 경비', 'text': '경비 지급기준은 별도로 정한다.'},
        ]
        self.enterContext(patch.object(llm, 'available', return_value=True))
        self.enterContext(patch.object(rt, '_record_call'))
        self.enterContext(patch.object(llm, 'S', replace(llm.S, openai_key='test', ollama_url='http://test', openai_json=True)))

    def generate(self, provider, topic, response, sources=None, *, native_refusal=False):
        message = {'refusal': '민감한 원문은 반환하지 않음', 'content': None} if native_refusal else {
            'content': json.dumps({'answer': response}, ensure_ascii=False)}
        with (patch.object(llm, 'ollama', return_value={'message': message}) as ollama,
              patch.object(llm, 'openai', return_value={'choices': [{'message': message}]}) as openai):
            result = answer.generate(rt.Ctx(1, provider=provider), topic, '교육비 지원 금액은?',
                                     self.sources if sources is None else sources, {},
                                     history=[{'role': 'user', 'content': '교육 신청에 관해 알려줘'}])
        called, unused = (ollama, openai) if provider == 'ollama' else (openai, ollama)
        called.assert_called_once()
        unused.assert_not_called()
        payload = called.call_args.args[1]
        schema = (payload.get('format') if provider == 'ollama' else
                  payload.get('response_format', {}).get('json_schema', {}).get('schema'))
        if not isinstance(schema, dict):
            schema = None
        return result, payload, schema

    def test_company_and_life_keep_existing_full_response_contract(self):
        for provider in ('ollama', 'openai'):
            for topic in ('company', 'life'):
                for status in answer.STATUSES:
                    with self.subTest(provider=provider, topic=topic, status=status):
                        ids = ['S001'] if status in ('found', 'partial') else []
                        response = {'status': status, 'summary': '기존 안내문', 'sourceIds': ids}
                        result, payload, schema = self.generate(provider, topic, response,
                                                               [] if status == 'not_found' else self.sources)
                        self.assertEqual(result, dict(response, sourceIds=['real-article-1'] if ids else []))
                        if provider == 'ollama':
                            self.assertEqual(schema['required'], ['status', 'summary', 'sourceIds'])
                        else:
                            self.assertIsNone(schema)
                        expected = answer.COMPANY_SYSTEM if topic == 'company' else answer.LIFE_SYSTEM
                        self.assertEqual(payload['messages'][0]['content'], expected)
                        self.assertNotEqual(expected, answer.REGULATION_SYSTEM)
                        self.assertNotEqual(answer.COMPANY_SYSTEM, answer.LIFE_SYSTEM)
                        if provider == 'ollama':
                            self.assertEqual(payload['format'], schema)
                        else:
                            self.assertEqual(payload['response_format'], {'type': 'json_object'})

    def test_knowledge_sources_keep_limits_virtual_flag_and_history(self):
        sources = [{'id': 'life-1', 'document': '생활 안내', 'text': '예약 메뉴에서 신청한다.',
                    'location': '예약 안내', 'asOf': '2025년 예시', 'sourceLimits': '메뉴 위치 안내용',
                    'isVirtual': True, 'textTruncated': False}]
        for provider in ('ollama', 'openai'):
            with self.subTest(provider=provider):
                result, payload, _ = self.generate(provider, 'life', {
                    'status': 'partial', 'summary': '가상 안내에서는 예약 메뉴를 이용해요.',
                    'sourceIds': ['S001']}, sources)
                user = json.loads(payload['messages'][-1]['content'])
                self.assertEqual(user['topic'], 'life')
                self.assertEqual(user['sources'], [dict(sources[0], id='S001')])
                self.assertEqual(payload['messages'][1], {'role': 'user', 'content': '교육 신청에 관해 알려줘'})
                self.assertEqual(result['sourceIds'], ['life-1'])

    def test_invalid_knowledge_output_is_an_error_without_retry(self):
        invalid = [
            {'status': 'found', 'summary': '안내예요.', 'sourceIds': ['S999']},
            {'status': 'found', 'summary': ' ', 'sourceIds': ['S001']},
            {'status': 'partial', 'summary': '일부 안내예요.', 'sourceIds': []},
            {'status': 'not_found', 'summary': '', 'sourceIds': ['S001']},
            {'status': 'refused'},
        ]
        for provider in ('ollama', 'openai'):
            for topic in ('company', 'life'):
                for response in invalid:
                    with self.subTest(provider=provider, topic=topic, response=response):
                        with patch.object(rt, 'llm_json', return_value=response) as model:
                            with self.assertRaises(llm.LlmError):
                                answer.generate(rt.Ctx(1, provider=provider), topic, '질문', self.sources, {})
                        model.assert_called_once()

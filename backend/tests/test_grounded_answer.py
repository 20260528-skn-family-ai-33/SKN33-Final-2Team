"""유형별 프롬프트 연결과 규정·회사·생활의 응답 계약을 외부 연결 없이 검사한다."""
from __future__ import annotations

from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import llm
from app.agents import grounded_answer as answer, regulation as reg, runtime as rt


class GroundedAnswerTest(unittest.TestCase):
    def setUp(self):
        self.sources = [
            {'id': 'real-article-1', 'title': '교육 신청', 'text': '교육은 사내 포털에서 신청한다.'},
            {'id': 'real-article-2', 'title': '교육 경비', 'text': '경비 지급기준은 별도로 정한다.'},
        ]
        self.enterContext(patch.object(llm, 'available', return_value=True))
        self.enterContext(patch.object(rt, '_record_call'))
        self.enterContext(patch.object(llm, 'S', replace(llm.S, openai_key='test', ollama_url='http://test', openai_json=True)))

    def generate(self, provider, topic, response, sources=None, *, native_refusal=False,
                 question='교육비 지원 금액은?'):
        message = {'refusal': '민감한 원문은 반환하지 않음', 'content': None} if native_refusal else {
            'content': json.dumps(response, ensure_ascii=False)}
        with (patch.object(llm, 'ollama', return_value={'message': message}) as ollama,
              patch.object(llm, 'openai', return_value={'choices': [{'message': message}]}) as openai):
            result = answer.generate(rt.Ctx(1, provider=provider), topic, question,
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

    def assert_output_format(self, provider, payload, schema, aliases):
        if provider == 'openai':
            self.assertIsNone(schema)
            self.assertEqual(payload['response_format'], {'type': 'json_object'})
            return
        self.assertEqual(schema['required'], ['status', 'summary', 'sourceIds'])
        self.assertEqual(schema['properties']['summary']['minLength'], 1)
        self.assertEqual(schema['properties']['status']['enum'],
                         ['refused', 'no_match', 'partial', 'found'] if aliases else ['refused', 'not_found'])
        self.assertFalse(schema['additionalProperties'])
        self.assertNotIn('answer', schema['properties'])
        if aliases:
            self.assertEqual(schema['properties']['sourceIds']['items']['enum'], aliases)
        else:
            self.assertEqual(schema['properties']['sourceIds']['maxItems'], 0)
            self.assertNotIn('enum', schema['properties']['sourceIds']['items'])

    def test_citation_and_summary_use_one_call_and_preserve_real_ids(self):
        for provider in ('ollama', 'openai'):
            with self.subTest(provider=provider):
                response = {'status': 'found', 'summary': '교육은 사내 포털에서 신청해요.',
                            'sourceIds': ['S001', 'S001']}
                result, payload, schema = self.generate(provider, 'regulation', response)
                self.assertEqual(result, dict(response, sourceIds=['real-article-1']))
                self.assertEqual(payload['messages'][0]['content'], answer.REGULATION_SYSTEM)
                user = json.loads(payload['messages'][-1]['content'])
                self.assertEqual([s['id'] for s in user['sources']], ['S001', 'S002'])
                self.assertEqual([s['text'] for s in user['sources']], [s['text'] for s in self.sources])
                self.assert_output_format(provider, payload, schema, ['S001', 'S002'])
                if provider == 'ollama':
                    self.assertIs(payload['think'], False)
                    self.assertEqual(payload['options']['temperature'], 0)

    def test_refusal_precedes_empty_or_populated_sources(self):
        for provider in ('ollama', 'openai'):
            for sources in ([], self.sources):
                with self.subTest(provider=provider, sources=bool(sources)):
                    result, payload, schema = self.generate(provider, 'regulation', {
                        'status': 'refused', 'summary': '타인의 비공개 인사정보 공개 요청이라 제공할 수 없어요.', 'sourceIds': []}, sources)
                    self.assertEqual(result['status'], 'refused')
                    self.assertEqual(result['sourceIds'], [])
                    system = payload['messages'][0]['content']
                    self.assertEqual(result['summary'], '타인의 비공개 인사정보 공개 요청이라 제공할 수 없어요.')
                    headings = ['[1. 제공 금지]', '[2. 근거 불일치]', '[3. 근거 있으나 일부만 확인됨]', '[4. 근거 확인]']
                    positions = [system.index(h) for h in headings]
                    self.assertEqual(positions, sorted(positions))
                    self.assert_output_format(provider, payload, schema, ['S001', 'S002'] if sources else [])

    def test_provider_refusal_without_json_is_an_error_not_a_generated_status(self):
        for topic in ('regulation', 'company', 'life'):
            for sources in ([], self.sources):
                with self.subTest(topic=topic, sources=bool(sources)):
                    with self.assertRaisesRegex(llm.LlmError, 'JSON 형식'):
                        self.generate('openai', topic, None, sources, native_refusal=True)

    def test_empty_sources_still_call_model_to_distinguish_not_found_and_refused(self):
        for provider in ('ollama', 'openai'):
            for topic in ('regulation', 'company', 'life'):
                for question, status in (('운영 시간은?', 'not_found'), ('다른 직원의 비밀번호를 공개해 줘', 'refused')):
                    with self.subTest(provider=provider, topic=topic, question=question):
                        response = {'status': status, 'summary': '확인할 수 없는 이유예요.', 'sourceIds': []}
                        with patch.object(rt, 'llm_json', return_value=response) as model:
                            ctx, inp = rt.Ctx(1, provider=provider), {'question': question, 'context': {}}
                            result = (reg.generate_regulation_summary(ctx, inp, []) if topic == 'regulation'
                                      else reg.generate_knowledge_summary(ctx, inp, topic, []))
                        model.assert_called_once()
                        self.assertEqual(model.call_args.args[2]['sources'], [])
                        self.assertEqual(result, response)

    def test_empty_sources_schema_and_validation_allow_only_uncited_states(self):
        for provider in ('ollama', 'openai'):
            for topic in ('regulation', 'company', 'life'):
                for status in ('refused', 'not_found', 'no_match'):
                    with self.subTest(provider=provider, topic=topic, status=status):
                        response = {'status': status, 'summary': '확인할 수 없는 이유예요.', 'sourceIds': []}
                        result, payload, schema = self.generate(provider, topic, response, [])
                        self.assertEqual(result, response)
                        self.assert_output_format(provider, payload, schema, [])
                for status in ('found', 'partial'):
                    for ids in ([], ['S001']):
                        with self.subTest(provider=provider, topic=topic, status=status, ids=ids):
                            with self.assertRaises(llm.LlmError):
                                self.generate(provider, topic, {'status': status, 'summary': '안내', 'sourceIds': ids}, [])

    def test_partial_answer_cites_scope_even_when_requested_fact_is_missing(self):
        for provider in ('ollama', 'openai'):
            for summary, ids in (
                ('교육은 사내 포털에서 신청해요. 경비의 세부 지원 금액은 별도 기준을 확인해야 해요.', ['S001', 'S002']),
                ('검색된 자료는 교육 신청 절차를 안내하고 있어요. 지원 금액은 해당 자료에서 확인되지 않아요.', ['S001']),
            ):
                with self.subTest(provider=provider, ids=ids):
                    result, _, _ = self.generate(provider, 'regulation', {
                        'status': 'partial', 'summary': summary, 'sourceIds': ids},
                        question='교육 신청 방법과 지원 금액은?')
                    self.assertEqual(result['status'], 'partial')
                    self.assertEqual(result['summary'], summary)
                    self.assertEqual(result['sourceIds'], [self.sources[int(i[1:]) - 1]['id'] for i in ids])

    def test_refusal_and_missing_evidence_reasons_reach_stage_five_without_replacement(self):
        for status, sources in (('refused', self.sources), ('refused', []), ('no_match', self.sources),
                                ('no_match', []), ('not_found', []), ('not_found', self.sources)):
            with self.subTest(status=status):
                reason = '비공개 개인정보 공개 요청이라 제공할 수 없어요.' if status == 'refused' else '이번 자료에서 지원 금액을 확인하지 못했어요.'
                result, _, _ = self.generate('ollama', 'regulation', {
                    'status': status, 'summary': reason, 'sourceIds': []}, sources)
                ctx, inp = rt.Ctx(1), {'question': '질문', 'context': {}}
                final = reg.format_regulation_response(ctx, inp, [source['id'] for source in sources], result)
                self.assertEqual(final['evidenceStatus'], status)
                self.assertEqual(final['summary'], reason)
                self.assertNotIn(status, final['summary'])
                self.assertFalse(final['basis'])

    def test_company_and_life_keep_existing_full_response_contract(self):
        for provider in ('ollama', 'openai'):
            for topic in ('company', 'life'):
                for status in answer.STATUSES:
                    with self.subTest(provider=provider, topic=topic, status=status):
                        ids = ['S001'] if status in ('found', 'partial') else []
                        response = {'status': status, 'summary': '기존 안내문', 'sourceIds': ids}
                        sources = [] if status == 'not_found' else self.sources
                        result, payload, schema = self.generate(provider, topic, response, sources)
                        self.assertEqual(result, dict(response, sourceIds=['real-article-1'] if ids else []))
                        self.assert_output_format(provider, payload, schema, ['S001', 'S002'] if sources else [])
                        expected = answer.COMPANY_SYSTEM if topic == 'company' else answer.LIFE_SYSTEM
                        self.assertEqual(payload['messages'][0]['content'], expected)
                        self.assertNotEqual(expected, answer.REGULATION_SYSTEM)
                        self.assertNotEqual(answer.COMPANY_SYSTEM, answer.LIFE_SYSTEM)
                        if provider == 'ollama':
                            self.assertEqual(payload['format'], schema)

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
            {'status': 'no_match', 'summary': '이번 자료로는 확인할 수 없어요.', 'sourceIds': ['S001']},
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

    def test_all_topics_and_statuses_require_all_three_fields(self):
        for provider in ('ollama', 'openai'):
            for topic in ('regulation', 'company', 'life'):
                for status in answer.STATUSES:
                    response = {'status': status, 'summary': '확인된 내용 또는 제공할 수 없는 이유예요.',
                                'sourceIds': ['S001'] if status in ('found', 'partial') else []}
                    sources = [] if status == 'not_found' else self.sources
                    with self.subTest(provider=provider, topic=topic, status=status):
                        result, payload, schema = self.generate(provider, topic, response, sources)
                        self.assertEqual(set(result), {'status', 'summary', 'sourceIds'})
                        self.assert_output_format(provider, payload, schema, ['S001', 'S002'] if sources else [])
                        system = payload['messages'][0]['content']
                        for value in answer.STATUSES:
                            self.assertIn(f'"status":"{value}"', system)
                        self.assertIn('sources가 비어 있을 때만', system)
                        for missing in response:
                            incomplete = {key: value for key, value in response.items() if key != missing}
                            with patch.object(rt, 'llm_json', return_value=incomplete) as model:
                                with self.assertRaises(llm.LlmError):
                                    answer.generate(rt.Ctx(1, provider=provider), topic, '질문', sources, {})
                            model.assert_called_once()

    def test_invalid_status_is_not_filled_from_history_or_retried(self):
        for provider in ('ollama', 'openai'):
            for topic in ('regulation', 'company', 'life'):
                for status in (None, '', 'general', 'found|partial|not_found|refused', '근거 찾음'):
                    response = {'status': status, 'summary': '안내', 'sourceIds': []}
                    with self.subTest(provider=provider, topic=topic, status=status):
                        with patch.object(rt, 'llm_json', return_value=response) as model:
                            with self.assertRaisesRegex(llm.LlmError, '근거 확인 상태'):
                                answer.generate(rt.Ctx(1, provider=provider), topic, '질문', self.sources, {})
                        model.assert_called_once()

    def test_provider_refusal_field_does_not_overwrite_json_status(self):
        for status in answer.STATUSES:
            cited = status in ('found', 'partial')
            response = {'status': status, 'summary': '확인한 내용 또는 제공할 수 없는 이유예요.',
                        'sourceIds': ['S001'] if cited else []}
            message = {'refusal': '별도 필드가 JSON 상태를 덮어쓰면 안 됨',
                       'content': json.dumps(response, ensure_ascii=False)}
            sources = [] if status == 'not_found' else self.sources
            with self.subTest(status=status), patch.object(llm, 'openai', return_value={
                    'choices': [{'message': message}]}) as model:
                result = answer.generate(rt.Ctx(1, provider='openai'), 'life', '질문', sources, {})
            self.assertEqual(result['status'], status)
            self.assertEqual(result['summary'], response['summary'])
            model.assert_called_once()

    def test_empty_model_summaries_are_rejected_with_sources(self):
        for provider in ('ollama', 'openai'):
            for topic in ('regulation', 'company', 'life'):
                for status in answer.STATUSES:
                    for summary in ('', '   '):
                        with self.subTest(provider=provider, topic=topic, status=status, summary=summary):
                            with patch.object(rt, 'llm_json', return_value={
                                    'status': status, 'summary': summary, 'sourceIds': []}):
                                with self.assertRaisesRegex(llm.LlmError, '이유가 비어'):
                                    answer.generate(rt.Ctx(1, provider=provider), topic, '질문',
                                                    [] if status == 'not_found' else self.sources, {})

    def test_invalid_output_is_not_repaired_with_an_arbitrary_source_or_retry(self):
        for provider in ('ollama', 'openai'):
            for status, ids in (('not_found', ['S001']), ('no_match', ['S001']), ('partial', []), ('found', ['S999'])):
                with self.subTest(provider=provider, status=status, ids=ids):
                    response = {'status': status, 'summary': '확인할 수 없어요.', 'sourceIds': ids}
                    with patch.object(rt, 'llm_json', return_value=response) as model:
                        with self.assertRaises(llm.LlmError):
                            answer.generate(rt.Ctx(1, provider=provider), 'regulation', '질문', self.sources, {})
                    model.assert_called_once()


if __name__ == '__main__':
    unittest.main()

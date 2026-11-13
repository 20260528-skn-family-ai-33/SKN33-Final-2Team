"""직원 챗봇의 인증·가데이터·세 자료 범주를 외부 연결 없이 검사한다."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, jobs, knowledge, regstore, bge_knowledge_search, bge_regulation_search, regulation_embeddings
from app.agents import regulation as reg
from app.agents import runtime as rt
from app.errors import AgentError, ApiError, api_error_handler
from app.llm import LlmError
from app.routers import work
from app.services import profile


class EmployeeChatbotTest(unittest.TestCase):
    job_id = '00000000-0000-4000-8000-000000000001'

    def setUp(self):
        parents = patch.object(regstore, 'parent_context', return_value=[])
        parents.start()
        self.addCleanup(parents.stop)
        app = FastAPI()
        app.include_router(work.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)
        self.employee = auth.Account('employee', 42, '직원')
        self.admin = auth.Account('admin', 1, '관리자')

    def test_question_requires_employee_account(self):
        for account, status in ((None, 401), (self.admin, 403)):
            with (self.subTest(status=status),
                  patch.object(auth, 'account_of', return_value=account),
                  patch.object(jobs, 'start') as start):
                response = self.client.post('/api/v1/assistant/ask', json={'question': '교육 규정'})
                self.assertEqual(response.status_code, status)
                start.assert_not_called()

    def test_authenticated_empty_question_is_rejected(self):
        with (patch.object(auth, 'account_of', return_value=self.employee),
              patch.object(jobs, 'start') as start):
            response = self.client.post('/api/v1/assistant/ask', json={'question': ' '})
        self.assertEqual(response.status_code, 400)
        start.assert_not_called()

    def test_employee_modes_use_authenticated_group_without_loading_full_profile(self):
        article = {'id': 'work-7', 'reg': 'work', 'group': '일반직', 'no': '제7조',
                   'title': '교육', 'chapter': '', 'text': '교육은 등록 원문을 따른다.'}
        for provider, demo in (('openai', False), ('ollama', False), ('ollama', True)):
            stored = {}

            def start(kind, employee_id, ref, fn):
                self.assertEqual((kind, employee_id), ('assistant', self.employee.id))
                stored.update(fn(Mock()))
                return self.job_id

            settings = {'ai_provider': provider, 'demo_mock': demo, 'reasoning': {provider: 'low'}}
            with (self.subTest(provider=provider, demo=demo),
                  patch.object(rt, 'S', replace(rt.S, demo_mode=True)),
                  patch.object(auth, 'account_of', return_value=self.employee),
                  patch.object(rt.db, 'one', return_value=settings) as load_settings,
                  patch.object(profile, 'employee_group', return_value='일반직') as load_group,
                  patch.object(profile, 'view', side_effect=AssertionError('프로필 조회 금지')),
                  patch.object(reg.question_classifier, 'classify', return_value={'label': '사내 규정', 'confidence': 0.9}) as classify,
                  patch.object(reg.llm, 'available', return_value=True), patch.object(rt, '_log') as log,
                  patch.object(regstore, 'search', return_value=[{'id': 'work-7'}]) as search,
                  patch.object(regstore, 'explicit_ref', return_value=None),
                  patch.object(regstore, 'article', return_value=article),
                  patch.object(regstore, 'reg_public', return_value={'name': '취업규칙'}),
                  patch.object(regstore, 'bundle', return_value={}),
                  patch.object(rt, 'llm_json', return_value={'status': 'found', 'summary': '등록 원문을 따라요.', 'sourceIds': ['S001']}) as model,
                  patch.object(jobs, 'start', side_effect=start)):
                response = self.client.post('/api/v1/assistant/ask',
                                            json={'question': '교육비 지원을 받을 수 있나요?', 'empGroup': '실무직'},
                                            headers={'Prefer': 'respond-async'})
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json()['jobId'], self.job_id)
                self.assertEqual(load_settings.call_args.kwargs['e'], self.employee.id)
                load_group.assert_called_once_with(self.employee.id)
                self.assertEqual(log.call_args.args[0].employee_id, self.employee.id)
                self.assertTrue({'apply', 'more', 'missing'}.isdisjoint(stored['answer']))
                self.assertEqual(stored['meta']['mode'], 'mock' if demo else provider)
                if demo:
                    self.assertEqual(stored['answer']['topic'], 'regulation')
                    self.assertTrue(stored['answer']['summary'])
                    for dependency in (classify, search, model):
                        dependency.assert_not_called()
                else:
                    search.assert_called_once_with('교육비 지원을 받을 수 있나요?', 5, '일반직', provider)
                    ctx, _, payload = model.call_args.args
                    self.assertEqual(ctx.reasoning, {provider: 'low'})
                    self.assertEqual(payload['user'], {})
                    self.assertEqual(payload['sources'][0]['appliesTo'], '일반직')
                    self.assertEqual(stored['answer']['evidenceStatus'], 'found')

    def test_job_view_and_cancel_allow_only_the_employee_owner(self):
        url = f'/api/v1/jobs/{self.job_id}'
        row = {'job_id': self.job_id, 'employee_id': self.employee.id, 'kind': 'assistant',
               'status': 'running', 'progress': {}, 'result': None, 'error': None}
        cases = ((self.employee, self.employee.id, 200),
                 (auth.Account('employee', 43, '다른 직원'), self.employee.id, 404),
                 (self.admin, self.employee.id, 404),
                 (None, self.employee.id, 401),
                 (self.employee, None, 404),
                 (self.admin, None, 404))

        for account, owner, status in cases:
            row['employee_id'] = owner
            transaction = Mock()
            transaction.one.return_value = row

            @contextmanager
            def tx():
                yield transaction

            with (self.subTest(account=account, owner=owner),
                  patch.object(auth, 'account_of', return_value=account),
                  patch.object(jobs.db, 'one', return_value=row),
                  patch.object(jobs.db, 'tx', tx)):
                self.assertEqual(self.client.get(url).status_code, status)
                cancel = self.client.post(f'{url}/cancel')
                self.assertEqual(cancel.status_code, status)
                if status == 200:
                    self.assertEqual(cancel.json()['status'], 'cancelled')
                    transaction.run.assert_called_once()
                else:
                    transaction.run.assert_not_called()

    def test_old_public_job_paths_are_removed(self):
        url = f'/api/v1/assistant/jobs/{self.job_id}'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(f'{url}/cancel').status_code, 404)

    def test_demo_answers_cover_all_suggestions_and_unknown_questions(self):
        suggestions = (
            ('교육비 지원을 받을 수 있나요?', 'regulation'),
            ('통근버스 시간표는 어디서 봐요?', 'life'),
            ('승진 기준이 궁금해요', 'regulation'),
            ('근무성적평정은 언제 하나요?', 'regulation'),
            ('수자원공사는 어떤 일을 하나요?', 'company'),
            ('회의실 예약은 어디서 하나요?', 'life'),
        )
        ctx = rt.Ctx(self.employee.id, demo=True)
        with (patch.object(rt, '_log'), patch.object(rt.time, 'sleep'),
              patch.object(reg.llm, 'openai', side_effect=AssertionError('유료 임베딩 호출 금지')),
              patch.object(rt, 'llm_json', side_effect=AssertionError('모델 호출 금지'))):
            for question, topic in suggestions:
                with self.subTest(question=question):
                    answer = reg.answer(ctx, question, [], {}, documents_only=True)
                    self.assertEqual(answer['topic'], topic)
                    self.assertTrue(answer['summary'])
                    self.assertFalse(answer['basis'])
                    self.assertTrue({'apply', 'more', 'missing'}.isdisjoint(answer))
            unknown = reg.answer(ctx, '지사 주차장은 어디인가요?', [], {}, documents_only=True)
            self.assertIn('준비된 답변이 없어요', unknown['summary'])
            outside = reg.answer(ctx, '오늘 날씨 알려줘', [], {}, documents_only=True)
            self.assertEqual(outside['kind'], 'out')


class DocumentScopeTest(unittest.TestCase):
    def setUp(self):
        parents = patch.object(regstore, 'parent_context', return_value=[])
        parents.start()
        self.addCleanup(parents.stop)

    def test_documents_only_discards_even_a_supplied_profile_context(self):
        ctx = rt.Ctx(employee_id=1, me={'name': 'private', 'empGroup': '실무직', 'grade': '4급'})
        def run(ctx, agent, task, inp, *args, **kwargs):
            self.assertEqual(inp['me'], {'empGroup': '실무직'})
            self.assertEqual(inp['context'], {})
            self.assertTrue(inp['documents_only'])
            self.assertNotIn('private', str(kwargs['log_input']))
            return reg.ans(kind='regulation', summary='원문 안내')
        with patch.object(rt, 'run', side_effect=run), patch.object(regstore, 'set_for') as group:
            result = reg.answer(ctx, '질문', [], {'name': 'private', 'plans': ['private']}, documents_only=True)
        self.assertEqual(result['summary'], '원문 안내')
        group.assert_not_called()

    def test_all_questions_without_employee_group_fail_before_classification_search_and_model(self):
        cases = [(group, question) for group in (None, '', '  ')
                 for question in ('교육비 지원 조건', '구내식당 메뉴는?', '수자원공사는 어떤 일을 하나요?',
                                  '오늘 날씨는?', '실무직 교육비 지원 기준은?')]
        for group, question in cases:
            ctx = rt.Ctx(employee_id=42, me={'empGroup': group})
            with (self.subTest(group=group, question=question),
                  patch.object(reg.llm, 'available', return_value=True),
                  patch.object(reg.question_classifier, 'classify') as classify,
                  patch.object(rt, '_log') as log,
                  patch.object(regstore, 'search') as search,
                  patch.object(regstore, 'explicit_ref') as explicit_ref,
                  patch.object(rt, 'llm_json') as model,
                  self.assertRaises(AgentError) as error):
                reg.answer(ctx, question, [], {}, documents_only=True)
            classify.assert_not_called()
            search.assert_not_called()
            explicit_ref.assert_not_called()
            model.assert_not_called()
            self.assertEqual(error.exception.info['code'], 'EMPLOYEE_GROUP_UNAVAILABLE')
            self.assertEqual(error.exception.info['user'], '로그인한 직원의 직원 구분을 확인할 수 없어요')
            self.assertFalse(error.exception.info['retryable'])
            self.assertEqual(log.call_args.args[1]['mode'], 'error')

    def test_pool_uses_employee_group_by_default_and_filters_overseas(self):
        arts = {'a': {'group': '일반직', 'overseas': False}, 'b': {'group': '실무직', 'overseas': False},
                'c': {'group': '일반직', 'overseas': True}}
        with patch.object(regstore, 'data', return_value={'arts': arts}):
            self.assertEqual(regstore.pool(None, '교육'), [])
            self.assertEqual(regstore.pool('일반직', '교육'), [arts['a']])
            self.assertEqual(regstore.pool('일반직', '국외근무'), [arts['a'], arts['c']])
            self.assertEqual(regstore.pool('일반직', '교육', all_groups=True), [arts['a'], arts['b']])

    def test_search_excludes_another_employee_group(self):
        article = {'id': 'a', 'group': '실무직', 'overseas': False, 'type': 'article',
                   'title': '교육', 'no': '제1조', 'text': '교육 신청 기준'}
        with patch.object(regstore, 'data', return_value={'arts': {'a': article}}):
            self.assertEqual([hit['id'] for hit in regstore.search('교육', 4, '실무직', 'mock')], ['a'])
            self.assertEqual(regstore.search('교육', 4, '일반직', 'mock'), [])
            vector = [1.] + [0.] * 1023
            with (patch.object(regulation_embeddings, 'embed', return_value=[vector]),
                  patch.object(bge_regulation_search, '_inputs', return_value={'a': ('text', 'sha')}),
                  patch.object(bge_regulation_search, '_stored', return_value={'a': {
                      'dimensions': 1024, 'input_sha256': 'sha', 'input_version': bge_regulation_search.INPUT_VERSION,
                      'meta_sha256': 'sha', 'actual_input_sha256': 'sha', 'token_count': 3,
                      'model_revision': regulation_embeddings.PROVENANCE['model_revision'],
                      'protocol': 'bge-m3/cls-l2-fp16/v1'}}),
                  patch.dict(os.environ, ASSISTANT_SEARCH_MODE='vector'),
                  patch.object(regstore.db, 'all_', return_value=[{'rag_chunk_id': 'a', 'score': 1}]) as query):
                self.assertEqual(regstore.search('교육', 4, '일반직', 'ollama'), [])
                query.assert_not_called()
                self.assertEqual(regstore.search('교육', 4, '실무직', 'ollama'), [{'id': 'a', 'score': 1.0}])
                self.assertEqual(query.call_args.kwargs['i'], ['a'])

    def test_explicit_article_uses_only_the_employee_groups_copy_of_a_document(self):
        general = {'key': 'general', 'name': '취업규칙'}
        practice = {'key': 'practice', 'name': '취업규칙'}
        arts = {key: {'id': key, 'reg': key, 'type': 'article', 'no': '제7조', 'text': key}
                for key in ('general', 'practice')}
        data = {'sets': {'일반직': {'regs': [general]}, '실무직': {'regs': [practice]}}, 'arts': arts}
        with patch.object(regstore, 'data', return_value=data):
            self.assertIsNone(regstore.explicit_ref('취업규칙 제7조', None))
            found = regstore.explicit_ref('취업규칙 제7조', '실무직')
        self.assertEqual(found['ids'], ['practice'])

    def test_life_search_uses_its_category_and_keeps_virtual_sources(self):
        hit = {'is_virtual': True}
        with (patch.dict(os.environ, ASSISTANT_SEARCH_MODE='vector'),
              patch.object(bge_knowledge_search.db, 'val', return_value=bge_knowledge_search.TABLE),
              patch.object(regulation_embeddings, 'embed', return_value=[[1.] + [0.] * 1023]),
              patch.object(bge_knowledge_search.db, 'one', return_value={'total': 1, 'indexed': 1}) as count,
              patch.object(bge_knowledge_search.db, 'all_', return_value=[hit])):
            self.assertEqual(knowledge.search_life('식당 위치'), [hit])
        self.assertEqual(count.call_args.kwargs['category'], knowledge.LIFE_CATEGORY)
        self.assertFalse(count.call_args.kwargs['real_only'])

    def test_company_search_still_excludes_virtual_sources(self):
        with (patch.object(bge_knowledge_search.db, 'val', return_value=bge_knowledge_search.TABLE),
              patch.object(bge_knowledge_search.db, 'one', return_value={'total': 0}) as count,
              patch.object(regulation_embeddings, 'embed') as embed):
            self.assertEqual(knowledge.search_company('회사 소개'), [])
        self.assertEqual(count.call_args.kwargs['category'], knowledge.CATEGORY)
        self.assertTrue(count.call_args.kwargs['real_only'])
        embed.assert_not_called()

    def test_life_missing_vectors_is_an_error_not_empty_success(self):
        with (patch.object(bge_knowledge_search.db, 'val', return_value=bge_knowledge_search.TABLE),
              patch.object(bge_knowledge_search.db, 'one', return_value={'total': 1, 'indexed': 0})):
            with self.assertRaisesRegex(LlmError, '벡터가 없거나 원문과 달라요'):
                knowledge.search_life('식당 위치')


    def test_life_cannot_use_company_category_or_fabricated_numbers(self):
        hit = {'category': knowledge.CATEGORY, 'is_virtual': False}
        inp = {'question': '식당', 'history': [], 'context': {}}
        with patch.object(knowledge, 'search_life', return_value=[hit]):
            with self.assertRaisesRegex(LlmError, '범주'):
                reg._life_answer(rt.Ctx(None), inp)
        hit.update(category=knowledge.LIFE_CATEGORY, chunk_id='life', document_id='guide',
                   document_title='생활안내', metadata={}, chunk_text='식당 위치 안내', chunk_text_sha256='a' * 64)
        with (patch.object(knowledge, 'search_life', return_value=[hit]),
              patch.object(rt, 'llm_json', return_value={'status': 'found', 'summary': '식비는 999원', 'sourceIds': ['S001']})):
            with self.assertRaisesRegex(LlmError, '사내 생활 답변의 숫자'):
                reg._life_answer(rt.Ctx(None), inp)


if __name__ == '__main__':
    unittest.main()

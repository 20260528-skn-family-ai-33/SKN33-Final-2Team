"""익명 챗봇의 계정 분리·세 자료 범주·공개 작업 경계를 외부 연결 없이 검사한다."""
from __future__ import annotations

from contextlib import contextmanager
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, jobs, knowledge, regstore
from app.agents import regulation as reg
from app.agents import runtime as rt
from app.errors import ApiError, api_error_handler
from app.llm import LlmError
from app.routers import work
from app.services import profile


class AnonymousChatbotTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(work.r)
        app.add_exception_handler(ApiError, api_error_handler)
        self.client = TestClient(app)

    def test_question_runs_without_login_profile_settings_or_roadmaps(self):
        def start(kind, employee_id, ref, fn):
            self.assertEqual((kind, employee_id), ('assistant', None))
            result = fn(Mock())
            self.assertEqual(result['answer']['summary'], '등록 자료 답변')
            return '00000000-0000-4000-8000-000000000001'

        with (patch.object(auth, 'account_of', side_effect=AssertionError('로그인 조회 금지')),
              patch.object(profile, 'view', side_effect=AssertionError('회원 조회 금지')),
              patch.object(rt, 'context', side_effect=AssertionError('개인 설정 조회 금지')),
              patch.object(work.PL, 'records', side_effect=AssertionError('로드맵 조회 금지')),
              patch.object(work.DR, 'current', side_effect=AssertionError('작성안 조회 금지')),
              patch.object(work.REG, 'answer', return_value={'summary': '등록 자료 답변'}) as answer,
              patch.object(work.regstore, 'bundle', return_value={}),
              patch.object(jobs, 'start', side_effect=start)):
            result = self.client.post('/api/v1/assistant/ask', json={'question': '교육 규정을 알려줘'},
                                      headers={'Prefer': 'respond-async'})
        self.assertEqual(result.status_code, 202)
        ctx, _, _, context = answer.call_args.args
        self.assertIsNone(ctx.employee_id)
        self.assertEqual(ctx.me, {})
        self.assertEqual(ctx.provider, 'ollama')
        self.assertEqual(context, {})
        self.assertTrue(answer.call_args.kwargs['documents_only'])

    def test_empty_question_is_rejected_without_login(self):
        with patch.object(jobs, 'start') as start:
            result = self.client.post('/api/v1/assistant/ask', json={'question': ' '})
        self.assertEqual(result.status_code, 400)
        start.assert_not_called()

    def test_public_request_reaches_regulation_model_with_documents_and_no_profile(self):
        stored = {}
        def start(kind, employee_id, ref, fn):
            stored.update(fn(Mock()))
            return '00000000-0000-4000-8000-000000000001'
        article = {'id': 'work-7', 'reg': 'work', 'group': '일반직', 'no': '제7조',
                   'title': '교육', 'chapter': '', 'text': '교육은 등록 원문을 따른다.'}
        with (patch.object(auth, 'account_of', side_effect=AssertionError('로그인 조회 금지')),
              patch.object(profile, 'view', side_effect=AssertionError('회원 조회 금지')),
              patch.object(reg.question_classifier, 'classify', return_value={'label': '사내 규정'}),
              patch.object(reg.llm, 'available', return_value=True), patch.object(rt, '_log'),
              patch.object(regstore, 'search', return_value=[{'id': 'work-7'}]) as search,
              patch.object(regstore, 'explicit_ref', return_value=None),
              patch.object(regstore, 'article', return_value=article),
              patch.object(regstore, 'reg_public', return_value={'name': '취업규칙'}),
              patch.object(regstore, 'bundle', return_value={}),
              patch.object(rt, 'llm_json', return_value={'status': 'found', 'summary': '등록 원문을 따라요.', 'sourceIds': ['S001']}) as model,
              patch.object(jobs, 'start', side_effect=start)):
            result = self.client.post('/api/v1/assistant/ask', json={'question': '교육 규정', 'name': '전달 금지'},
                                      headers={'Prefer': 'respond-async'})
        self.assertEqual(result.status_code, 202)
        search.assert_called_once_with('교육 규정', 4, None, 'ollama', all_groups=True)
        self.assertEqual(model.call_args.args[2]['user'], {})
        self.assertEqual(model.call_args.args[2]['sources'][0]['appliesTo'], '일반직')
        self.assertEqual(stored['answer']['evidenceStatus'], 'found')
        self.assertEqual(stored['meta']['classification']['label'], '사내 규정')

    def test_public_poll_and_cancel_use_anonymous_chatbot_scope(self):
        jid = '00000000-0000-4000-8000-000000000001'
        with patch.object(jobs, 'view', return_value={'status': 'running'}) as view:
            result = self.client.get(f'/api/v1/assistant/jobs/{jid}?wait=1')
        self.assertEqual(result.status_code, 200)
        view.assert_called_once_with(jid, None, 1, anonymous_kind='assistant')
        with patch.object(jobs, 'cancel', return_value='cancelled') as cancel:
            result = self.client.post(f'/api/v1/assistant/jobs/{jid}/cancel')
        self.assertEqual(result.status_code, 200)
        cancel.assert_called_once_with(jid, None, anonymous_kind='assistant')

    def test_public_job_rejects_invalid_id(self):
        result = self.client.get('/api/v1/assistant/jobs/not-a-uuid')
        self.assertEqual(result.status_code, 422)


class PublicJobBoundaryTest(unittest.TestCase):
    def row(self, **changes):
        return dict(job_id='id', employee_id=None, kind='assistant', status='done', progress={},
                    result={'answer': 'public'}, error=None, **changes)

    def test_public_poll_allows_only_anonymous_assistant_jobs(self):
        for employee_id, kind in [(None, 'assistant'), (1, 'assistant'), (None, 'learning_generation'), (1, 'roadmap')]:
            with self.subTest(employee_id=employee_id, kind=kind):
                row = self.row()
                row.update(employee_id=employee_id, kind=kind)
                with patch.object(jobs.db, 'one', return_value=row):
                    if employee_id is None and kind == 'assistant':
                        self.assertEqual(jobs.view('id', None, anonymous_kind='assistant')['result'], row['result'])
                    else:
                        with self.assertRaises(ApiError) as error:
                            jobs.view('id', None, anonymous_kind='assistant')
                        self.assertEqual(error.exception.status, 404)

    def test_public_cancel_cannot_touch_account_or_non_chatbot_jobs(self):
        for employee_id, kind in [(None, 'assistant'), (1, 'assistant'), (None, 'roadmap')]:
            with self.subTest(employee_id=employee_id, kind=kind):
                transaction = Mock()
                transaction.one.return_value = {'employee_id': employee_id, 'kind': kind, 'status': 'running'}
                @contextmanager
                def tx():
                    yield transaction
                with patch.object(jobs.db, 'tx', tx):
                    if employee_id is None and kind == 'assistant':
                        self.assertEqual(jobs.cancel('id', None, anonymous_kind='assistant'), 'cancelled')
                        transaction.run.assert_called_once()
                    else:
                        with self.assertRaises(ApiError):
                            jobs.cancel('id', None, anonymous_kind='assistant')
                        transaction.run.assert_not_called()


class DocumentScopeTest(unittest.TestCase):
    def test_documents_only_discards_even_a_supplied_profile_context(self):
        ctx = rt.Ctx(employee_id=1, me={'name': 'private', 'empGroup': '실무직', 'grade': '4급'})
        def run(ctx, agent, task, inp, *args, **kwargs):
            self.assertEqual(inp['me'], {})
            self.assertEqual(inp['context'], {})
            self.assertTrue(inp['documents_only'])
            self.assertNotIn('private', str(kwargs['log_input']))
            return reg.ans(kind='regulation', summary='원문 안내')
        with patch.object(rt, 'run', side_effect=run), patch.object(regstore, 'set_for') as group:
            result = reg.answer(ctx, '질문', [], {'name': 'private', 'plans': ['private']}, documents_only=True)
        self.assertEqual(result['summary'], '원문 안내')
        group.assert_not_called()

    def test_all_groups_is_explicit_and_preserves_existing_employee_search(self):
        arts = {'a': {'group': '일반직', 'overseas': False}, 'b': {'group': '실무직', 'overseas': False},
                'c': {'group': '일반직', 'overseas': True}}
        with patch.object(regstore, 'data', return_value={'arts': arts}):
            self.assertEqual(regstore.pool(None, '교육'), [])
            self.assertEqual(regstore.pool('일반직', '교육'), [arts['a']])
            self.assertEqual(regstore.pool(None, '교육', all_groups=True), [arts['a'], arts['b']])
            self.assertEqual(regstore.pool(None, '국외근무', all_groups=True), list(arts.values()))

    def test_anonymous_explicit_article_uses_registered_document_without_employee_group(self):
        info = {'key': 'work', 'name': '취업규칙'}
        data = {'sets': {'일반직': {'regs': [info]}}}
        with (patch.object(regstore, 'data', return_value=data),
              patch.object(regstore, 'find_article', return_value=['article']),
              patch.object(regstore, 'article', return_value={'text': '원문'})):
            self.assertIsNone(regstore.explicit_ref('취업규칙 제7조', None))
            found = regstore.explicit_ref('취업규칙 제7조', None, all_groups=True)
        self.assertEqual(found['ids'], ['article'])

    def test_life_search_uses_its_category_and_keeps_virtual_sources(self):
        with (patch.object(knowledge.llm, 'embed_model', return_value=knowledge.MODEL),
              patch.object(knowledge.llm, 'embed_ready', return_value=True),
              patch.object(knowledge.llm, 'embed', return_value=[[1.0] * knowledge.DIMENSIONS]),
              patch.object(knowledge.db, 'one', return_value={'total': 1, 'indexed': 1}) as count,
              patch.object(knowledge.db, 'all_', return_value=[{'is_virtual': True}]) as query):
            self.assertEqual(knowledge.search_life('식당 위치'), [{'is_virtual': True}])
        self.assertEqual(count.call_args.kwargs['category'], knowledge.LIFE_CATEGORY)
        self.assertFalse(query.call_args.kwargs['real_only'])

    def test_company_search_still_excludes_virtual_sources(self):
        with (patch.object(knowledge.llm, 'embed_model', return_value=knowledge.MODEL),
              patch.object(knowledge.db, 'one', return_value={'total': 0}) as count,
              patch.object(knowledge.llm, 'embed') as embed):
            self.assertEqual(knowledge.search_company('회사 소개'), [])
        self.assertEqual(count.call_args.kwargs['category'], knowledge.CATEGORY)
        self.assertTrue(count.call_args.kwargs['real_only'])
        embed.assert_not_called()

    def test_life_missing_vectors_is_an_error_not_empty_success(self):
        with (patch.object(knowledge.llm, 'embed_model', return_value=knowledge.MODEL),
              patch.object(knowledge.db, 'one', return_value={'total': 1, 'indexed': 0})):
            with self.assertRaisesRegex(LlmError, '사내 생활 검색 임베딩이 준비되지'):
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

"""가짜 규정과 모의 모델로 조항 이어 묻기·이전 답변 전달의 회귀를 검사한다."""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app.agents import regulation as reg
from app.agents import runtime as rt
from app.llm import LlmError


class RegulationFollowUpTest(unittest.TestCase):
    def setUp(self):
        self.ctx = rt.Ctx(employee_id=1, me={'empGroup': '일반직'})
        regs = [{'key': 'edu', 'name': '인재개발규정'}, {'key': 'work', 'name': '취업규칙'}]
        for item in regs:
            item.update(version_label='test', amendment_date=None, effective_from=None,
                        file_name='', employee_group='일반직', overseas_only=False)
        self.articles = {}
        for key, no, text in [('edu', 7, '학습시간을 인정한다.'), ('edu', 9, '교육 신청은 교육포털에서 한다.'),
                              ('work', 2, '직원에게 적용한다.'), ('work', 9, '근무를 기록한다.')]:
            aid = f'{key}-{no}'
            self.articles[aid] = {'id': aid, 'reg': key, 'no': f'제{no}조', 'text': text,
                                  'title': '', 'chapter': '', 'type': 'article', 'path': '',
                                  'group': '일반직', 'overseas': False}
        data = {'regs': {item['key']: item for item in regs}, 'arts': self.articles,
                'sets': {'일반직': {'regs': regs}}}
        for target, name, value in [(reg.regstore, 'data', data), (reg.llm, 'available', True),
                                    (reg.question_classifier, 'classify', {'label': '사내 규정'})]:
            mock = patch.object(target, name, return_value=value)
            setattr(self, name, mock.start())
            self.addCleanup(mock.stop)
        search = patch.object(reg.regstore, 'search', return_value=[{'id': 'work-2'}])
        self.search = search.start()
        self.addCleanup(search.stop)
        self.history = [{'q': '인재개발규정 제7조 알려줘',
                         'a': {'kind': 'regulation', 'level': 'ok', 'summary': '학습시간을 인정해요.',
                               'basis': ['edu-7'], 'apply': '이전 적용 안내', 'more': ['이전 추가 안내'],
                               'missing': ['이전 미등록 기준']}}]

    def ask(self, question, history=None, status='found', source_ids=None, summary='교육 신청은 교육포털에서 해요.'):
        inp = {'question': question, 'me': self.ctx.me, 'context': {},
               'history': self.history if history is None else history}
        response = {'status': status, 'summary': summary,
                    'sourceIds': source_ids if source_ids is not None else
                                 ['S001'] if status in ('found', 'partial') else []}
        with patch.object(rt, 'llm_json', return_value=response) as model:
            result = reg._api(self.ctx, inp)
        return result, model, inp

    def assert_summary_history(self, model):
        self.assertEqual(model.call_args.kwargs['history'], [
            {'role': 'user', 'content': self.history[0]['q']},
            {'role': 'assistant', 'content': self.history[0]['a']['summary']},
        ])

    def test_article_follow_up_prioritizes_requested_article_and_keeps_summary(self):
        for question in ('그 규정 제9조 내용을 알려줘', '그럼 제9조는?', '제9조는요?',
                         '앞에서 설명한 규정의 제9조 내용을 자세히 알려 주세요'):
            with self.subTest(question=question):
                first, _, _ = self.ask('인재개발규정 제7조 알려줘', history=[], summary='학습시간을 인정해요.')
                self.history[0]['a'] = first
                result, model, _ = self.ask(question)
                self.assertEqual(result['basis'], ['edu-9'])
                self.assertEqual(result['retrieved'], ['edu-9', 'edu-7', 'work-2'])
                payload = model.call_args.args[2]
                self.assertEqual(payload['requested']['where'], '제9조')
                self.assertEqual(payload['sources'][0]['regulation'], '인재개발규정')
                self.assertEqual(payload['sources'][0]['no'], '제9조')
                self.assert_summary_history(model)

    def test_chatbot_includes_directly_referenced_paragraphs_without_replacing_search_hits(self):
        for aid, key, no, text in (
            ('edu-24-5', 'edu', '제24조 제5항', '제1항부터 제4항까지의 규정에도 불구하고 조정할 수 있다.'),
            ('edu-24-1', 'edu', '제24조 제1항', '위탁교육 경비의 지급기준은 따로 정한다.'),
            ('edu-24-4', 'edu', '제24조 제4항', '예산 범위에서 지급한다.'),
            ('edu-24-6', 'edu', '제24조 제6항', '별도 확인한다.'),
            ('work-24-1', 'work', '제24조 제1항', '다른 규정의 같은 번호다.'),
        ):
            self.articles[aid] = {'id': aid, 'reg': key, 'no': no, 'text': text, 'title': '',
                                  'chapter': '', 'type': 'paragraph', 'path': '',
                                  'group': '일반직', 'overseas': False}
        self.search.return_value = [{'id': 'edu-24-5'}, {'id': 'edu-9'}]
        with (patch.object(rt, '_log'), patch.object(rt, 'llm_json', return_value={
            'status': 'partial', 'summary': '지급기준은 따로 확인해야 해요.', 'sourceIds': ['S003'],
        }) as model):
            answer = reg.answer(self.ctx, '교육비 지원 신청 조건이 궁금해요', [], {}, documents_only=True)
        self.assertEqual(answer['retrieved'], ['edu-24-5', 'edu-9', 'edu-24-1', 'edu-24-4'])
        self.assertEqual(answer['basis'], ['edu-24-1'])
        self.assertEqual(answer['evidenceStatus'], 'partial')
        self.assertEqual(model.call_args.args[2]['sources'][2]['no'], '제24조 제1항')
        self.assertEqual(reg.regstore.referenced_paragraphs(['edu-24-5'], limit=1), ['edu-24-1'])

    def test_reference_follow_up_also_passes_summary_to_classifier(self):
        _, model, inp = self.ask('그 규정 제9조 내용을 알려줘')
        self.assertIn('인재개발규정 제7조', self.classify.call_args.args[0])
        self.assertIn('학습시간을 인정해요.', self.classify.call_args.args[0])
        self.assertTrue(inp['_classification']['usedHistory'])
        self.assert_summary_history(model)

    def test_hybrid_chatbot_supplies_sibling_context_with_original_citation_ids(self):
        def paragraph(identifier, number, text):
            return {'id': identifier, 'reg': 'edu', 'no': f'제24조 제{number}항', 'text': text,
                    'title': '', 'chapter': '', 'type': 'paragraph', 'path': '',
                    'parent': 'actual-article-node', 'order': number, 'group': '일반직', 'overseas': False}
        hit = paragraph('edu-24-2', 2, '교육비 지원은 승인된 과정에 적용한다.')
        sibling = paragraph('edu-24-1', 1, '승인 조건은 담당 부서에 확인한다.')
        self.articles.update({hit['id']: hit, sibling['id']: sibling})
        self.search.return_value = [{'id': hit['id']}, {'id': 'edu-9'}]
        with patch.object(reg.hybrid_search, 'enabled', return_value=True), patch.object(reg.regstore, 'pool', return_value=[hit, sibling]), patch.object(rt, '_log'), patch.object(rt, 'llm_json', return_value={'status': 'partial', 'summary': '승인 조건은 담당 부서에 확인해요.', 'sourceIds': ['S003']}) as model:
            answer = reg.answer(self.ctx, '교육비 지원 조건', [], {}, documents_only=True)
        self.assertEqual(answer['retrieved'], ['edu-24-2', 'edu-9', 'edu-24-1'])
        self.assertEqual(answer['basis'], ['edu-24-1'])
        self.assertEqual(model.call_args.args[2]['sources'][2]['no'], '제24조 제1항')

    def test_long_and_topic_keyword_follow_ups_use_summary_throughout_route(self):
        questions = ('그 규정에서 교육 신청을 취소하는 절차도 알려 주세요',
                     '앞에서 설명한 내용을 내 상황에 적용하면 어떻게 되나요?',
                     '온라인 교육도 교육비 지원을 받을 수 있나요?',
                     '근무시간에도 인정되나요?', '더 자세히 설명해 주세요')
        for question in questions:
            with self.subTest(question=question):
                self.search.reset_mock()
                _, model, inp = self.ask(question)
                self.assertTrue(inp['_classification']['usedHistory'])
                classified = self.classify.call_args.args[0]
                self.assertIn('인재개발규정', classified)
                self.assertIn('학습시간을 인정해요.', classified)
                self.assertIn(question, classified)
                self.assertEqual(self.search.call_count, 2)
                query = self.search.call_args.args[0]
                self.assertIn('인재개발규정', query)
                self.assertIn('학습시간을 인정해요.', query)
                self.assertIn(question, query)
                self.assert_summary_history(model)

    def test_third_question_keeps_root_and_answer_summaries_after_topic_change(self):
        unrelated = {'q': '취업규칙의 근무 기록 방법을 자세히 알려 주세요',
                     'a': {'summary': '관계없는 앞 주제', 'basis': ['work-9']}}
        second = {'q': '그 규정 제9조 내용을 알려줘',
                  'a': {'summary': '교육 신청은 교육포털에서 해요.', 'basis': ['edu-9']}}
        _, model, _ = self.ask('앞에서 설명한 내용을 내 상황에 적용하면 어떻게 되나요?',
                               history=[unrelated, *self.history, second])
        self.assertIn('인재개발규정', self.classify.call_args.args[0])
        self.assertIn(second['a']['summary'], self.classify.call_args.args[0])
        self.assertIn('인재개발규정', self.search.call_args.args[0])
        messages = model.call_args.kwargs['history']
        self.assertEqual(messages, [
            {'role': 'user', 'content': self.history[0]['q']},
            {'role': 'assistant', 'content': self.history[0]['a']['summary']},
            {'role': 'user', 'content': second['q']},
            {'role': 'assistant', 'content': second['a']['summary']},
        ])
        self.assertNotIn('관계없는 앞 주제', str(messages))
        self.assertNotIn('work-9', str(messages))

    def test_follow_up_passes_only_latest_five_turns_verbatim(self):
        repeated_answer = '앞서 안내한 교육 조건을 다시 확인해요.' * 6 + '\n원문 끝의 추가 조건도 확인해요.'
        history = [*self.history, *[
            {'q': f'그 내용의 후속 질문 {index}', 'a': {'summary': repeated_answer}}
            for index in range(6)]]
        original = copy.deepcopy(history)
        question = '그 내용을 더 설명해 주세요'
        _, model, _ = self.ask(question, history=history)
        expected = []
        for turn in history[-5:]:
            expected.extend(({'role': 'user', 'content': turn['q']},
                             {'role': 'assistant', 'content': repeated_answer}))
        self.assertEqual(model.call_args.kwargs['history'], expected)
        classified = self.classify.call_args.args[0]
        searched = self.search.call_args.args[0]
        self.assertTrue(classified.startswith(f'현재 질문: {question}'))
        self.assertLess(classified.index(history[-1]['q']), classified.index(history[-5]['q']))
        for query in (classified, searched):
            self.assertEqual(query.count(repeated_answer), 5)
            self.assertNotIn(history[0]['q'], query)
            self.assertNotIn(history[1]['q'], query)
        self.assertEqual(history, original)

    def test_explicit_topic_change_and_outside_question_do_not_use_old_summary(self):
        for question in ('다른 질문인데 연차휴가는 며칠인가요?', '오늘 날씨 알려줘'):
            with self.subTest(question=question):
                self.search.reset_mock()
                _, model, inp = self.ask(question)
                self.assertFalse(inp['_classification']['usedHistory'])
                self.assertEqual(self.classify.call_args.args[0], question)
                self.assertEqual(self.search.call_count, 1)
                self.assertEqual(model.call_args.kwargs['history'], [])

    def test_outside_classification_with_history_skips_search_and_llm(self):
        self.classify.return_value = {'label': '범위 밖'}
        result, model, inp = self.ask('그럼 오늘 날씨는 어때?')
        self.assertEqual(result['kind'], 'out')
        self.assertFalse(inp['_classification']['usedHistory'])
        self.search.assert_not_called()
        model.assert_not_called()

    def test_document_follow_ups_use_summary_for_classification_search_and_answer(self):
        cases = [
            (reg.knowledge.CATEGORY, 'search_company', '한국수자원공사는 어떤 일을 하는 기관인가요?',
             '수자원 관리와 수돗물 공급 업무를 해요.', '그 사업을 더 자세히 설명해 주세요', False),
            (reg.knowledge.LIFE_CATEGORY, 'search_life', '교육원 구내식당은 어디에 있나요?',
             '교육원 생활 안내의 구내식당 항목에서 위치를 확인해요.', '그 식당은 어떻게 찾아가나요?', True),
        ]
        for label, search_name, previous_question, summary, question, is_virtual in cases:
            with self.subTest(label=label):
                self.classify.return_value = {'label': label}
                history = [{'q': previous_question, 'a': {'summary': summary}}]
                hit = {'chunk_id': 'doc-1', 'document_id': 'doc', 'document_title': label,
                       'category': label, 'is_virtual': is_virtual, 'chunk_text': summary,
                       'chunk_text_sha256': 'a' * 64, 'metadata': {}}
                with patch.object(reg.knowledge, search_name, return_value=[hit]) as search:
                    _, model, inp = self.ask(question, history=history, summary=summary)
                self.assertTrue(inp['_classification']['usedHistory'])
                self.assertIn(summary, self.classify.call_args.args[0])
                self.assertIn(summary, search.call_args.args[0])
                self.assertEqual(model.call_args.kwargs['history'][1]['content'], summary)
                self.search.assert_not_called()

    def test_contextual_outside_follow_up_uses_summary_only_for_classification(self):
        self.classify.return_value = {'label': '범위 밖'}
        result, model, inp = self.ask('그 내용을 더 설명해 주세요')
        self.assertEqual(result['kind'], 'out')
        self.assertTrue(inp['_classification']['usedHistory'])
        self.assertIn(self.history[0]['a']['summary'], self.classify.call_args.args[0])
        self.search.assert_not_called()
        model.assert_not_called()

    def test_company_without_hits_keeps_summary_and_empty_sources(self):
        self.classify.return_value = {'label': '수자원공사 정보'}
        with patch.object(reg.knowledge, 'search_company', return_value=[]):
            _, model, _ = self.ask('그 내용을 더 설명해 주세요', status='not_found')
        self.assert_summary_history(model)
        self.assertEqual(model.call_args.args[2]['sources'], [])

    def test_life_menu_answer_can_be_summarized_without_model_raw_output(self):
        self.classify.return_value = {'label': '사내 생활안내'}
        menu = reg.D['intranet'][0]
        history = [{'q': '사내 공지사항은 어디서 볼 수 있나요?',
                    'a': {'summary': '', 'intranet': [menu['id']]}}]
        with patch.object(reg.knowledge, 'search_life', return_value=[]):
            _, model, _ = self.ask('그 메뉴에서 어떤 내용을 확인할 수 있나요?', history=history, status='not_found')
        summary = model.call_args.kwargs['history'][1]['content']
        self.assertIn(menu['menu'], summary)
        self.assertIn(menu['covers'], summary)
        self.assertNotIn(menu['id'], summary)
        self.search.assert_not_called()

    def test_explicit_other_regulation_does_not_inherit_previous_sources(self):
        result, model, _ = self.ask('취업규칙 제9조 내용을 자세히 알려 주세요')
        self.assertEqual(result['basis'], ['work-9'])
        self.assertNotIn('edu-7', result['retrieved'])
        self.assertEqual(model.call_args.kwargs['history'], [])

    def test_explicit_same_regulation_is_independent(self):
        result, model, _ = self.ask('인재개발규정 제9조 내용을 알려줘')
        self.assertEqual(result['basis'], ['edu-9'])
        self.assertNotIn('edu-7', result['retrieved'])
        self.assertEqual(model.call_args.kwargs['history'], [])

    def test_unrelated_question_does_not_inherit_regulation(self):
        result, model, _ = self.ask('취업규칙의 적용 범위를 자세히 알려 주세요')
        self.assertEqual(result['retrieved'], ['work-2'])
        self.assertNotIn('requested', model.call_args.args[2])
        self.assertEqual(model.call_args.kwargs['history'], [])

    def test_korean_particles_do_not_inherit_regulation(self):
        questions = ('자격증 취득비 지원 범위 기준이 뭐야?', '취업규칙에서 출장이 절차상 어떻게 처리돼?',
                     '연봉 인상률이 기준보다 높으면?', '복무규정상 재택근무도 신청 가능한가요?',
                     '여비규정에서 출장비 지급 기준이 어떻게 돼?')
        for question in questions:
            with self.subTest(question=question):
                self.search.reset_mock()
                result, model, inp = self.ask(question)
                self.assertFalse(inp['_classification']['usedHistory'])
                self.assertEqual(self.classify.call_args.args[0], question)
                self.search.assert_called_once()
                self.assertEqual(self.search.call_args.args[0], question)
                self.assertEqual(model.call_args.kwargs['history'], [])
                self.assertNotIn('edu-7', result['retrieved'])

    def test_no_previous_regulation_does_not_guess_article(self):
        for history in ([], [{'q': '다른 질문', 'a': {'summary': '앞 답변', 'basis': []}}],
                        [{'q': '다른 질문', 'a': {'summary': '앞 답변', 'basis': ['deleted-id']}}]):
            with self.subTest(history=history):
                _, model, _ = self.ask('그 규정 제9조 내용을 알려줘', history=history)
                self.assertNotIn('requested', model.call_args.args[2])
                self.assertNotIn('edu-9', str(model.call_args.args[2]['sources']))
                self.assertEqual(bool(model.call_args.kwargs['history']), bool(history))

    def test_unregistered_article_keeps_note_and_summary_history(self):
        result, model, _ = self.ask('그 규정 제99조 내용을 알려줘', status='not_found')
        self.assertEqual(result['evidenceStatus'], 'not_found')
        self.assertIn('인재개발규정', result['summary'])
        self.assertIn('제99조', result['summary'])
        self.assertIn('담당 부서에 문의', result['summary'])
        self.assertEqual(result['basis'], [])
        self.assertEqual(model.call_args.args[2]['sources'], [])
        self.assert_summary_history(model)

    def test_summary_history_excludes_old_shape_and_real_ids_without_mutation(self):
        original = copy.deepcopy(self.history)
        _, model, _ = self.ask('그럼 제9조는?')
        self.assert_summary_history(model)
        self.assertEqual(self.history, original)

    def test_history_without_summary_uses_empty_text(self):
        self.history[0]['a'].pop('summary')
        messages = reg._hist_msgs(self.history)
        self.assertEqual(messages[-1], {'role': 'assistant', 'content': ''})

    def test_old_real_citation_id_is_still_rejected(self):
        with self.assertRaisesRegex(LlmError, '출처'):
            self.ask('그럼 제9조는?', source_ids=['edu-7'])

    def test_new_topic_does_not_inherit_group_from_previous_question(self):
        history = [{'q': '실무직 교육비 지원 기준은?', 'a': {'summary': '실무직 기준 안내', 'basis': ['edu-7']}}]
        classified = reg.classify_question_roberta('다른 질문인데 연차휴가는 며칠인가요?', history, me={'empGroup': '일반직'})
        self.assertEqual(classified['group'], '일반직')
        self.assertFalse(classified['detectedFromQuestion'])
        self.assertEqual(classified['follow_history'], [])

    def test_follow_up_inherits_group_from_previous_question(self):
        history = [{'q': '실무직 교육비 지원 기준은?', 'a': {'summary': '실무직 기준 안내', 'basis': ['edu-7']}}]
        classified = reg.classify_question_roberta('그럼 지원 한도는 얼마야?', history, me={'empGroup': '일반직'})
        self.assertEqual(classified['group'], '실무직')
        self.assertTrue(classified['detectedFromQuestion'])
        self.assertEqual(len(classified['follow_history']), 1)


if __name__ == '__main__':
    unittest.main()

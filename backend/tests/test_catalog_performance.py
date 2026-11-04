"""색인 재사용·사전 로딩·로드맵 JSON 값 보존. 외부 모델과 DB 호출 없음."""
import copy
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

from app import catalog, catalog_budget as budget, catalog_candidates as candidates
from app.agents import runtime


def records():
    return {key: {'id': key, 'title': f'SQL {key}', 'skills': ['SQL'], 'provider': 'test',
                  'type': 'course', 'usable': True, 'cost': 0, 'hours': 2,
                  'content': '학습목표\nSQL 조회', 'curriculum': {'items': [{'title': 'SQL 조인 실습'}]}}
            for key in ('a', 'b')}


class IndexReuseTests(unittest.TestCase):
    def setUp(self):
        self.source = patch.object(candidates, '_source', None)
        self.index = patch.object(candidates, '_index', {})
        self.source.start()
        self.index.start()
        self.addCleanup(self.source.stop)
        self.addCleanup(self.index.stop)

    def test_unchanged_snapshot_reuses_normalization_and_keeps_both_record_snapshots(self):
        old = records()
        first = candidates.cached_index(old)
        updated = copy.deepcopy(old)
        with patch.object(candidates, 'learning_lines', wraps=candidates.learning_lines) as normalize:
            second = candidates.cached_index(updated)
        normalize.assert_not_called()
        self.assertIsNot(first, second)
        self.assertIs(first['a']['record'], old['a'])
        self.assertIs(second['a']['record'], updated['a'])
        self.assertIs(first['a']['rows'], second['a']['rows'])

    def test_changed_content_only_rebuilds_that_record_and_clears_its_profiles(self):
        old = records()
        first = candidates.cached_index(old)
        first['a']['query_profiles']['test'] = {'relatedUnits': 1}
        first['b']['query_profiles']['test'] = {'relatedUnits': 1}
        updated = copy.deepcopy(old)
        updated['a']['curriculum']['items'][0]['title'] = 'SQL 트랜잭션 검증'
        with patch.object(candidates, 'learning_lines', wraps=candidates.learning_lines) as normalize:
            second = candidates.cached_index(updated)
        self.assertEqual(normalize.call_count, 1)
        self.assertIn('트랜잭션', second['a']['rows'][0][1])
        self.assertEqual(second['a']['query_profiles'], {})
        self.assertIs(first['b']['query_profiles'], second['b']['query_profiles'])
        self.assertIn('조인', first['a']['rows'][0][1])

    def test_metadata_changes_are_visible_without_modifying_an_active_old_request(self):
        old = records()
        first = candidates.cached_index(old)
        updated = copy.deepcopy(old)
        updated['a'].update(cost=100, hours=7, usable=False, skills=['Python'], title='새 자료명')
        second = candidates.cached_index(updated)
        self.assertEqual(second['a']['record']['cost'], 100)
        self.assertEqual(second['a']['record']['hours'], 7)
        self.assertFalse(second['a']['record']['usable'])
        self.assertEqual(second['a']['skills'], {'Python'})
        self.assertEqual(first['a']['record']['cost'], 0)
        self.assertTrue(first['a']['record']['usable'])

    def test_removed_and_added_resources_do_not_leak_between_snapshots(self):
        old = records()
        first = candidates.cached_index(old)
        updated = {'b': copy.deepcopy(old['b']), 'c': dict(old['a'], id='c')}
        second = candidates.cached_index(updated)
        self.assertEqual(set(second), {'b', 'c'})
        self.assertEqual(set(first), {'a', 'b'})
        self.assertIs(first['b']['rows'], second['b']['rows'])

    def test_parallel_refreshes_reuse_normalization_with_isolated_record_references(self):
        old = records()
        first = candidates.cached_index(old)
        snapshots = [copy.deepcopy(old) for _ in range(4)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            indexes = list(pool.map(candidates.cached_index, snapshots))
        for snapshot, index in zip(snapshots, indexes):
            self.assertIs(index['a']['record'], snapshot['a'])
            self.assertIs(index['a']['rows'], first['a']['rows'])


class WarmupTests(unittest.TestCase):
    def test_warmup_prepares_catalog_index_and_tokenizer_without_model_calls(self):
        data = records()
        order = []
        with patch.object(catalog, 'items', side_effect=lambda: order.append('catalog') or data), \
                patch.object(candidates, 'cached_index', side_effect=lambda value: order.append('index')) as index, \
                patch.object(budget, 'tokens', side_effect=lambda value: order.append('tokenizer') or 0), \
                patch.object(runtime.llm, 'chat') as model:
            catalog.warmup_roadmap()
        self.assertEqual(order, ['catalog', 'index', 'tokenizer'])
        index.assert_called_once_with(data)
        model.assert_not_called()


class LifespanWarmupTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_prepares_before_yielding_and_runs_work_off_event_loop(self):
        from app import main
        loop_thread = threading.get_ident()
        threads = []
        with patch.object(main.jobs, 'mark_lost', return_value=0), \
                patch.object(catalog, 'warmup_roadmap', side_effect=lambda: threads.append(threading.get_ident())):
            async with main.lifespan(main.app):
                self.assertEqual(len(threads), 1)
                self.assertNotEqual(threads[0], loop_thread)

    async def test_failed_optional_warmup_is_logged_and_does_not_hide_error(self):
        from app import main
        with patch.object(main.jobs, 'mark_lost', return_value=0), \
                patch.object(catalog, 'warmup_roadmap', side_effect=ValueError('검증 파일 누락')), \
                self.assertLogs(main.logger, level='ERROR') as log:
            async with main.lifespan(main.app):
                pass
        self.assertIn('사전 로딩 실패', log.output[0])
        self.assertIn('검증 파일 누락', log.output[0])


class CompactRoadmapInputTests(unittest.TestCase):
    def test_resource_catalog_compaction_preserves_book_keys_and_string_spaces(self):
        data = {'skills': [{'name': 'RAG', 'books': [{'choiceKey': 'B1'}]}],
                'bookCatalog': [{'choiceKey': 'B1', 'content': '공백  두 개 유지', 'cost': None}]}
        ctx = SimpleNamespace(mode='openai', reasoning={}, meta={})
        with patch.object(runtime.llm, 'chat', return_value={'content': '{}'}) as model:
            runtime.llm_json(ctx, '자료 후보 규칙', data, role='resources')
        wire = model.call_args.args[1][-1]['content']
        self.assertEqual(json.loads(wire), data)
        self.assertIn('공백  두 개 유지', wire)
        self.assertLess(len(wire), len(json.dumps(data, ensure_ascii=False)))
        self.assertEqual(model.call_args.kwargs['role'], 'resources')

    def test_roadmap_compacts_json_without_changing_values_strings_or_message_contract(self):
        data = {'goal': '공백  두 개와 줄바꿈\n유지', 'catalog': [{'id': 'a', 'cost': None, 'hours': 1.5}],
                'quote': '"인용" · 한국어', 'selected': True}
        ctx = SimpleNamespace(mode='openai', reasoning={'openai': 'high'}, meta={})
        history = [{'role': 'assistant', 'content': '이전 내용'}]
        with patch.object(runtime.llm, 'chat', return_value={'content': '{"ok":true}', 'loadMs': 3}) as chat:
            self.assertEqual(runtime.llm_json(ctx, 'DB prompt', data, role='roadmap', history=history), {'ok': True})
        args, kwargs = chat.call_args
        self.assertEqual(args[1][:2], [{'role': 'system', 'content': 'DB prompt'}] + history)
        message = args[1][-1]['content']
        self.assertEqual(json.loads(message), data)
        self.assertEqual(list(json.loads(message)), list(data))
        self.assertLess(len(message), len(json.dumps(data, ensure_ascii=False)))
        self.assertEqual(kwargs['role'], 'roadmap')
        self.assertEqual(kwargs['reasoning'], 'high')
        self.assertEqual(ctx.meta, {'loadMs': 3})

    def test_other_agents_keep_existing_serialization(self):
        ctx = SimpleNamespace(mode='ollama', reasoning={}, meta={})
        data = {'goal': '문서 검색', 'values': [1, 2]}
        with patch.object(runtime.llm, 'chat', return_value={'content': '{}'}) as chat:
            runtime.llm_json(ctx, 'DB prompt', data, role='regulation')
        self.assertEqual(chat.call_args.args[1][-1]['content'], json.dumps(data, ensure_ascii=False, default=str))


if __name__ == '__main__':
    unittest.main()

"""Execution defaults and committed-reset reports; all external clients are mocked."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import load_data
from src.database.ingestion.real_data_ingestor import RealDataIngestor, PipelineExecutionError
from src.database.local_runtime import DATA
from tests.test_ai_catalog_filter import SKILLS, client, row


class IngestionExecutionTests(unittest.TestCase):
    def setUp(self):
        self.ing = RealDataIngestor(config={'ingestion': {}}, ai_client=client())
        context = MagicMock()
        context.__enter__.return_value.info.host = '127.0.0.1'
        context.__enter__.return_value.execute.return_value.fetchall.return_value = SKILLS
        self.conn = context.__enter__.return_value
        self.enterContext(patch('src.database.deployment.connect', return_value=context))
        self.enterContext(patch('src.database.local_runtime.server_data_directory', return_value=DATA))
        self.backup = self.enterContext(patch('src.database.local_runtime.backup', return_value={'backup': 'mock-reset.dump'}))
        self.reset = self.enterContext(patch('src.database.catalog_reset.reset_skill_catalogs',
            return_value={'deleted': {'courses': 1}, 'removed_resource_associations': 2}))
        self.batch = {'rows': {}, 'sources': {}, 'failures': {}, 'collection_complete': True,
                      'unresolved_rule_names': []}
        self.collect = self.enterContext(patch.object(self.ing, 'collect', return_value=self.batch))
        self.apply = self.enterContext(patch.object(self.ing, 'apply', return_value={
            'status': 'SUCCESS', 'tables': {}, 'database_changes': True, 'user_data_changed': False}))

    def test_default_and_legacy_entry_point_do_not_reset(self):
        for execute in (self.ing.execute_full_pipeline, self.ing.ingest_and_map_all):
            result = execute()
            self.assertEqual(result['status'], 'SUCCESS')
            self.assertFalse(result['user_data_changed'])
            self.assertNotIn('reset', result)
        self.backup.assert_not_called()
        self.reset.assert_not_called()

    def test_default_collection_failure_does_not_change_data(self):
        self.batch['failures'] = {'books': 'FAILED'}
        result = self.ing.execute_full_pipeline()
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['database_changes'])
        self.assertFalse(result['user_data_changed'])
        self.backup.assert_not_called()
        self.reset.assert_not_called()
        self.apply.assert_not_called()

    def test_reset_success_reports_both_zero_and_nonzero_detachments(self):
        for removed in (0, 2):
            with self.subTest(removed=removed):
                self.reset.return_value['removed_resource_associations'] = removed
                result = self.ing.execute_full_pipeline(reset_catalog=True)
                self.assertEqual(result['user_data_changed'], removed > 0)
                self.assertTrue(result['database_changes'])
                self.assertEqual(result['reset']['removed_resource_associations'], removed)
                self.assertEqual(result['backup'], 'mock-reset.dump')

    def test_reset_collection_failure_keeps_committed_details(self):
        self.batch['failures'] = {'books': 'FAILED'}
        for removed in (0, 2):
            with self.subTest(removed=removed):
                self.reset.return_value['removed_resource_associations'] = removed
                result = self.ing.execute_full_pipeline(reset_catalog=True)
                self.assertEqual(result['status'], 'FAILED')
                self.assertEqual(result['user_data_changed'], removed > 0)
                self.assertTrue(result['database_changes'])
                self.assertEqual(result['reset']['removed_resource_associations'], removed)
                self.assertEqual(result['backup'], 'mock-reset.dump')
        self.apply.assert_not_called()

    def test_exception_after_reset_retains_context_without_exposing_error_text(self):
        for failing in (self.collect, self.apply):
            with self.subTest(stage='collect' if failing is self.collect else 'apply'):
                failing.side_effect = RuntimeError('PRIVATE_EXCEPTION_TEXT')
                with self.assertRaises(PipelineExecutionError) as caught:
                    self.ing.execute_full_pipeline(reset_catalog=True)
                report = caught.exception.report
                self.assertTrue(report['user_data_changed'])
                self.assertTrue(report['database_changes'])
                self.assertEqual(report['backup'], 'mock-reset.dump')
                self.assertEqual(report['reset']['removed_resource_associations'], 2)
                self.assertNotIn('PRIVATE_EXCEPTION_TEXT', json.dumps(report))
                failing.side_effect = None

    def test_exception_without_reset_preserves_the_original_exception_contract(self):
        self.collect.side_effect = RuntimeError('collection failure')
        with self.assertRaisesRegex(RuntimeError, '^collection failure$'):
            self.ing.execute_full_pipeline()
        self.backup.assert_not_called()
        self.reset.assert_not_called()

    def test_dry_run_still_screens_with_ai_but_never_resets_or_applies(self):
        # Use real collection/admission with a mock GPT client to distinguish
        # "no DB writes" from "no API calls" even when --reset is also selected.
        with patch.object(self.ing, 'collect', wraps=RealDataIngestor.collect.__get__(self.ing)), \
             patch('src.database.ingestion.real_data_ingestor.KINDS', ('books',)), \
             patch.object(self.ing, 'fetch_books_from_api', return_value=[row()]), \
             patch('src.database.ingestion.catalog_details.finalize', side_effect=lambda _, kind, rows: rows):
            result = self.ing.execute_full_pipeline(dry_run=True, reset_catalog=True)
        self.assertEqual(self.ing.ai_client.chat.completions.create.call_count, 1)
        self.assertFalse(result['database_changes'])
        self.assertFalse(result['user_data_changed'])
        self.assertFalse(result['embedding_api_called'])
        self.backup.assert_not_called()
        self.reset.assert_not_called()
        self.apply.assert_not_called()

    def test_default_run_still_collects_every_catalog(self):
        result = self.ing.execute_full_pipeline()
        self.assertIsNone(self.collect.call_args.kwargs['kinds'])
        self.assertEqual(self.collect.call_args.kwargs['skip_isbns'], frozenset())
        self.assertEqual(result['collection_scope'], 'all_catalogs')
        self.assertFalse(any('public.books' in call.args[0] for call in self.conn.execute.call_args_list))

    def test_only_new_books_collects_books_without_saved_isbns(self):
        def query(sql, *args):
            result = MagicMock()
            result.fetchall.return_value = [{'isbn': '9788900000001'}] if 'public.books' in sql else SKILLS
            return result
        self.conn.execute.side_effect = query
        result = self.ing.execute_full_pipeline(only_new_books=True)
        self.assertEqual(self.collect.call_args.kwargs['kinds'], ('books',))
        self.assertEqual(self.collect.call_args.kwargs['skip_isbns'], frozenset({'9788900000001'}))
        self.assertEqual(result['collection_scope'], 'new_books_only')
        self.apply.assert_called_once()
        self.backup.assert_not_called()
        self.reset.assert_not_called()

    def test_only_new_books_rejects_reset_before_any_change(self):
        with self.assertRaisesRegex(ValueError, '--reset'):
            self.ing.execute_full_pipeline(only_new_books=True, reset_catalog=True)
        self.conn.execute.assert_not_called()
        for step in (self.backup, self.reset, self.collect, self.apply):
            step.assert_not_called()


class NarrowedCatalogTests(unittest.TestCase):
    def test_books_only_collection_never_calls_other_sources(self):
        ing = RealDataIngestor(config={'ingestion': {}}, ai_client=client())
        others = {kind: self.enterContext(patch.object(ing, f'fetch_{kind}_from_api'))
                  for kind in ('courses', 'certifications', 'jobs', 'majors')}
        books = self.enterContext(patch.object(ing, 'fetch_books_from_api', return_value=[row()]))
        self.enterContext(patch('src.database.ingestion.catalog_details.finalize',
                                side_effect=lambda _, kind, rows: rows))
        batch = ing.collect(SKILLS, kinds=('books',), skip_isbns=frozenset({'9788900000001'}))
        self.assertEqual(set(batch['rows']), {'books'})
        self.assertEqual(len(batch['rows']['books']), 1)
        self.assertEqual(books.call_args.kwargs['skip_isbns'], frozenset({'9788900000001'}))
        for fetch in others.values():
            fetch.assert_not_called()
        with self.assertRaises(ValueError):
            ing.collect(SKILLS, kinds=('videos',))

    def test_books_only_batch_writes_books_and_leaves_other_catalogs_untouched(self):
        ing = RealDataIngestor(config={'ingestion': {}}, ai_client=client())
        statements = []

        class Connection:
            @contextmanager
            def transaction(self):
                yield

            def execute(self, sql, params=None):
                statements.append(sql)
                result = MagicMock()
                result.fetchall.return_value = SKILLS if 'public.skill_tags' in sql else []
                result.fetchone.return_value = {'id': 'present'} if 'to_regclass' in sql else None
                return result

        validation = {'removed_rows': {'removed_resource_associations': 0}}
        with patch('src.database.ingestion.catalog_finalization.finalize_catalog', return_value=({}, validation)):
            result = ing.apply(Connection(), {'failures': {}, 'rows': {'books': [row()]},
                                              'skill_identity': SKILLS, 'sources': {}})
        self.assertEqual(set(result['tables']), {'books'})
        self.assertEqual(result['tables']['books']['inserted'], 1)
        writes = [s for s in statements if s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'LOCK'))]
        self.assertTrue(any('public.books' in s for s in writes))
        for other in ('courses', 'certifications', 'jobs', 'majors'):
            with self.subTest(catalog=other):
                self.assertFalse(any(f'public.{other}' in s for s in writes))


class IngestionCliTests(unittest.TestCase):
    def test_only_new_books_flag_reaches_pipeline_and_rejects_conflicts(self):
        for suffix, expected in (([], False), (['--only-new-books', '--dry-run'], True)):
            with self.subTest(args=suffix), patch.object(sys, 'argv', ['load_data.py'] + suffix), \
                 patch.object(load_data, 'RealDataIngestor') as constructor, redirect_stdout(StringIO()):
                constructor.return_value.execute_full_pipeline.return_value = {'status': 'READY'}
                self.assertEqual(load_data.main(), 0)
                kwargs = constructor.return_value.execute_full_pipeline.call_args.kwargs
                self.assertEqual(kwargs['only_new_books'], expected)
                self.assertFalse(kwargs['reset_catalog'])
        for suffix in (['--only-new-books', '--reset'], ['--only-new-books', '--refresh-book-images']):
            with self.subTest(args=suffix), patch.object(sys, 'argv', ['load_data.py'] + suffix), \
                 patch.object(load_data, 'RealDataIngestor') as constructor, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    load_data.main()
                self.assertEqual(caught.exception.code, 2)
                constructor.assert_not_called()

    def test_default_incremental_alias_and_explicit_reset(self):
        for suffix, expected in (([], False), (['--incremental'], False), (['--reset'], True)):
            with self.subTest(args=suffix), patch.object(sys, 'argv', ['load_data.py'] + suffix), \
                 patch.object(load_data, 'RealDataIngestor') as constructor, redirect_stdout(StringIO()):
                constructor.return_value.execute_full_pipeline.return_value = {'status': 'SUCCESS'}
                self.assertEqual(load_data.main(), 0)
                self.assertEqual(constructor.return_value.execute_full_pipeline.call_args.kwargs['reset_catalog'], expected)

    def test_conflicting_modes_fail_before_instantiating_ingestion(self):
        for suffix in (['--reset', '--incremental'], ['--reset', '--refresh-book-images']):
            with self.subTest(args=suffix), patch.object(sys, 'argv', ['load_data.py'] + suffix), \
                 patch.object(load_data, 'RealDataIngestor') as constructor, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    load_data.main()
                self.assertEqual(caught.exception.code, 2)
                constructor.assert_not_called()

    def test_cli_writes_the_committed_reset_failure_report(self):
        report = {'status': 'FAILED', 'message': '초기화 후 실패', 'database_changes': True,
                  'user_data_changed': True, 'backup': 'mock-reset.dump',
                  'reset': {'removed_resource_associations': 2}}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            destination = Path(folder) / 'report.json'
            output = StringIO()
            with patch.object(sys, 'argv', ['load_data.py', '--reset', '--report', str(destination)]), \
                 patch.object(load_data, 'RealDataIngestor') as constructor, redirect_stdout(output):
                constructor.return_value.execute_full_pipeline.side_effect = PipelineExecutionError(report)
                self.assertEqual(load_data.main(), 2)
            self.assertEqual(json.loads(destination.read_text(encoding='utf-8')), report)
            self.assertEqual(json.loads(output.getvalue()), report)

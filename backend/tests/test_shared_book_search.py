"""같은 초안에서 세 코스가 공유하는 도서 검색과 코스별 최종 선택."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from threading import Barrier, Lock
from unittest import TestCase
from unittest.mock import Mock, patch

from app.agents.resource_recommendations import recommend_from_catalog
from app.errors import ApiError
from app.services import draft_book_search, resource_rag


class DraftCache:
    def __init__(self):
        self.entries = {}
        self.lock = Lock()

    @contextmanager
    def tx(self):
        with self.lock:
            yield self

    def one(self, sql, *, e, p, g, skill):
        if (e, p, g) == (1, 'draft', 'generation'):
            return {'entry': self.entries.get(skill)}

    def run(self, sql, *, entry, p):
        self.entries.update(entry.obj)

    def all(self, sql, **params):
        raise AssertionError('이 검사에서는 벡터 DB 응답을 대체한다.')


class SharedBookTests(TestCase):
    def test_three_concurrent_courses_share_search_catalog_and_keys_but_choose_separately(self):
        cache = DraftCache()
        resource_rag.cached_vectors.cache_clear()
        self.addCleanup(resource_rag.cached_vectors.cache_clear)
        skills = ['SQL', 'Python']
        items = {}
        for name, count in zip(skills, [40, 2]):
            for i in range(count):
                key = f'book_{name}-{i:02d}'
                items[key] = dict(id=key, type='book', usable=True, title=f'{name} {i}',
                                  content='목표 관련 소개', skills=[name], cost=i+1)
        calls = {}
        start = Barrier(3)

        def embedding(texts):
            self.assertEqual(len(texts), 2)
            self.assertFalse(any('코스 전용' in text for text in texts))
            return [[1.] * resource_rag.DIMENSIONS for _ in texts]

        def matches(kind, ids, vector, limit, free_only, *, read):
            return [dict(resource_id=key, similarity=0.8) for key in sorted(ids)[:limit]]

        def choose(ctx, system, payload, **kwargs):
            code = payload['course']['id']
            index = int(code[-1]) - 1
            self.assertIn('코스 전용', payload['course']['learningSkills'][0]['targetOutcome'])
            calls[code] = (payload['bookCatalog'], {r['name']: r['books'] for r in payload['skills']})
            return {'skills': [dict(name=r['name'], courses=[],
                                    books=[{'key': r['books'][index % len(r['books'])]['choiceKey']}])
                               for r in payload['skills']]}

        def recommend(code):
            order = list(reversed(skills)) if code == 'A2' else skills
            targets = [dict(name=name, application=f'{code} 코스 전용 적용',
                            targetOutcome=f'{code} 코스 전용 결과') for name in order]
            pre = {'project': {'goal': '조회 작업', 'selectedSkills': [{'name': n} for n in skills]},
                   'selection': {'skills': targets}, '_commonApplications': {'SQL': '쿼리', 'Python': '집계'}}
            start.wait(timeout=5)
            result = recommend_from_catalog(Mock(live=True), pre, {'id': code, 'learningSkills': targets},
                                            book_search=partial(draft_book_search.search, 1, 'draft', 'generation'))
            for row in result['skills']:
                self.assertEqual(row['modelBookCounts'], {'candidates': len(calls[code][1][row['name']]), 'recommended': 1})
            return next(r['books'][0]['id'] for r in result['skills'] if r['name'] == 'SQL')

        with patch('app.catalog.items', return_value=items), patch.object(draft_book_search.db, 'tx', cache.tx), \
                patch.object(resource_rag.embeddings, 'embed', side_effect=embedding) as embed, \
                patch.object(resource_rag, 'search_vectors', side_effect=matches) as search, \
                patch('app.agents.runtime.llm_json', side_effect=choose), ThreadPoolExecutor(max_workers=3) as pool:
            picks = list(pool.map(recommend, ['A1', 'A2', 'A3']))
        self.assertEqual(search.call_count, 2)
        embed.assert_called_once()
        self.assertEqual(calls['A1'], calls['A2'])
        self.assertEqual(calls['A1'], calls['A3'])
        catalog, allowed = calls['A1']
        self.assertEqual(len(catalog), 30)
        self.assertEqual(len(allowed['Python']), 2)
        self.assertEqual(len(set(picks)), 3)

    def test_retry_new_query_and_changed_eligibility(self):
        cache = DraftCache()
        find = partial(draft_book_search.search, 1, 'draft', 'generation', 'SQL')
        row = dict(resource_id='a', similarity=.9)
        with patch.object(draft_book_search.db, 'tx', cache.tx), \
                patch.object(resource_rag, 'search_vectors', side_effect=[RuntimeError(), [], [row], [row], [row]]) as db_search:
            with self.assertRaises(RuntimeError):
                find('기본', ['a', 'b'], (), 30)
            self.assertEqual(find('기본', ['a', 'b'], (), 30), [])
            self.assertFalse(cache.entries)
            self.assertEqual(find('기본', ['a', 'b'], (), 30), [row])
            self.assertEqual(find('기본', ['b', 'a'], (), 30), [row])
            find('새 목표', ['a', 'b'], (), 30)
            find('새 목표', ['a'], (), 30)
            self.assertEqual(db_search.call_count, 5)
            with self.assertRaises(ApiError):
                draft_book_search.search(2, 'draft', 'generation', 'SQL', '새 목표', ['a'], (), 30)

from unittest import TestCase
from unittest.mock import patch

from app import catalog


def resource(key, title, *, kind='course', provider='기관', site='K-MOOC', stage=2, usable=True):
    return {'id': key, 'title': title, 'type': kind, 'kind': catalog.KIND[kind], 'provider': provider,
            'platform': site if kind == 'course' else None, 'stage': stage, 'skills': [], 'usable': usable}


class ResourceBrowsingTests(TestCase):
    def setUp(self):
        rows = [resource(str(i), f'강좌 {i:02d}') for i in range(65, 0, -1)]
        rows.extend([
            resource('duplicate', '강좌 01', stage=3),
            resource('other', '강좌 01', provider='다른 기관', site='Inflearn'),
            resource('same-provider', '강좌 02', site='Inflearn', stage=3),
            resource('hidden', '제외 강좌', site='미공개', usable=False),
            resource('cert-test', '자격 시험', kind='cert'),
            resource('book-test', '도서', kind='book'),
        ])
        self.snapshot = {r['id']: r for r in rows}
        self.enterContext(patch.object(catalog, '_search_items', return_value=self.snapshot))

    def test_global_order_across_pages_and_duplicate_representative(self):
        for sort in ('default', 'title_asc', 'title_desc'):
            with self.subTest(sort=sort):
                pages = [catalog.search(kind='강좌', sort=sort, offset=offset) for offset in (0, 30, 60)]
                self.assertEqual([len(p['items']) for p in pages], [30, 30, 6])
                self.assertTrue(all(p['total'] == 66 for p in pages))
                items = [item for page in pages for item in page['items']]
                ids = [item['id'] for item in items]
                self.assertEqual(len(set(ids)), 66)
                self.assertIn('1', ids)
                self.assertNotIn('duplicate', ids)
                if sort != 'default':
                    keys = [(item['title'], item['id']) for item in items]
                    self.assertEqual(keys, sorted(keys, reverse=sort == 'title_desc'))
                self.assertEqual(catalog.search(kind='강좌', sort=sort, offset=90)['items'], [])

    def test_sites_are_complete_and_filter_before_deduplication(self):
        result = catalog.search(kind='강좌', q='강좌', platform='Inflearn', sort='title_asc')
        self.assertEqual([r['id'] for r in result['items']], ['other', 'same-provider'])
        self.assertEqual(result['total'], 2)
        empty = catalog.search(kind='강좌', q='없는자료', platform='K-MOOC')
        self.assertEqual(empty, {'items': [], 'total': 0, 'platforms': ['Inflearn', 'K-MOOC']})

    def test_legacy_picker_and_certificate_kind(self):
        self.assertEqual([r['id'] for r in catalog.search(kind='자격')['items']], ['cert-test'])
        result = catalog.search('', '강좌', 3, ['duplicate'], 12, 0, False)
        self.assertEqual([r['id'] for r in result['items']], ['same-provider'])
        self.assertNotIn('platforms', result)

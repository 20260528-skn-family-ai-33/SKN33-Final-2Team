from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from app import catalog
from app.services import course_recommendations, plans


class BookPageLinkTests(TestCase):
    def setUp(self):
        self.key = 'book_9788909084048'
        self.api = 'https://data4library.kr/api/srchDtlList?isbn13=9788909084048'
        self.page = 'https://data4library.kr/bookV?seq=2251002'
        self.items = {self.key: {'id': self.key, 'type': 'book', 'usable': True, 'url': self.page}}
        self.old = {'id': self.key, 'url': self.api, 'why': '네트워크 실습', 'cost': 12000}

    def test_draft_reuses_selection_and_replaces_only_the_click_target(self):
        saved = {'skills': [{'name': 'TCP/IP', 'courses': [], 'books': [self.old], 'selectedBooks': [self.key]}]}
        with patch.object(catalog, 'items', return_value=self.items):
            row = course_recommendations.available_recommendations(saved, 'A3')['skills'][0]
        self.assertEqual(row['books'], [dict(self.old, url=self.page)])
        self.assertEqual(row['selectedBooks'], [self.key])
        self.assertEqual(self.old['url'], self.api)

    def test_preserves_bookstore_links_and_omits_an_unresolvable_api_url(self):
        store = dict(self.old, url='https://example.org/books/a')
        self.assertEqual(catalog.refresh_book_links([store, self.old], {}),
                         [store, dict(self.old, url='')])

    def test_confirmed_plan_and_previous_version_return_public_link_without_rewriting_snapshots(self):
        report = {'recommendations': {'skills': [{'name': 'TCP/IP', 'books': [self.old], 'courses': []}]}}
        saved_plan = {'def': {'learningReport': report}}
        old_version = deepcopy(saved_plan)
        row = {'roadmap_id': 'roadmap', 'content': saved_plan, 'status': 'IN_PROGRESS',
               'created_at': None, 'done_at': None, 'archived_at': None, 'resumed_at': None}
        with patch.object(plans.db, 'all_', side_effect=[[{'plan': old_version}], []]), \
             patch.object(plans, '_comments', return_value=[]), patch.object(catalog, 'items', return_value=self.items):
            result = plans.record(row, for_mgr=True)
        def book(plan):
            return plan['def']['learningReport']['recommendations']['skills'][0]['books'][0]
        self.assertEqual(book(result['plan'])['url'], self.page)
        self.assertEqual(book(result['versions'][0])['url'], self.page)
        self.assertEqual(book(saved_plan)['url'], self.api)
        self.assertEqual(book(old_version)['url'], self.api)

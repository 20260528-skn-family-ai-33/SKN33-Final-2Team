import json
from contextlib import nullcontext
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import Account, require_employee
from app.routers import preassessment as api
from app.services import drafts
from app.services.resource_rag import version_for
from test_preassessment_api import api_app


class CachedResourceAvailabilityTests(TestCase):
    def setUp(self):
        self.pid, self.gid, self.rid = (str(uuid4()) for _ in range(3))
        self.url = f'/api/v2/drafts/{self.pid}/recommendations'
        self.project = {'goal': 'SQL 조인'}
        self.me = {}
        self.choices = {'SQL': {'course': 'course', 'books': ['book'], 'enabled': True}}
        self.items = {
            rid: {'id': rid, 'type': kind, 'title': rid, 'usable': True, 'cost': cost, 'hours': 2}
            for rid, kind, cost in (
                ('course', 'course', 0), ('alt-course', 'course', 0),
                ('book', 'book', 100), ('alt-book', 'book', None),
            )
        }
        self.fresh_items = deepcopy(self.items)
        self.rec = {
            'id': self.rid, 'retrieval': {'version': version_for('A3')},
            'skills': [{'name': 'SQL', 'courses': [self.items['course'], self.items['alt-course']],
                        'books': [self.items['book'], self.items['alt-book']],
                        'selectedCourse': 'alt-course', 'selectedBooks': ['alt-book', 'book']}],
        }
        self.cache = {'recommendations': self.rec, 'resourceChoices': self.choices}
        self.saved = {
            'version': 1, 'generationId': self.gid, 'completed': True,
            'project': self.project, 'profile': api.profile_input(self.me),
            'selection': {'skills': [{'name': 'SQL'}]}, 'skillOrder': ['SQL'],
            'resourceChoices': self.choices, 'courseRecommendations': {'A3': self.cache, 'A1': self.cache},
        }
        self.draft = {'chosen': 'A3', 'gen': {'options': {'A3': {}, 'A1': {}}}}
        self.raw = {'v2Survey': self.saved, 'draft': self.draft}
        self.tx = Mock()
        self.tx.all.return_value = []
        self.tx.one.return_value = {'draft_choices': self.raw}
        self.tx.run.return_value = 1
        self.client = TestClient(api_app)
        self.addCleanup(self.client.close)
        self.enterContext(patch.dict(api_app.dependency_overrides, {require_employee: lambda: Account('employee', 1, '')}))
        self.enterContext(patch.object(api.db, 'tx', side_effect=lambda: nullcontext(self.tx)))
        self.enterContext(patch.object(drafts, '_row', return_value={'draft_choices': self.raw}))
        self.enterContext(patch.object(api, 'project_input', return_value=self.project))
        self.enterContext(patch.object(api.profile, 'view', return_value=self.me))
        self.lookup = self.enterContext(patch('app.catalog.items', side_effect=self.catalog_items))
        self.generate = self.enterContext(patch.object(api, 'recommend_from_catalog', side_effect=AssertionError('unexpected generation')))

    def catalog_items(self, refresh=False):
        return self.fresh_items if refresh else self.items

    def put(self, *, course_id='course', books=None, track='A3'):
        return self.client.put(f'{self.url}/choices', params={'course': track}, json={
            'generationId': self.gid, 'recommendationId': self.rid,
            'choices': {'SQL': {'course': course_id, 'books': books if books is not None else ['book'], 'enabled': True}},
        })

    def test_cache_filters_alternatives_and_defaults_without_regenerating_or_writing(self):
        del self.items['alt-course']
        self.items['alt-book'] = {'id': 'alt-book', 'type': 'course', 'usable': True}
        self.rec['retrieval']['version'] = 'old'
        before = deepcopy(self.raw)
        self.enterContext(patch.object(api, 'generation_guard', return_value=nullcontext()))
        self.enterContext(patch.object(api, 'course_input', return_value={'id': 'A3'}))
        for request in (self.client.get, self.client.post):
            response = request(self.url, params={'course': 'A3'})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result['recommendations']['id'], self.rid)
            self.assertTrue(result['recommendations']['outdated'])
            self.assertEqual(result['choices'], self.choices)
            row = result['recommendations']['skills'][0]
            self.assertEqual([item['id'] for item in row['courses']], ['course'])
            self.assertEqual([item['id'] for item in row['books']], ['book'])
            self.assertIsNone(row['selectedCourse'])
            self.assertEqual(row['selectedBooks'], ['book'])
        self.assertEqual(self.raw, before)
        self.generate.assert_not_called()
        self.tx.run.assert_not_called()

    def test_valid_change_saves_through_store_with_fresh_catalog(self):
        response = self.put(course_id='alt-course', books=['alt-book'])
        self.assertEqual(response.status_code, 200, response.text)
        self.lookup.assert_any_call(refresh=True)
        self.tx.run.assert_called_once()
        stored = json.loads(self.tx.run.call_args.kwargs['value'])
        self.assertEqual(stored['courseRecommendations']['A3']['resourceChoices'], response.json()['choices'])
        self.assertEqual(stored['courseRecommendations']['A1']['resourceChoices'], self.choices)

    def test_completion_after_cache_hides_course_and_rejects_old_selection(self):
        self.tx.all.return_value = [{'course_id': 'alt-course'}]
        response = self.client.get(self.url, params={'course': 'A3'})
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()['recommendations']['skills'][0]
        self.assertEqual([c['id'] for c in row['courses']], ['course'])
        self.assertEqual(response.json()['choices'], self.choices)
        self.assertIsNone(row['selectedCourse'])
        self.assertEqual(self.put(course_id='alt-course').status_code, 422)
        self.tx.run.assert_not_called()

    def test_completion_after_initial_check_is_rechecked_on_save(self):
        self.tx.all.side_effect = [[], [{'course_id': 'course'}]]
        self.assertEqual(self.put().status_code, 422)
        self.tx.run.assert_not_called()

    def test_cached_selected_completed_course_requires_new_candidates(self):
        self.tx.all.return_value = [{'course_id': 'course'}]
        response = self.client.get(self.url, params={'course': 'A3'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()['recommendations'])
        self.assertEqual(self.put().status_code, 409)
        self.tx.run.assert_not_called()

    def test_course_completed_while_model_runs_is_not_saved(self):
        self.cache.pop('recommendations')
        self.tx.all.side_effect = [[], [{'course_id': 'course'}]]
        self.generate.side_effect = None
        self.generate.return_value = self.rec
        self.enterContext(patch.object(api, 'generation_guard', return_value=nullcontext()))
        self.enterContext(patch.object(api, 'course_input', return_value={'id': 'A3'}))
        self.enterContext(patch.object(api.runtime, 'context', return_value=Mock(live=True)))
        response = self.client.post(self.url, params={'course': 'A3'})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['error']['code'], 'RECOMMENDATIONS_CHANGED')
        self.tx.run.assert_not_called()

    def test_deleted_after_get_is_rejected_even_if_catalog_snapshot_still_lists_it(self):
        response = self.client.get(self.url, params={'course': 'A3'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()['recommendations']['skills'][0]['courses']), 2)
        del self.fresh_items['alt-course']
        before = deepcopy(self.raw)
        self.assertEqual(self.put(course_id='alt-course').status_code, 422)
        self.lookup.assert_any_call(refresh=True)
        self.tx.run.assert_not_called()
        self.assertEqual(self.raw, before)

    def test_direct_put_rejects_unusable_or_type_changed_book(self):
        for state in ({'usable': False}, {'type': 'cert'}):
            with self.subTest(state=state):
                self.fresh_items['alt-book'] = dict(self.items['alt-book'], **state)
                self.assertEqual(self.put(books=['alt-book']).status_code, 422)
        self.tx.run.assert_not_called()

    def test_free_price_change_filters_alternative_and_rejects_direct_put(self):
        self.rec['retrieval']['version'] = version_for('A1')
        self.fresh_items['alt-course']['cost'] = 100
        self.assertEqual(self.put(track='A1', course_id='alt-course').status_code, 422)
        self.items['alt-course'] = self.fresh_items['alt-course']
        response = self.client.get(self.url, params={'course': 'A1'})
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()['recommendations']['skills'][0]
        self.assertEqual([item['id'] for item in row['courses']], ['course'])
        self.assertEqual([item['id'] for item in row['books']], ['book', 'alt-book'])
        self.assertIsNone(row['selectedCourse'])
        self.assertEqual(response.json()['choices'], self.choices)
        self.tx.run.assert_not_called()

    def test_free_selected_course_price_change_still_invalidates_cache(self):
        self.rec['retrieval']['version'] = version_for('A1')
        self.items['course'] = dict(self.items['course'], cost=100)
        response = self.client.get(self.url, params={'course': 'A1'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()['recommendations'])
        self.assertEqual(response.json()['choices'], {})
        self.tx.run.assert_not_called()

    def test_empty_current_lists_can_save_empty_choices(self):
        row = self.rec['skills'][0]
        row.update(courses=[], books=[], selectedCourse=None, selectedBooks=[])
        self.choices['SQL'].update(course=None, books=[])
        response = self.client.get(self.url, params={'course': 'A3'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['recommendations']['skills'], [row])
        self.assertEqual(self.put(course_id=None, books=[]).status_code, 200)
        self.lookup.assert_not_called()
        self.tx.run.assert_called_once()

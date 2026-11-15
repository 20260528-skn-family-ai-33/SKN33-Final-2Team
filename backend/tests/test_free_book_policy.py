import unittest
from copy import deepcopy
from unittest.mock import Mock, patch
from app.free_track import validate_free_plan
from app.errors import ApiError
from app.services import plans

class FreeBookPolicyTests(unittest.TestCase):
 def check(self,rows):
  t=Mock();t.all.return_value=rows
  plan={'opt':'A1','acts':[{'res':row['resource_key']} for row in rows]}
  validate_free_plan(t,plan)
  self.assertIn('FOR SHARE',t.all.call_args.args[0]);return plan
 def test_book_price_counts_as_zero(self):
  p=self.check([{'resource_key':'c','resource_type':'course','cost_won':0},{'resource_key':'book_b','resource_type':'book','cost_won':23000}]);self.assertEqual(p['cost'],0);self.assertFalse(p['costUnknown'])
 def test_unknown_book_price_is_not_marked_unknown(self):
  p=self.check([{'resource_key':'book_b','resource_type':'book','cost_won':None}]);self.assertEqual(p['cost'],0);self.assertFalse(p['costUnknown'])
 def test_zero_budget_allows_book_without_price(self):
  t=Mock();t.all.return_value=[{'resource_key':'c','resource_type':'course','cost_won':0},{'resource_key':'book_b','resource_type':'book','cost_won':None}]
  plan={'opt':'A2','acts':[{'res':'c'},{'res':'book_b'}]}
  validate_free_plan(t,plan,budget='0');self.assertEqual((plan['cost'],plan['costUnknown']),(0,False))
 def test_book_cost_helper_only_changes_books(self):
  from app.course_levels import book_cost
  self.assertEqual((book_cost('book',None),book_cost('book',23000),book_cost('course',None),book_cost('course',5000)),(0,0,None,5000))
 def test_vector_search_treats_books_as_free(self):
  from app.services import resource_rag
  read=Mock(return_value=[])
  resource_rag.search_vectors('books',['1'],[0.0],5,True,read=read)
  sql=read.call_args.args[0]
  self.assertIn("CASE WHEN e.resource_type='books' THEN 0 ELSE m.cost_won END",sql)
  self.assertIn("e.resource_type='books' OR m.cost_won=0",sql)
 def test_paid_course_still_rejected(self):
  with self.assertRaises(ApiError):self.check([{'resource_key':'c','resource_type':'course','cost_won':1}])
 def test_deleted_book_is_still_rejected(self):
  with self.assertRaises(ApiError):self.check([{'resource_key':'book_b','resource_type':'book','cost_won':23000,'deleted':True}])

 def test_zero_budget_rechecks_crash_and_challenge_at_confirmation(self):
  for track in ('A2', 'A3'):
   for price in (48000, None, 0):
    with self.subTest(track=track, price=price):
     t = Mock()
     t.all.return_value = [{'resource_key':'c', 'resource_type':'course', 'cost_won':price}]
     plan = {'opt':track, 'acts':[{'res':'c'}]}
     if price == 0:
      validate_free_plan(t, plan, budget='0')
      self.assertEqual(plan['cost'], 0)
     else:
      with self.assertRaises(ApiError) as error:
       validate_free_plan(t, plan, budget='0')
      self.assertEqual(error.exception.code, 'ZERO_BUDGET_PRICE_CHANGED')
     self.assertIn('FOR SHARE', t.all.call_args.args[0])


class ConfirmedBookCostTests(unittest.TestCase):
    def read(self, plan, steps, versions=()):
        original = deepcopy(plan)
        row = dict(roadmap_id='r', content=plan, step_prices=steps, status='IN_PROGRESS',
                   created_at=None, done_at=None, archived_at=None, resumed_at=None)
        with patch.object(plans.db, 'all_', side_effect=[[{'plan': v} for v in versions], []]), \
             patch.object(plans, '_comments', return_value=[]), patch.object(plans.catalog, 'items', return_value={}):
            result = plans.record(row, for_mgr=True)
        self.assertEqual(plan, original)
        return result

    def test_current_and_previous_versions_use_their_own_selected_prices(self):
        acts = [{'res': 'course'}, {'res': 'book_1'}, {'res': 'book_1'}]
        current = dict(version=2, acts=acts, cost=23000, costUnknown=False)
        offers = {'courses': [{'id': 'course', 'cost': 4000}],
                  'books': [{'id': 'book_1', 'cost': 10000}, {'id': 'unused', 'cost': 9000}]}
        previous = {'version': 1, 'acts': acts, 'cost': 14000, 'costUnknown': False,
                    'def': {'learningReport': {'recommendations': {'skills': [offers]}}}}
        result = self.read(current, {'course': [False, 0], 'book_1': [True, 23000]}, [previous, current])
        self.assertEqual((result['plan']['cost'], result['plan']['costUnknown']), (0, False))
        self.assertEqual([p['cost'] for p in result['versions']], [4000, 0])
        self.assertEqual(previous['cost'], 14000)

    def test_preserves_unknown_course_and_exam_prices_and_unverifiable_totals(self):
        cases = [
            ({'course': [False, 0], 'book': [True, None]}, (0, True), (0, False)),
            ({'course': [False, None], 'book': [True, 23000]}, (23000, True), (0, True)),
            ({'exam': [False, None], 'book': [True, None]}, (0, True), (0, True)),
            ({'course': [False, 48000]}, (0, True), (0, True)),
            ({'course': [False, 1000], 'book': [True, 23000]}, (1000, False), (1000, False)),
            ({'book': [True, 23000]}, (5000, True), (5000, True)),
        ]
        for prices, saved, expected in cases:
            with self.subTest(prices=prices, saved=saved):
                plan = dict(acts=[{'res': key} for key in prices], cost=saved[0], costUnknown=saved[1])
                result = self.read(plan, prices)['plan']
                self.assertEqual((result['cost'], result['costUnknown']), expected)

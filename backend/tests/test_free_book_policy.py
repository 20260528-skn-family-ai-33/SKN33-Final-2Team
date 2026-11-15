import unittest
from unittest.mock import Mock
from app.free_track import validate_free_plan
from app.errors import ApiError

class FreeBookPolicyTests(unittest.TestCase):
 def check(self,rows):
  t=Mock();t.all.return_value=rows
  plan={'opt':'A1','acts':[{'res':row['resource_key']} for row in rows]}
  validate_free_plan(t,plan)
  self.assertIn('FOR SHARE',t.all.call_args.args[0]);return plan
 def test_free_course_with_paid_book_keeps_book_cost(self):
  p=self.check([{'resource_key':'c','resource_type':'course','cost_won':0},{'resource_key':'book_b','resource_type':'book','cost_won':23000}]);self.assertEqual(p['cost'],23000)
 def test_unknown_book_price_is_allowed_but_visible(self):
  p=self.check([{'resource_key':'book_b','resource_type':'book','cost_won':None}]);self.assertTrue(p['costUnknown'])
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

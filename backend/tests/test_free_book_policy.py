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

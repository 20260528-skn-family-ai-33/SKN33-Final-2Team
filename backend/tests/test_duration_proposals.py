import unittest
from app.services.duration_proposals import calculate_durations,METHOD
from app.agents.resource_recommendations import RecommendationError

class DurationTests(unittest.TestCase):
 def setUp(self):
  self.project={'details':{'hours':6}}
  self.rec={'skills':[{'name':name,'courses':[{'id':name+'c','hours':8}],'books':[{'id':name+'b'+str(i)} for i in range(3)]} for name in ('A','B')]}
  self.choices={name:{'course':name+'c','books':[name+'b0'],'enabled':True} for name in ('A','B')}
 def compute(self,weekly=4):return calculate_durations(self.project,self.rec,self.choices,['A','B'],weekly)
 def test_known_hours_ceil_excludes_selected_books(self):
  self.choices['A']['books']=['Ab0','Ab1','Ab2']
  result=self.compute()['A'];self.assertEqual(result['weeks'],2);self.assertEqual(result['courseWeeks'],2);self.assertEqual(result['method'],METHOD)
 def test_unknown_course_hours_is_one_week(self):
  self.rec['skills'][0]['courses'][0]['hours']=None
  self.assertEqual(self.compute()['A']['weeks'],1)
 def test_estimated_hours_used_without_claiming_confirmed(self):
  self.rec['skills'][0]['courses'][0]['estimated']=['hours']
  self.assertEqual(self.compute()['A']['courseWeeks'],2)
  self.assertEqual(self.compute()['A']['estimatedCourses'],['Ac'])
 def test_course_weekly_hours_used_if_no_input(self):
  self.project['details']['hours']=''
  self.assertEqual(self.compute(4)['A']['weeks'],2)
 def test_excluding_subtracts_skill_without_model(self):
  self.choices['A']['enabled']=False
  self.assertEqual(list(self.compute()),['B'])
 def test_book_only_and_no_materials_are_not_filled_with_fake_course(self):
  self.rec['skills'][0]['courses']=[];self.choices['A']['course']=None
  self.assertEqual(self.compute()['A']['weeks'],0)
  self.choices['A']['books']=[];self.assertEqual(self.compute()['A']['weeks'],0)
 def test_weekly_time_must_be_valid(self):
  self.project['details']['hours']=''
  with self.assertRaises(RecommendationError):self.compute(None)


class PeriodLimitTests(unittest.TestCase):
 def test_selected_total_over_deadline_keeps_actual_estimate(self):
  rec={'skills':[{'name':n,'courses':[{'id':n,'hours':20}],'books':[]} for n in ('A','B')]}
  choices={n:{'course':n,'books':[]} for n in ('A','B')}
  result=calculate_durations({'details':{'weeks':8,'hours':4}},rec,choices,['A','B'],4)
  self.assertEqual(sum(row['weeks'] for row in result.values()),10)

 def test_saved_recommendation_limit_does_not_block_selection(self):
  rec={'periodWeeks':8,'skills':[{'name':'A','courses':[{'id':'a','hours':72}],'books':[]}]}
  result=calculate_durations({'details':{}},rec,{'A':{'course':'a','books':[]}},['A'],4)
  self.assertEqual(result['A']['weeks'],18)


 def test_all_courses_keep_actual_estimate_over_input_period(self):
  for course in ('A1','A2','A3'):
   rec={'skills':[{'name':'A','courses':[{'id':'a','hours':72}],'books':[]}]}
   result=calculate_durations({'details':{'weeks':8,'hours':4},'selectedCourse':{'id':course}},rec,{'A':{'course':'a','books':[]}},['A'],4)
   self.assertEqual(result['A']['weeks'],18)

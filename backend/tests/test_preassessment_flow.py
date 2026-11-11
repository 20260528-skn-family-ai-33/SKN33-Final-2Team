from unittest import TestCase
from app.services.preassessment_flow import checked_skills
from app.agents.skill_selection import SelectionError
from app.services.drafts import input_signature

class PreassessmentFlowTests(TestCase):
    def test_selected_subset_and_order_preserved_without_mutating_input(self):
        rows=[{'name':n,'application':'Apply '+n} for n in ('B','A')]
        out=checked_skills(rows,['A','B','C'])
        self.assertEqual([r['name'] for r in out['skills']],['B','A'])
        self.assertNotIn('reason',rows[0])
    def test_unknown_duplicate_empty_or_more_than_three_rejected(self):
        row={'name':'A','application':'Use A'}
        for rows in ([],[row,row],[dict(row,name='unknown')],[row]*6,[dict(row,application='')]):
            with self.assertRaises(SelectionError):checked_skills(rows,['A'])
    def test_three_skills_pass_and_four_are_rejected(self):
        names=['A','B','C','D']
        rows=[{'name':n,'application':'Use '+n} for n in names]
        self.assertEqual([r['name'] for r in checked_skills(rows[:3],names)['skills']],['A','B','C'])
        with self.assertRaises(SelectionError):checked_skills(rows,names)
    def test_skill_order_or_membership_invalidates_assessment_signature(self):
        d={'goal':'SQL','prefs':{},'selectedSkills':[{'name':'A'},{'name':'B'}]}
        before=input_signature(d);d['selectedSkills'].reverse()
        self.assertNotEqual(before,input_signature(d))

    def test_recommendations_allow_three_reject_four_and_keep_challenge_depth_validation(self):
        from app.services.course_skills import validate_recommendations
        rows=[{'name':str(i),'application':'Specific scope'} for i in range(4)]
        allowed={r['name'] for r in rows}
        for course in ('A1','A2','A3'):
            if course!='A3':self.assertEqual(len(validate_recommendations(rows[:3],allowed,course)),3)
            with self.assertRaises(ValueError):validate_recommendations(rows,allowed,course)
        with self.assertRaises(ValueError):validate_recommendations(rows[:3],allowed,'A3',require_depth=True)

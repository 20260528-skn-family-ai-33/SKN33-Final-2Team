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
    def test_unknown_duplicate_empty_or_more_than_five_rejected(self):
        row={'name':'A','application':'Use A'}
        for rows in ([],[row,row],[dict(row,name='unknown')],[row]*6,[dict(row,application='')]):
            with self.assertRaises(SelectionError):checked_skills(rows,['A'])
    def test_skill_order_or_membership_invalidates_assessment_signature(self):
        d={'goal':'SQL','prefs':{},'selectedSkills':[{'name':'A'},{'name':'B'}]}
        before=input_signature(d);d['selectedSkills'].reverse()
        self.assertNotEqual(before,input_signature(d))

    def test_fixed_skills_allow_crash_five_but_keep_challenge_depth_validation(self):
        from app.services.course_skills import validate_recommendations
        rows=[{'name':str(i),'application':'Specific scope'} for i in range(5)]
        allowed={r['name'] for r in rows}
        self.assertEqual(len(validate_recommendations(rows,allowed,'A2',max_skills=5)),5)
        with self.assertRaises(ValueError):validate_recommendations(rows,allowed,'A2')
        with self.assertRaises(ValueError):validate_recommendations(rows,allowed,'A3',max_skills=5,require_depth=True)

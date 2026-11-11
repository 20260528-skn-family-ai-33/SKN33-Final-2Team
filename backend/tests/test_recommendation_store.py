import copy
import unittest
from unittest.mock import Mock, patch
from app.services import survey_store as store
from app.agents.resource_recommendations import RecommendationError

class RecommendationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tx=Mock();self.tx.run.return_value=1
        self.tx.all.return_value = []
        self.pre={'version':1,'generationId':'pre','completed':True,'survey':{},'answers':{'q':0}}
        self.tx.one.return_value={'draft_choices':{store.KEY:self.pre}}
        items = {'c': {'id': 'c', 'type': 'course', 'cost': 0, 'usable': True},
                 'b': {'id': 'b', 'type': 'book', 'usable': True}}
        catalog = patch('app.catalog.items', return_value=items)
        catalog.start()
        self.addCleanup(catalog.stop)
        self.result={'skills':[{'name':'분석','courses':[items['c']],'books':[items['b']],'selectedCourse':'c','selectedBooks':['b']}]}
    def test_recommendations_default_one_book_and_preserve_assessment(self):
        saved=store.save_recommendations(self.tx,1,'project','pre',self.result)
        self.assertEqual(saved['resourceChoices'],{'분석':{'course':'c','books':['b'],'enabled':True}})
        self.assertEqual(saved['answers'],{'q':0})
        self.assertEqual(self.pre['answers'],{'q':0})
        self.assertNotIn('recommendations',self.pre)
    def test_incomplete_or_changed_assessment_cannot_store(self):
        for changed in ({'completed':False},{'generationId':'new'}):
            self.tx.one.return_value={'draft_choices':{store.KEY:dict(self.pre,**changed)}}
            with self.assertRaises(store.StoreError):store.save_recommendations(self.tx,1,'project','pre',self.result)
        self.tx.run.assert_not_called()
    def test_choices_must_reference_current_recommendation(self):
        saved=store.save_recommendations(self.tx,1,'project','pre',self.result)
        self.tx.one.return_value={'draft_choices':{store.KEY:saved}}
        self.tx.run.reset_mock()
        with self.assertRaises(store.StoreError):store.save_resource_choices(self.tx,1,'project','pre','old',{})
        self.tx.run.assert_not_called()
        choices={'분석':{'course':'c','books':[]}}
        result=store.save_resource_choices(self.tx,1,'project','pre',saved['recommendations']['id'],choices)
        self.assertEqual(result['resourceChoices'],choices)

    def test_exclusion_keeps_skill_and_selected_materials(self):
        saved=store.save_recommendations(self.tx,1,'project','pre',self.result)
        self.tx.one.return_value={'draft_choices':{store.KEY:saved}}
        choices={'분석':{'course':'c','books':['b'],'enabled':False}}
        updated=store.save_resource_choices(self.tx,1,'project','pre',saved['recommendations']['id'],choices,skill_order=['분석'])
        self.assertEqual(updated['skillOrder'],['분석'])
        self.assertFalse(updated['resourceChoices']['분석']['enabled'])
        self.assertEqual(updated['resourceChoices']['분석']['books'],['b'])

    def test_course_selection_marks_materials_ready_without_generating_activities(self):
        from app.services.activity_selection import materials_ready
        saved=store.save_recommendations(self.tx,1,'project','pre',self.result,course='A1')
        from app.services.course_recommendations import merge_scope,scope_view
        base=merge_scope(self.pre,saved)
        self.tx.one.return_value={'draft_choices':{store.KEY:base}}
        self.assertFalse(materials_ready(scope_view(base,'A1')))
        choices={'분석':{'course':'c','books':['b'],'enabled':True}}
        updated=store.save_resource_choices(self.tx,1,'project','pre',saved['recommendations']['id'],choices,course='A1')
        self.assertTrue(materials_ready(updated))
        self.assertFalse(updated.get('activityProposal'))
        changed=copy.deepcopy(updated);changed['resourceChoices']['분석']['books']=[]
        self.assertFalse(materials_ready(changed))
        combined=merge_scope(base,updated)
        self.assertTrue(materials_ready(scope_view(combined,'A1')))
        self.assertFalse(materials_ready(scope_view(combined,'A3')))

    def test_new_recommendations_require_material_selection_again(self):
        from app.services.activity_selection import materials_ready
        saved=store.save_recommendations(self.tx,1,'project','pre',self.result,course='A1')
        from app.services.course_recommendations import merge_scope
        base=merge_scope(self.pre,saved)
        self.tx.one.return_value={'draft_choices':{store.KEY:base}}
        updated=store.save_resource_choices(self.tx,1,'project','pre',saved['recommendations']['id'],saved['resourceChoices'],course='A1')
        self.tx.one.return_value={'draft_choices':{store.KEY:merge_scope(base,updated)}}
        replaced=store.save_recommendations(self.tx,1,'project','pre',self.result,course='A1',replace=True)
        self.assertFalse(materials_ready(replaced))

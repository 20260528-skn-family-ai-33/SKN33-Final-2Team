import copy
import unittest
from unittest.mock import Mock
from app.services import survey_store as store
from app.agents.resource_recommendations import RecommendationError

class RecommendationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tx=Mock();self.tx.run.return_value=1
        self.pre={'version':1,'generationId':'pre','completed':True,'survey':{},'answers':{'q':0}}
        self.tx.one.return_value={'draft_choices':{store.KEY:self.pre}}
        self.result={'skills':[{'name':'분석','courses':[{'id':'c'}],'books':[{'id':'b'}],'selectedCourse':'c','selectedBooks':['b']}]}
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

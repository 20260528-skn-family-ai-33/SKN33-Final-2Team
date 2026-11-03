from contextlib import contextmanager, nullcontext
from unittest import TestCase
from unittest.mock import Mock,patch
from app.routers import preassessment as api
from app.services.course_recommendations import scope_view

@contextmanager
def transaction(tx):
    yield tx

class SelectedSkillGenerationTests(TestCase):
    def test_generate_only_user_selected_skills_without_reselecting(self):
        tx=Mock();rows=[{'name':'SQL','application':'Join'}]
        project={'goal':'SQL goal','selectedSkills':rows}
        with patch.object(api,'generation_guard',return_value=nullcontext()), patch.object(api.db,'tx',side_effect=lambda:transaction(tx)), patch.object(api,'project_input',return_value=project), patch.object(api,'read',return_value=None), patch.object(api.profile,'view',return_value={}), patch.object(api,'profile_input',return_value={}), patch.object(api.runtime,'context',return_value=Mock(live=True)), patch('app.catalog.skill_names',return_value=['SQL','Python']), patch.object(api,'select_from_catalog') as select, patch.object(api,'generate_survey',return_value={}) as generate, patch.object(api,'save_generated',return_value={}), patch.object(api,'public_view',return_value={'generationId':'g'}):
            self.assertEqual(api.generate_for(1,'p'),{'generationId':'g'})
        select.assert_not_called()
        self.assertEqual([r['name'] for r in generate.call_args.args[1]['skills']],['SQL'])

    def test_new_flow_course_scoping_preserves_selected_skill_order(self):
        rows=[{'name':'B','application':'B scope'},{'name':'A','application':'A scope'}]
        saved={'project':{'selectedSkills':rows},'selection':{'skills':rows},'generationId':'g'}
        option={'learningSkillsVersion':'v','learningSkills':[{'name':'A','application':'other'}]}
        scoped=scope_view(saved,'A2',option)
        self.assertEqual(scoped['skillOrder'],['B','A'])
        self.assertEqual([r['application'] for r in scoped['selection']['skills']],['B scope','A scope'])

    def test_skill_preview_does_not_send_learning_conditions_to_the_model(self):
        from types import SimpleNamespace
        from uuid import uuid4
        project={'goal':'SQL goal','projectSummary':'기획서 요약','details':{'hours':8,'weeks':12,'budget':10000,'etc':'주말'},'selectedSkills':[{'name':'SQL','application':'Join'}]}
        with patch.object(api,'generation_guard',return_value=nullcontext()),patch.object(api.db,'tx',side_effect=lambda:transaction(Mock())),patch.object(api,'project_input',side_effect=lambda *_:dict(project)),patch.object(api.profile,'view',return_value={}),patch.object(api,'profile_input',return_value={}),patch.object(api.runtime,'context',return_value=Mock(live=True)),patch.object(api,'select_from_catalog',return_value={'skills':[]}) as select:
            api.preview_skills.__wrapped__(uuid4(),a=SimpleNamespace(id=1))
        payload=select.call_args.args[1]
        self.assertNotIn('details',payload);self.assertNotIn('selectedSkills',payload)
        self.assertEqual(payload['goal'],'SQL goal');self.assertEqual(payload['projectSummary'],'기획서 요약')
        self.assertIn('details',project)

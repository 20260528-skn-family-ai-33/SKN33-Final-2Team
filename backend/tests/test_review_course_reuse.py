from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from app.services import activity_selection as activities, drafts
from app.routers import preassessment as api
from app.errors import ApiError

class ReviewCourseReuseTests(TestCase):
    def setUp(self):
        self.draft={'chosen':'A2','gen':{'options':{'A1':{'id':'A1'},'A2':{'id':'A2'}}}}
        self.saved={'generationId':'g','recommendations':{'id':'r'},'resourceChoices':{},'skillOrder':[]}
    def context(self, course=None):
        with patch('app.services.survey_store.read',return_value={}), patch.object(drafts,'_row',return_value={'draft_choices':{'draft':self.draft}}), patch.object(api,'course_context',return_value=deepcopy(self.saved)), patch.object(activities,'materials_ready',return_value=True):
            return activities.context(Mock(),1,'p',course)
    def test_explicit_course_does_not_change_current_choice(self):
        _,d=self.context('A1')
        self.assertEqual(d['chosen'],'A1'); self.assertEqual(self.draft['chosen'],'A2')
    def test_legacy_client_uses_current_course(self):
        _,d=self.context();self.assertEqual(d['chosen'],'A2')
    def test_unknown_course_is_rejected(self):
        with self.assertRaises(ApiError):self.context('A3')
    def test_courses_have_distinct_guards_and_existing_result_skips_model(self):
        def context(*args,course=None):return deepcopy(self.saved),dict(self.draft,chosen=course or self.draft['chosen'])
        with patch.object(api.db,'tx',side_effect=lambda:nullcontext(Mock())), patch.object(api,'generation_guard',side_effect=lambda *args:nullcontext()) as guard, patch.object(activities,'context',side_effect=context), patch.object(activities,'current_record',return_value={'key':'existing'}), patch.object(activities,'view',return_value={'proposal':'cached'}), patch.object(api.runtime,'context') as model:
            for course in ('A1','A2'):
                self.assertEqual(api.propose_activities.__wrapped__('p',SimpleNamespace(id=1),course=course),{'proposal':'cached'})
        self.assertEqual([call.args for call in guard.call_args_list],[('draft-review','p:A1'),('draft-review','p:A2')]);model.assert_not_called()
    def test_changed_materials_are_rejected_before_background_result_is_saved(self):
        def context(*args,course=None):return deepcopy(self.saved),dict(self.draft,chosen=course or self.draft['chosen'])
        def mutate(employee,project,save):save(Mock(),{'v2Survey':{}})
        with patch.object(api.db,'tx',side_effect=lambda:nullcontext(Mock())), patch.object(api,'generation_guard',side_effect=lambda *args:nullcontext()), patch.object(activities,'context',side_effect=context), patch.object(activities,'current_record',return_value=None), patch.object(api.runtime,'context',return_value=SimpleNamespace(live=True,mode='test')), patch.object(activities,'propose',return_value={'key':'old'}), patch.object(activities,'fingerprint',return_value='changed'), patch.object(drafts,'_mutate',side_effect=mutate), patch.object(activities,'append_proposal') as append:
            with self.assertRaises(ApiError) as error:api.propose_activities.__wrapped__('p',SimpleNamespace(id=1),course='A1')
        self.assertEqual(error.exception.code,'ACTIVITIES_CHANGED');append.assert_not_called()

    def test_skill_query_routes_to_single_skill_repropose_and_rejects_invalid_before_model(self):
        saved = deepcopy(self.saved)
        saved['skillOrder'] = ['SQL', 'Disabled']
        saved['resourceChoices'] = {'SQL': {'course': 'c1', 'books': [], 'enabled': True}, 'Disabled': {'course': 'c2', 'books': [], 'enabled': False}}
        def context(*args, course=None):
            return deepcopy(saved), dict(self.draft, chosen=course or self.draft['chosen'])
        with patch.object(api.db, 'tx', side_effect=lambda: nullcontext(Mock())), \
             patch.object(api, 'generation_guard', side_effect=lambda *args: nullcontext()), \
             patch.object(activities, 'context', side_effect=context), \
             patch.object(activities, 'current_record', return_value=None), \
             patch.object(api.runtime, 'context') as rt_ctx:
            with self.assertRaises(ApiError) as no_initial:
                api.propose_activities.__wrapped__('p', SimpleNamespace(id=1), skill='SQL', course='A2')
            self.assertEqual(no_initial.exception.code, 'ACTIVITIES_REQUIRED')
            rt_ctx.assert_not_called()

        for bad_skill in ('', '   ', 'Missing', 'Disabled'):
            with self.subTest(bad_skill=bad_skill), \
                 patch.object(api.db, 'tx', side_effect=lambda: nullcontext(Mock())), \
                 patch.object(api, 'generation_guard', side_effect=lambda *args: nullcontext()), \
                 patch.object(activities, 'context', side_effect=context), \
                 patch.object(activities, 'current_record', return_value={'key': 'k', 'option': {'acts': []}}), \
                 patch.object(api.runtime, 'context') as rt_ctx:
                with self.assertRaises(ApiError) as err:
                    api.propose_activities.__wrapped__('p', SimpleNamespace(id=1), skill=bad_skill, course='A2')
                self.assertEqual(err.exception.code, 'SKILL_REQUIRED')
                rt_ctx.assert_not_called()

        existing = {'id': 'rev-0', 'key': 'k', 'option': {'acts': []}}
        def mutate(employee, project, save):
            state = {'v2Survey': {}}
            save(Mock(), state)
            return state
        with patch.object(api.db, 'tx', side_effect=lambda: nullcontext(Mock())), \
             patch.object(api, 'generation_guard', side_effect=lambda *args: nullcontext()), \
             patch.object(activities, 'context', side_effect=context), \
             patch.object(activities, 'current_record', return_value=existing), \
             patch.object(activities, 'fingerprint', return_value='k'), \
             patch.object(api.runtime, 'context', return_value=SimpleNamespace(live=True, mode='test')), \
             patch.object(api.runtime, 'model', return_value=Mock()), \
             patch.object(activities, 'repropose_skill', return_value={'id': 'rev-1', 'key': 'k', 'changedSkill': 'SQL'}) as repropose, \
             patch.object(activities, 'propose') as propose_all, \
             patch.object(drafts, '_mutate', side_effect=mutate), \
             patch.object(activities, 'append_proposal'), \
             patch('app.services.course_recommendations.merge_scope', return_value={}), \
             patch('app.services.course_recommendations.scope_view', return_value={}), \
             patch.object(activities, 'view', return_value={'proposal': {'id': 'rev-1'}}):
            out = api.propose_activities.__wrapped__('p', SimpleNamespace(id=1), skill=' SQL ', course='A2')
        self.assertEqual(out['proposal']['id'], 'rev-1')
        repropose.assert_called_once()
        self.assertEqual(repropose.call_args.args[2], 'SQL')
        propose_all.assert_not_called()

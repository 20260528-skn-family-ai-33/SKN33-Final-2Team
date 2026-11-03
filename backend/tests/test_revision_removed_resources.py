"""제외·교체 자료가 이전 스냅샷 때문에 필수 후보로 부활하지 않는지 검증한다."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from app import catalog_candidates, llm
from app.agents import roadmap
from test_catalog_candidates import resource


class RevisionRemovedResourcesTests(TestCase):
    def run_revision(self, action, *, stale=True, shared=False, additions=None, cert=False):
        records={'new':resource('new')}
        if stale: records['old']=resource('old',usable=False)
        acts=[{'id':'a','stage':2,'title':'이전 강좌','res':'old','hours':4}]
        if shared: acts.append(dict(acts[0],id='b'))
        changes={action:[{'key':'a'}]} if action else {}
        if additions: changes['addResources']=additions
        handoff={'goal':'SQL 조인 검증','focus':['SQL'],'skillNames':['SQL'],
                 'selectedResourceIds':['old'],'prefs':{'certRes':'old'} if cert else {}}
        inp={'pid':'A3','plan':{'opt':'A3','name':'Challenge','hours':6,'start':2,'acts':acts,'def':{}},
             'handoff':handoff,'changes':changes}
        original=deepcopy(inp)
        def select(texts,track,**kwargs):
            return catalog_candidates.select(records,['SQL'],texts,track,required=kwargs.get('required'))
        def run(ctx,name,task,data,mock,api,**kwargs): return api(None)
        with patch.object(roadmap.rt,'run',side_effect=run), patch.object(roadmap,'_sys',return_value='system'), \
             patch.object(roadmap.catalog,'skill_names',return_value=['SQL']), \
             patch.object(roadmap.catalog,'roadmap_selection',side_effect=select) as selection, \
             patch.object(roadmap.catalog_budget,'pack',side_effect=lambda chosen,system,payload,limit:payload), \
             patch.object(roadmap.rt,'llm_json',return_value={'acts':[]}) as model, \
             patch.object(roadmap,'_validate_learning_acts'), patch.object(roadmap,'finish_option',return_value={'acts':[]}):
            try:
                roadmap.revise(SimpleNamespace(mode='openai'),inp)
                return selection.call_args.kwargs['required'],model.call_args.args[2]
            finally:
                self.assertEqual(inp,original)

    def test_remove_and_replace_allow_deleted_or_unusable_old_resource(self):
        for action in ('removeActs','replaceActs'):
            for stale in (False,True):
                with self.subTest(action=action,stale=stale):
                    required,payload=self.run_revision(action,stale=stale)
                    self.assertNotIn('old',required)
                    self.assertEqual(payload['handoff']['selectedResourceIds'],[])

    def test_shared_resource_still_required_by_retained_activity_is_rejected(self):
        with self.assertRaises(llm.LlmError):self.run_revision('removeActs',shared=True)

    def test_retained_unavailable_resource_is_still_rejected(self):
        with self.assertRaises(llm.LlmError):self.run_revision(None)

    def test_explicit_addition_is_still_validated(self):
        for rid in ('old','missing'):
            with self.subTest(rid=rid),self.assertRaises(llm.LlmError):
                self.run_revision('replaceActs',additions=[rid])
        required,_=self.run_revision('replaceActs',additions=['new'])
        self.assertIn('new',required)

    def test_removed_certificate_snapshot_does_not_reintroduce_old_resource(self):
        _,payload=self.run_revision('removeActs',cert=True)
        self.assertIsNone(payload['handoff']['prefs']['certRes'])

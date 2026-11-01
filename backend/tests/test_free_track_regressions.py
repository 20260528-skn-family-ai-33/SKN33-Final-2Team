"""Free-only regressions from PR #41. No model calls or database writes."""
import copy
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import Mock, patch
from app import catalog, catalog_budget, llm
from app.agents import roadmap as rm
from app.errors import ApiError
from app.free_track import validate_free_plan
from app.services import drafts, plans

@contextmanager
def tx_of(t):
    yield t

class FreeTrackRegressions(unittest.TestCase):
    def resources(self, cert_cost=0):
        def item(key,cost,kind='강좌'):
            return {'id':key,'title':key,'cost':cost,'hours':1,'format':'영상','kind':kind,
                    'type':'cert' if kind=='자격' else 'course','stage':2,'skills':['s'],'usable':True,
                    'content':'RAG 검색과 근거 답변을 학습한다.'}
        return {'free':item('free',0),'paid':item('paid',100),'unknown':item('unknown',None),
                'cert':item('cert',cert_cost,'자격')}

    def handoff(self):
        return {'goal':'RAG test','startStage':1,'prefs':{'certRes':'cert','weeklyHours':4,
                'deadlineWeeks':None,'budgetWon':None,'formatKey':'mixed'}}

    def template(self):
        return {'tagline':'test','reason':'test','pros':[],'cons':[],
                'acts':[{'stage':2,'title':'free','res':'free'},
                        {'stage':3,'title':'task','res':None,'hours':1,'how':'test'}]}

    def test_mock_generation_free_paid_unknown_cert(self):
        for cost in (0,100,None):
            resources=self.resources(cost)
            templates={pid:self.template() for pid in ('A1','A2','A3')}
            for pid in templates:
                with self.subTest(pid=pid,cost=cost), patch.object(rm,'_cat',return_value=resources), patch.object(rm,'TEMPLATES',templates):
                    out=rm._mock_option({'pid':pid,'handoff':self.handoff()})
                    ids=[a['res'] for a in out['acts']]
                    self.assertEqual('cert' in ids,pid!='A1' or cost==0)
                    if pid=='A1' and cost!=0:
                        self.assertIn('제외',out['reason'])
                    self.assertIn('free',ids)

    def test_free_generation_ignores_available_budget(self):
        resources = self.resources(1000)
        template = self.template()
        template['acts'].append({'stage': 2, 'title': 'paid', 'res': 'paid'})
        for budget in (0, 100000, 1000000):
            h = self.handoff()
            h['prefs']['budgetWon'] = budget
            with self.subTest(budget=budget), patch.object(rm, '_cat', return_value=resources), patch.object(rm, 'TEMPLATES', {'A1': template}):
                out = rm._mock_option({'pid': 'A1', 'handoff': h})
            ids = [a['res'] for a in out['acts'] if a.get('res')]
            self.assertEqual(ids, ['free'])
            self.assertIn('제외', out['reason'])
    def test_mock_regeneration_and_revision_filter_existing_paid(self):
        resources=self.resources(100)
        for pid in ('A1','A2','A3'):
            prev={'id':pid,'name':pid,'short':pid,'tagline':'test','reason':'test','pros':[],'cons':[],
                  'acts':[{'id':'f','stage':2,'title':'free','res':'free','hours':1,'how':'test'},
                          {'id':'p','stage':2,'title':'paid','res':'paid','hours':1,'how':'test'}]}
            plan=dict(prev,opt=pid,start=1,hours=4); plan['def']=prev
            with patch.object(rm,'_cat',return_value=resources):
                regen=rm._mock_regen({'pid':pid,'previousDef':copy.deepcopy(prev),'request':{},'handoff':self.handoff()})
                revised=rm._mock_revise({'pid':pid,'plan':copy.deepcopy(plan),'changes':{},'handoff':self.handoff()})
            for result in (regen,revised):
                with self.subTest(pid=pid,result=result):
                    self.assertEqual(any(a['res']=='paid' for a in result['acts']),pid!='A1')
                    if pid=='A1': self.assertTrue(any('제외' in note for note in result['notes']))

    def test_replacement_prefers_free_only_for_free(self):
        data=self.resources()
        data['paid']['title']='AAA'
        data['free']['title']='ZZZ'
        with patch.object(rm,'_cat',return_value=data):
            self.assertEqual(rm._alt_same('unknown',set(),None,free_only=True),'free')
            self.assertEqual(rm._alt_same('unknown',set(),None),'paid')

    def test_revision_format_replacement_keeps_free_activity(self):
        for pid in ('A1', 'A2', 'A3'):
            for hint, original_format, target_format in (
                ('영상으로', '문서', '영상'),
                ('문서로', '영상', '문서'),
            ):
                for paid_cost in (100, None):
                    for with_other_activity in (False, True):
                        resources = self.resources()
                        original = dict(resources['free'], id='original', title='원본', format=original_format)
                        paid = dict(resources['paid'], id='paid-target', title='AAA 유료 후보', format=target_format, cost=paid_cost)
                        free = dict(resources['free'], id='free-target', title='ZZZ 무료 후보', format=target_format)
                        data = {r['id']: r for r in (original, paid, free)}
                        acts = [{'id': 'original-act', 'stage': 2, 'title': '원본', 'res': 'original', 'hours': 1, 'how': '기존 활동'}]
                        if with_other_activity:
                            acts.append({'id': 'task', 'stage': 3, 'title': '유지할 실습', 'res': None, 'hours': 1, 'how': '직접 실습'})
                        plan = {'opt': pid, 'name': pid, 'short': pid, 'tagline': 'test', 'start': 1, 'hours': 4, 'acts': acts}
                        changes = {'replaceActs': [{'key': 'original-act', 'title': '원본'}], 'replaceHint': hint}
                        with self.subTest(pid=pid, hint=hint, paid_cost=paid_cost, multi=with_other_activity), patch.object(rm, '_cat', return_value=data):
                            result = rm._mock_revise({'pid': pid, 'plan': plan, 'handoff': self.handoff(), 'changes': changes})
                            expected = 'free-target' if pid == 'A1' else 'paid-target'
                            self.assertEqual([a['res'] for a in result['acts'] if a.get('res')], [expected])
                            self.assertEqual(len(result['acts']), len(acts))

    def test_filter_precedes_per_skill_limit_and_evidence_budget(self):
        pool={str(i):dict(self.resources()['paid'],id=str(i),title=f'AAA{i:02}') for i in range(28)}
        pool['free']=dict(self.resources()['free'],title='ZZZ')
        with patch.object(catalog,'items',return_value=pool), patch.object(catalog,'skills_for',return_value=['s']), patch.object(catalog_budget,'tokens',return_value=1):
            for pid in ('A1','A2','A3'):
                h=self.handoff(); h['prefs']['certRes']=None
                out=rm._track_catalog(pid,h)
                if pid=='A1':
                    self.assertEqual([r['id'] for r in out],['free'])
                else:
                    self.assertEqual(len(out),20)
                    self.assertNotIn('free',[r['id'] for r in out])

    def test_hints_and_existing_resources_filtered_before_pack(self):
        resources=self.resources()
        h=self.handoff(); h['resourceHints']=['paid','unknown','free']; h['skillNames']=['s']
        for pid in ('A1','A2','A3'):
            with self.subTest(pid=pid), patch.object(catalog,'items',return_value=resources), patch.object(catalog_budget,'tokens',return_value=1):
                out=rm._track_catalog(pid,h,['cert'])
                self.assertEqual({r['id'] for r in out},{'free','cert'} if pid=='A1' else set(resources))

    def test_confirmation_rejects_current_nonfree_missing_and_legacy(self):
        for price in (100,None,'missing'):
            for pid in ('A1','A2','A3'):
                with self.subTest(pid=pid,price=price):
                    t=Mock(); t.all.return_value=[] if price=='missing' else [{'resource_key':'free','cost_won':price}]
                    plan={'opt':pid,'acts':[{'res':'free'}],'cost':99,'costUnknown':True}
                    if pid=='A1':
                        with self.assertRaises(ApiError) as error: validate_free_plan(t,plan)
                        self.assertEqual(error.exception.status,409)
                        self.assertEqual(error.exception.code,'FREE_TRACK_PRICE_CHANGED')
                        self.assertEqual(plan['acts'],[{'res':'free'}])
                    else:
                        validate_free_plan(t,plan)
                        t.all.assert_not_called()
                        self.assertEqual(plan['cost'],99)

    def test_completed_legacy_paid_activity_is_rejected_with_guidance(self):
        t = Mock()
        t.all.return_value = [{'resource_key': 'old-paid', 'cost_won': 100}]
        plan = {'opt': 'A1', 'acts': [{'res': 'old-paid', 'done': True}], 'cost': 100}
        original = copy.deepcopy(plan)
        with self.assertRaises(ApiError) as error:
            validate_free_plan(t, plan)
        self.assertEqual(error.exception.code, 'FREE_TRACK_PRICE_CHANGED')
        self.assertIn('다시 생성', error.exception.message)
        self.assertIn('다른 Track', error.exception.message)
        self.assertEqual(plan, original)
    def test_soft_deleted_free_resource_is_rejected_without_plan_change(self):
        t = Mock()
        t.all.return_value = [{'resource_key': 'deleted-free', 'cost_won': 0, 'deleted': True}]
        plan = {'opt': 'A1', 'acts': [{'res': 'deleted-free'}], 'cost': 0}
        original = copy.deepcopy(plan)
        with self.assertRaises(ApiError) as error:
            validate_free_plan(t, plan)
        self.assertEqual(error.exception.code, 'FREE_TRACK_PRICE_CHANGED')
        self.assertEqual(plan, original)

    def test_activity_storage_uses_validated_free_cost_and_refreshes_catalog(self):
        for pid in ('A1', 'A2', 'A3'):
            plan = {'opt': pid, 'acts': [{'id': 'act', 'title': '자료', 'res': 'resource', 'stage': 2, 'hours': 1, 'wFrom': 1, 'wTo': 1}]}
            # 캐시가 잘못된 값을 반환해도 검증한 Free 활동 가격은 0으로 저장한다.
            resource = {'type': 'course', 'title': '자료', 'cost': 100}
            t = Mock()
            t.all.return_value = []
            t.val.return_value = 'step'
            with self.subTest(pid=pid), patch.object(catalog, 'items', return_value={'resource': resource}) as items:
                plans._write_steps(t, 'roadmap', plan)
                items.assert_called_once_with(refresh=pid == 'A1')
                self.assertEqual(t.val.call_args.kwargs['c'], 0 if pid == 'A1' else 100)

    def test_valid_free_uses_current_zero_and_keeps_activities(self):
        t=Mock(); t.all.return_value=[{'resource_key':'free','cost_won':0}]
        plan={'opt':'A1','acts':[{'res':'free'},{'res':None}],'cost':100,'costUnknown':True}
        validate_free_plan(t,plan)
        self.assertEqual(plan['cost'],0)
        self.assertFalse(plan['costUnknown'])
        self.assertEqual(len(plan['acts']),2)
        self.assertIn('FOR SHARE',t.all.call_args.args[0])

    def test_confirm_endpoint_checks_before_any_write(self):
        for cost in (0,100,None,'missing'):
            for pid in ('A1','A2','A3'):
                option={'id':pid,'name':pid,'short':pid,'tagline':'test','acts':[]}
                w={'draftPlan':{'exists':True},'draft':{'chosen':pid,'gen':{'options':{pid:option}},
                    'handoff':{},'goal':'test','quiz':{'questions':[],'domain':'test'},'answers':{},'prefs':{}}}
                t=Mock(); t.all.return_value=[] if cost=='missing' else [{'resource_key':'free','cost_won':cost}]
                plan={'opt':pid,'acts':[{'res':'free'}],'cost':100,'costUnknown':True}
                with self.subTest(pid=pid,cost=cost), ExitStack() as stack:
                    stack.enter_context(patch.object(drafts.db,'tx',side_effect=lambda:tx_of(t)))
                    stack.enter_context(patch.object(drafts,'_row',return_value={'draft_choices':w}))
                    stack.enter_context(patch.object(drafts,'_wrap',side_effect=lambda x:x))
                    stack.enter_context(patch.object(drafts,'_sync'))
                    stack.enter_context(patch.object(rm,'params_of',return_value={}))
                    stack.enter_context(patch.object(rm,'build_plan',return_value=plan))
                    stack.enter_context(patch.object(drafts,'deep_on',return_value=False))
                    round_=stack.enter_context(patch.object(drafts,'_round',return_value='round'))
                    insert=stack.enter_context(patch.object(plans,'insert_roadmap',return_value='saved'))
                    stack.enter_context(patch.object(plans,'shared_with',return_value=[]))
                    if pid=='A1' and cost!=0:
                        with self.assertRaises(ApiError): drafts.confirm(1,'draft')
                        insert.assert_not_called(); round_.assert_not_called(); t.run.assert_not_called()
                    else:
                        self.assertEqual(drafts.confirm(1,'draft')['planId'],'saved')
                        insert.assert_called_once()
                        if pid=='A1': self.assertEqual(plan['cost'],0)

    def test_revision_accept_checks_before_any_write(self):
        for cost in (0,100,None,'missing'):
            for pid in ('A1','A2','A3'):
                plan={'opt':pid,'def':{},'acts':[{'res':'free'}],'name':pid,'tagline':'test','cost':100}
                pd={'to':plan,'label':'test','prefsTo':{},'handoff':{}}
                row={'roadmap_id':'roadmap','content':{'opt':pid,'version':1}}
                t=Mock(); t.one.return_value={'result':pd,'status':'ready'}
                t.all.return_value=[] if cost=='missing' else [{'resource_key':'free','cost_won':cost}]
                with self.subTest(pid=pid,cost=cost), ExitStack() as stack:
                    stack.enter_context(patch.object(plans.db,'tx',side_effect=lambda:tx_of(t)))
                    stack.enter_context(patch.object(plans,'_owned',return_value=row))
                    stack.enter_context(patch.object(plans,'record',return_value={'ok':True}))
                    write=stack.enter_context(patch.object(plans,'_write_steps'))
                    if pid=='A1' and cost!=0:
                        with self.assertRaises(ApiError): plans.accept_revision(1,'roadmap','revision')
                        t.run.assert_not_called(); write.assert_not_called()
                    else:
                        self.assertEqual(plans.accept_revision(1,'roadmap','revision'),{'ok':True})
                        write.assert_called_once()
                        if pid!='A1': t.all.assert_not_called()

if __name__=='__main__':
    unittest.main()

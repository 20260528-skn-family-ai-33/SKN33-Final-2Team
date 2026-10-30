"""Free-only regressions from PR #41. No model calls or database writes."""
import copy
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import Mock, patch
from app import catalog, llm
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
                    'type':'cert' if kind=='자격' else 'course','stage':2,'skills':['s'],'usable':True}
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

    def test_filter_precedes_top_28_and_evidence_budget(self):
        pool={str(i):dict(self.resources()['paid'],id=str(i),title=f'AAA{i:02}') for i in range(28)}
        pool['free']=dict(self.resources()['free'],title='ZZZ')
        def pack(rows,texts):
            seen.append([r['id'] for r in rows])
            return rows
        with patch.object(catalog,'items',return_value=pool), patch.object(catalog,'skills_for',return_value=['s']), patch.object(catalog,'agent_views',side_effect=pack):
            for pid in ('A1','A2','A3'):
                seen=[]
                h=self.handoff(); h['prefs']['certRes']=None
                out=rm._track_catalog(pid,h)
                if pid=='A1':
                    self.assertEqual([r['id'] for r in out],['free'])
                    self.assertEqual(seen,[['free']])
                else:
                    self.assertEqual(len(out),28)
                    self.assertNotIn('free',[r['id'] for r in out])

    def test_hints_and_existing_resources_filtered_before_pack(self):
        resources=self.resources()
        h=self.handoff(); h['resourceHints']=['paid','unknown','free']
        for pid in ('A1','A2','A3'):
            with self.subTest(pid=pid), patch.object(catalog,'for_agent',return_value=[]), patch.object(rm,'_cat',return_value=resources), patch.object(catalog,'agent_views',side_effect=lambda rows,texts:rows):
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
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from app.agents import roadmap
from app.services import prompt_selection_store as store
from app.services.prompt_selection_metrics import summarize


class PromptSelectionStoreTests(TestCase):
    def setUp(self):
        self.generation = {'key':'generation','options':{course:{'id':course,'optionId':course+'-o','promptProvenance':{'promptVersionId':course+'-v','source':'ollama'}} for course in ('A1','A2','A3')}}
        self.displayed = [{'course':course,'optionId':course+'-o','promptVersionId':course+'-v'} for course in ('A1','A2','A3')]

    def test_intermediate_selection_is_not_counted_until_confirmation(self):
        snapshot = store.comparison_snapshot(self.generation,self.displayed)
        self.assertNotIn('eventType',snapshot)
        draft = {'chosen':'A3','gen':self.generation,'selectionComparison':snapshot}
        evidence = store.confirmation_evidence('project',draft)
        self.assertEqual(evidence['eventType'],'roadmap_confirmed')
        self.assertEqual(summarize([evidence])['eligibleDecisions'],1)

    def test_tampered_and_partial_display_do_not_block_legacy_flow_but_are_not_counted(self):
        for rows in (None,[],self.displayed[:2],self.displayed[:2]+[self.displayed[0]]):
            self.assertIsNone(store.comparison_snapshot(self.generation,rows))
        rows = deepcopy(self.displayed); rows[0]['promptVersionId']='fake'
        self.assertIsNone(store.comparison_snapshot(self.generation,rows))
        self.assertIsNone(store.confirmation_evidence('p',{'gen':self.generation,'chosen':'A1'}))

    def test_generation_or_option_change_invalidates_earlier_comparison(self):
        draft = {'chosen':'A1','gen':deepcopy(self.generation),'selectionComparison':store.comparison_snapshot(self.generation,self.displayed)}
        draft['gen']['options']['A2']['optionId']='regenerated'
        self.assertIsNone(store.confirmation_evidence('p',draft))
        draft['gen']=deepcopy(self.generation); draft['gen']['key']='new'
        self.assertIsNone(store.confirmation_evidence('p',draft))
        draft['gen']=deepcopy(self.generation); draft['gen']['regenRun']={'A3':{'jobId':'job'}}
        self.assertIsNone(store.confirmation_evidence('p',draft))

    def test_snapshot_does_not_follow_later_changes(self):
        snapshot = store.comparison_snapshot(self.generation,self.displayed)
        self.generation['options']['A1']['promptProvenance']['promptVersionId']='new'
        self.assertEqual(snapshot['displayed'][0]['promptVersionId'],'A1-v')

    def test_reader_only_selects_confirmed_rows_with_existing_evidence(self):
        with patch.object(store.db,'all_',return_value=[{'evidence':{'eventType':'roadmap_confirmed'}},{'evidence':None}]) as read:
            self.assertEqual(len(store.read_decisions()),1)
        self.assertIn('selected_at IS NOT NULL',read.call_args.args[0])
        self.assertIn("baseline_content -> 'selectionEvidence'", read.call_args.args[0])
        self.assertIn("baseline_content ? 'selectionEvidence'", read.call_args.args[0])
        self.assertTrue(read.call_args.args[0].startswith('SELECT '))

    def test_generation_captures_actual_db_version_and_effective_prompt_hash(self):
        prompt='### GENERATION\n현재 계획 지시문\n### REVISION\n수정 지시문'
        with patch.object(roadmap.db,'all_',return_value=[{'prompt_version_id':'version-id','system_prompt':prompt}]), \
             patch.object(roadmap,'_catalog_payload',side_effect=lambda pid,value,*args:value), \
             patch.object(roadmap.catalog,'skill_names',return_value=[]), \
             patch.object(roadmap.rt,'llm_json',return_value={'acts':[]}), \
             patch.object(roadmap,'finish_option',side_effect=lambda *args,**kwargs:{'id':'A1','acts':[]}), \
             patch.object(roadmap.rt,'run',side_effect=lambda ctx,name,task,inp,mock,api,**kw:api(None)):
            first=roadmap.option(SimpleNamespace(mode='ollama'),{'pid':'A1','handoff':{'goal':'조회'}})
            second=roadmap.option(SimpleNamespace(mode='ollama'),{'pid':'A1','handoff':{'goal':'조회'}})
        self.assertEqual(first['promptProvenance']['promptVersionId'],'version-id')
        self.assertEqual(first['promptProvenance']['source'],'ollama')
        self.assertEqual(len(first['promptProvenance']['effectivePromptHash']),64)
        self.assertNotEqual(first['optionId'],second['optionId'])
        self.assertNotIn('systemPrompt',first['promptProvenance'])

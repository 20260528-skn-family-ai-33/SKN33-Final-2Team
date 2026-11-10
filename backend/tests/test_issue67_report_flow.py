"""가상 5스킬의 사전·사후 응답 → 보고서 입력·저장 계약 검사."""
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
from test_issue67_scenarios import scenario
from app.services import plans

class Issue67ReportTests(TestCase):
    def test_five_skill_evidence_reaches_model_and_is_saved_without_live_database(self):
        saved=scenario(5)['saved']
        survey=saved['survey'];questions=[]
        for group in survey['groups']:
            for q in group['surveys']:
                questions.append({'id':q['id'],'area':group['skill'],'skill':group['skill'],'text':q['text']})
        assess={'domain':'가상 공개 규정 검색','questions':questions,'answers':{q['id']:str(saved['answers'][q['id']]) for q in questions},'v2':{'survey':deepcopy(survey),'answers':deepcopy(saved['answers'])}}
        plan={'version':1,'goal':saved['project']['goal'],'name':'가상 검증 계획','opt':'A3','assess':assess,'handoff':saved['project'],'acts':[{'id':str(i),'skill':g['skill'],'title':g['skill']+' 검증','how':'공개 예제 입력·출력 대조','res':None} for i,g in enumerate(survey['groups'])]}
        post_survey=deepcopy(survey)
        post_answers={q['id']:str((q['answer']+1)%5) for g in post_survey['groups'] for q in g['quizzes']}
        for g in post_survey['groups']:
            for q in g['quizzes']:q['answer']=(q['answer']+1)%5
        post={'answers':{q['id']:'5' for q in questions},'quizAnswers':post_answers,'goalSelf':'1'}
        progress={'0':{'status':'done','memo':'모의 실행 근거','file':{'name':'synthetic.txt'}}}
        row={'roadmap_id':'p','project_id':1,'diagnostic_round_id':1,'content':plan}
        tx=Mock();tx.one.side_effect=[None,{'content':plan}];tx.val.side_effect = lambda sql, **kw: 'IN_PROGRESS' if 'SELECT status::text' in sql else 'report'
        tx.all.side_effect=lambda sql,**kw: [{'activity_id':key,'status':item['status'],'memo':item['memo'],'attachment':item['file']} for key,item in progress.items()] if 'activity_progress' in sql else []
        captured={}
        def model(ctx,system,payload,**kw):
            captured.update(deepcopy(payload))
            return {'good':['모의 결과'],'improve':['실제 모델 품질 검증 필요'],'next':{'goal':'추가 검증','why':'모의 흐름'}}
        with ExitStack() as stack:
            for target,name,value in [(plans,'_owned',row),(plans,'record',{'plan':plan,'post':post,'progress':progress}),(plans,'_report_deep',None),(plans.db,'one',{'deep':{'v2Quiz':post_survey}}),(plans.db,'val',{}),(plans.rt,'context',SimpleNamespace(mode='openai')),(plans.rt,'sim_once',None)]:
                stack.enter_context(patch.object(target,name,return_value=value))
            stack.enter_context(patch.object(plans.db,'J',side_effect=lambda x:x))
            transaction=stack.enter_context(patch.object(plans.db,'tx'));transaction.return_value.__enter__.return_value=tx
            stack.enter_context(patch.object(plans.jobs,'start',side_effect=lambda kind,e,ref,work:work(SimpleNamespace(job_id='j')) and 'j'))
            stack.enter_context(patch.object(plans.rt,'llm_json',side_effect=model))
            stack.enter_context(patch.object(plans.rt,'run',side_effect=lambda ctx,name,task,inp,mock,api,**kw:api(None)))
            plans.report_start(1,'p')
        report=next(c.kwargs['c'] for c in tx.val.call_args_list if 'c' in c.kwargs)
        self.assertEqual(len(captured['items']),15)
        self.assertEqual(len(report['surveyEvidence']),15)
        self.assertEqual(len(captured['quizEvidence']),15)
        self.assertTrue(all(q['post']=='정답' for q in captured['quizEvidence']))
        self.assertEqual(len(captured['completed']),1)
        self.assertEqual(len(captured['notCompleted']),4)
        self.assertFalse(captured['executionEvidence']['activities'][0]['attachmentContentVerified'])
        self.assertEqual(len(report['executionSnapshot']['activities']),5)
        post['answers'][questions[0]['id']]='1'
        self.assertEqual(report['surveyEvidence'][0]['post'],'5')
    def test_post_answers_are_saved_by_question_sequence_and_quiz_ids(self):
        saved=scenario(5)['saved'];survey=saved['survey']
        qs=[{'id':q['id'],'area':g['skill'],'skill':g['skill'],'text':q['text']} for g in survey['groups'] for q in g['surveys']]
        quiz={q['id']:str(q['answer']) for g in survey['groups'] for q in g['quizzes']}
        plan={'assess':{'questions':qs,'v2':{'survey':survey,'answers':saved['answers']}}}
        row={'roadmap_id':'p','status':'IN_PROGRESS','project_id':1,'diagnostic_round_id':1,'content':plan}
        tx=Mock();tx.all.side_effect=[[{'question_id':q['id'],'sequence_no':i,'question':q['text'],'skill':q['skill'],'options':[]} for i,q in enumerate(qs,1)],[{'sequence_no':i,'question_id':'post-'+str(i)} for i in range(1,16)]]
        answers={q['id']:str(i%5+1) for i,q in enumerate(qs)}
        with patch.object(plans,'_owned',return_value=row),patch.object(plans,'record',return_value={'post':True}),patch.object(plans.db,'one',return_value={'deep':{'v2Quiz':survey}}),patch.object(plans.db,'J',side_effect=lambda x:x),patch.object(plans.db,'tx') as transaction:
            transaction.return_value.__enter__.return_value=tx
            plans.save_post(1,'p',{'answers':answers,'quizAnswers':quiz,'goalSelf':'1'})
        writes=[c.kwargs for c in tx.run.call_args_list if 'assessment_responses' in c.args[0]]
        self.assertEqual(len(writes),15)
        self.assertEqual([c['q'] for c in writes],['post-'+str(i) for i in range(1,16)])
        self.assertEqual([c['s'] for c in writes],[int(answers[q['id']]) for q in qs])
        self.assertEqual(next(c.kwargs['answers'] for c in tx.run.call_args_list if 'v2Answers' in c.args[0]),quiz)

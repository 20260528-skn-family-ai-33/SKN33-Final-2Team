import copy
import unittest
from app.services.assessment_context import compact, VERSION

class AssessmentContextTests(unittest.TestCase):
    def sample(self):
        return {'groups':[{'skill':'SQL', 'title':'설문 제목',
            'surveys':[{'id':'s','text':'조인 결과를 검증할 수 있다.'}],
            'quizzes':[{'id':'q','q':'질문 원문','concept':'조인 행 증가','questionType':'원인 판단','difficulty':'적용',
                        'options':['정답','오답','다른 보기'],'answer':0,'explain':'키 중복 확인'}]}],
            'answers':{'s':5,'q':1}}

    def test_wrong_answer_keeps_measurement_and_evidence_without_raw_choices(self):
        source=self.sample(); before=copy.deepcopy(source); out=compact(source)
        self.assertEqual(out['version'],VERSION)
        self.assertEqual(out['skills'][0]['surveys'],[{'measure':'조인 결과를 검증할 수 있다.','selfRating':5}])
        q=out['skills'][0]['quizzes'][0]
        self.assertEqual(q,dict(concept='조인 행 증가',questionType='원인 판단',difficulty='적용',result='incorrect',
                                selectedAnswer='오답',correctAnswer='정답',reason='키 중복 확인'))
        self.assertEqual(source,before)
        self.assertNotIn('answers',out)

    def test_correct_unanswered_and_zero_index_are_distinct(self):
        for answer,status in ((0,'correct'),(None,'unanswered')):
            source=self.sample();source['answers']['q']=answer
            q=compact(source)['skills'][0]['quizzes'][0]
            self.assertEqual(q['result'],status)
            self.assertEqual('reason' in q,status!='correct')
            if answer is None:self.assertIsNone(q['selectedAnswer'])

    def test_legacy_concept_falls_back_to_question(self):
        source=self.sample();source['groups'][0]['quizzes'][0].pop('concept')
        self.assertEqual(compact(source)['skills'][0]['quizzes'][0]['concept'],'질문 원문')

    def test_unknown_or_invalid_form_preserves_whole_original(self):
        for value in (-1,True,99,'0'):
            source=self.sample();source['answers']['q']=value
            self.assertEqual(compact(source),source)
        for source in ({},None,{'groups':[],'answers':{}},{'groups':[{}],'answers':{}}):
            self.assertEqual(compact(source),source)

    def test_all_skills_and_item_order_kept_and_idempotent(self):
        source=self.sample()
        for i in range(1,5):
            group=copy.deepcopy(source['groups'][0]);group['skill']=str(i);group['surveys'][0]['id']='s'+str(i);group['quizzes'][0]['id']='q'+str(i);source['groups'].append(group)
        out=compact(source)
        self.assertEqual([s['skill'] for s in out['skills']],['SQL','1','2','3','4'])
        self.assertEqual(compact(out),out)

    def test_unrecognized_evidence_is_not_silently_discarded(self):
        source=self.sample();source['essays']=[{'text':'추가 근거'}]
        self.assertEqual(compact(source),source)
        source=self.sample();source['groups'][0]['quizzes'][0]['extraEvidence']='추가 근거'
        self.assertEqual(compact(source),source)
        source=self.sample();source['answers']['unknown']=3
        self.assertEqual(compact(source),source)

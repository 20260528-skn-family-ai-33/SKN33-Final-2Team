import unittest
from copy import deepcopy
from app.errors import ApiError
from app.services.post_quiz import validate,comparison,public_assessment

class PostQuizTests(unittest.TestCase):
    def test_parallel_quiz_preserves_measurement_and_original_survey(self):
        from app.services.post_quiz import generate
        self.plan['goal']='SQL 프로젝트'
        group=self.plan['assess']['v2']['survey']['groups'][0]
        group['surveys']=[{'id':'s','text':'중복 조인을 검증할 수 있다.'}]
        measurement={'concept':'일대다 조인의 행 증가','questionType':'오류 원인 판단','difficulty':'적용'}
        group['quizzes'][0].update(measurement)
        original=deepcopy(self.plan)
        row={'id':'q','skill':'SQL','q':'주문 조인 후 행이 늘어난 원인은?',
             'options':['a','b','c','d','e'],'answer':1,'explain':'일대다 관계 때문이다.',**measurement}
        result=generate(self.plan,lambda *_:{'quizzes':[row]})
        self.assertEqual(self.plan,original)
        self.assertEqual(result['groups'][0]['surveys'],[])
        self.assertEqual(result['groups'][0]['quizzes'][0]['concept'],measurement['concept'])
        for key in measurement:
            bad=deepcopy(row);bad[key]='다른 기준'
            with self.subTest(key=key), self.assertRaises(ApiError):
                generate(self.plan,lambda *_:{'quizzes':[bad]})

    def test_whitespace_only_rewording_and_duplicate_choices_are_rejected(self):
        from app.services.post_quiz import generate
        self.plan['goal']='SQL 프로젝트'
        row={'id':'q','skill':'SQL','q':'조인   구문','options':['a','b','c','d','e'],'answer':1,'explain':'근거'}
        with self.assertRaises(ApiError):generate(self.plan,lambda *_:{'quizzes':[row]})
        row.update(q='새로운 조인 상황',options=['a',' a ','c','d','e'])
        with self.assertRaises(ApiError):generate(self.plan,lambda *_:{'quizzes':[row]})

    def setUp(self):
        self.plan={'assess':{'v2':{'survey':{'groups':[{'skill':'SQL','quizzes':[{'id':'q','q':'조인 구문','options':['JOIN','DROP'],'answer':0,'explain':'근거'}]}]},'answers':{'q':1}}}}
    def test_zero_answer_is_valid_and_required(self):
        self.assertEqual(validate(self.plan,{'q':'0'},True),{'q':'0'})
        for answers in ({},{'q':'2'},{'other':0},{'q':False}):
            with self.assertRaises(ApiError):validate(self.plan,answers,True)
    def test_pre_post_comparison(self):
        row=comparison(self.plan,{'q':'0'})[0]
        self.assertEqual((row['pre'],row['post']),('오답','정답'))
    def test_public_questions_hide_answer_without_mutation(self):
        self.plan['assess']['v2']['survey']['groups'][0]['quizzes'][0]['concept']='조인 관계'
        value=public_assessment(self.plan['assess'])
        self.assertNotIn('answer',value['v2']['survey']['groups'][0]['quizzes'][0])
        self.assertNotIn('concept',value['v2']['survey']['groups'][0]['quizzes'][0])
        revealed=public_assessment(self.plan['assess'],reveal=True)
        self.assertEqual(revealed['v2']['survey']['groups'][0]['quizzes'][0]['answer'],0)
        self.assertEqual(revealed['v2']['survey']['groups'][0]['quizzes'][0]['explain'],'근거')
        self.assertNotIn('concept',revealed['v2']['survey']['groups'][0]['quizzes'][0])
        self.assertEqual(self.plan['assess']['v2']['survey']['groups'][0]['quizzes'][0]['answer'],0)
    def test_legacy_plan_has_no_required_v2_quiz(self):
        self.assertEqual(validate({'assess':{}},{},True),{})

    def test_new_quiz_keeps_ids_and_rejects_repeated_question(self):
        from app.services.post_quiz import generate
        row={'id':'q','skill':'SQL','q':'새 조인 상황','options':['a','b','c','d','e'],'answer':1,'explain':'근거'}
        self.plan['goal']='SQL 프로젝트'
        result=generate(self.plan,lambda *_:{'quizzes':[row]})
        self.assertEqual(result['groups'][0]['quizzes'][0]['id'],'q')
        self.assertEqual(comparison(self.plan,{'q':'1'},result)[0]['post'],'정답')
        row['q']='조인 구문'
        with self.assertRaises(ApiError):generate(self.plan,lambda *_:{'quizzes':[row]})

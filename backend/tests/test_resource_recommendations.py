import copy
import unittest
from unittest.mock import Mock
from app.agents.resource_recommendations import RecommendationError, candidate_pools, recommend_resources, validate_choices

class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.project = {'goal': '수질 데이터 분석', 'projectSummary': None, 'desiredCompetencies': '전처리'}
        self.selection = {'skills': [{'name': '분석', 'application': '분석 구현'}]}
        self.items = {f'{kind}{i}': {'id': f'{kind}{i}', 'title': f'자료 {i}', 'type': kind,
                      'usable': True, 'skills': ['분석'], 'cost': i, 'content': '목차 근거'}
                      for kind in ('course', 'book') for i in range(4)}
    def raw(self):
        return {'skills': [dict(name='분석', **{kind: [{'id': f'{prefix}{i}', 'why': '프로젝트 관련 자료', 'knowledge': '데이터 처리 지식'} for i in range(3)]
                            for kind, prefix in [('courses', 'course'), ('books', 'book')]})]}
    def recommend(self, raw=None, items=None):
        return recommend_resources(self.project, self.selection, self.items if items is None else items, lambda *_: self.raw() if raw is None else raw)
    def test_top_recommendation_and_one_book_default(self):
        row=self.recommend()['skills'][0]
        self.assertEqual(row['selectedCourse'],'course0')
        self.assertEqual(row['selectedBooks'],['book0'])
        self.assertEqual([r['aiRecommended'] for r in row['courses']],[True,False,False])
    def test_unrelated_and_unusable_resources_filtered_before_limit(self):
        items={f'bad{i}':dict(self.items['course0'],id=f'bad{i}',title='AAA',skills=['다른스킬']) for i in range(30)}
        items['free']=dict(self.items['course0'],id='free',title='ZZZ')
        items['deleted']=dict(self.items['book0'],id='deleted',usable=False)
        pool=candidate_pools(self.project,self.selection,items,limit=1)[0]
        self.assertEqual([r['id'] for r in pool['courses']],['free'])
        self.assertEqual(pool['books'],[])
    def test_missing_resources_remain_empty_without_model_call(self):
        model=Mock()
        result=recommend_resources(self.project,self.selection,{},model)
        self.assertEqual(result['skills'][0]['selectedBooks'],[])
        self.assertIsNone(result['skills'][0]['selectedCourse'])
        model.assert_not_called()
    def test_fewer_than_three_resources_not_padded(self):
        raw=self.raw();raw['skills'][0]['books']=raw['skills'][0]['books'][:1]
        result=self.recommend(raw)
        self.assertEqual(len(result['skills'][0]['books']),1)
    def test_wrong_type_unknown_duplicate_and_more_than_three_rejected(self):
        bad=[]
        raw=self.raw();raw['skills'][0]['courses'][0]['id']='book0';bad.append(raw)
        raw=self.raw();raw['skills'][0]['courses'][0]['id']='invented';bad.append(raw)
        raw=self.raw();raw['skills'][0]['courses'][1]=copy.deepcopy(raw['skills'][0]['courses'][0]);bad.append(raw)
        raw=self.raw();raw['skills'][0]['courses'].append({'id':'course3','why':'이유','knowledge':'지식'});bad.append(raw)
        for raw in bad:
            with self.subTest(raw=raw),self.assertRaises(RecommendationError):self.recommend(raw)
    def test_course_one_and_book_max_three_validation(self):
        result=self.recommend()
        validate_choices(result,{'분석':{'course':'course0','books':['book0','book1','book2']}})
        for course,books in [(['course0','course1'],[]),('course0',['book0']*2),('course0',['book0','book1','book2','book3']),('course0',['unknown'])]:
            with self.subTest(course=course,books=books),self.assertRaises(RecommendationError):
                validate_choices(result,{'분석':{'course':course,'books':books}})
    def test_raw_document_and_personal_data_not_added_to_model_payload(self):
        project=dict(self.project,rawText='원문',profile={'name':'개인정보'})
        model=Mock(return_value=self.raw())
        recommend_resources(project,self.selection,self.items,model)
        payload=model.call_args.args[1]
        self.assertNotIn('rawText',payload['project'])
        self.assertNotIn('profile',payload['project'])

    def test_null_curriculum_items_still_allows_recommendation(self):
        items=copy.deepcopy(self.items)
        for row in items.values(): row['curriculum']={'items':None}
        model=Mock(return_value=self.raw())
        result=recommend_resources(self.project,self.selection,items,model)
        self.assertEqual(len(result['skills'][0]['courses']),3)
        self.assertEqual(model.call_args.args[1]['skills'][0]['courses'][0]['outline'],[])

    def test_short_reference_keys_map_only_to_their_skill_and_kind(self):
        def model(_, payload):
            rows=payload['skills'][0]
            return {'skills':[dict(name='분석',**{key:[{'key':row['choiceKey'],'why':'이유','knowledge':'지식'} for row in rows[key][:3]] for key in ('courses','books')})]}
        result=recommend_resources(self.project,self.selection,self.items,model)
        self.assertEqual(result['skills'][0]['courses'][0]['id'],'course0')
        raw=self.raw();raw['skills'][0]['courses'][0]={'key':'S1-B1','why':'이유','knowledge':'지식'}
        with self.assertRaises(RecommendationError):self.recommend(raw)

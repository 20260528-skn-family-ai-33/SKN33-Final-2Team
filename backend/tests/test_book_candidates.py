"""공통 도서 30권의 중복·범위·입력 크기와 공유 자료 키의 권한 경계를 검증한다."""
from copy import deepcopy
import unittest
from app.services import book_candidates as books
from app.agents.resource_recommendations import recommend_resources, RecommendationError


def item(key, skills, kind='book', **extra):
    return {'id':key,'type':kind,'usable':True,'skills':skills,'title':key,'cost':100,'hours':2,
            'content':'학습 설명 '+('소개 '*1000),**extra}


class BookCandidateTests(unittest.TestCase):
    def test_thirty_unique_books_are_balanced_across_skills_and_rare_skill_is_kept(self):
        items={f'b{i}':item(f'b{i}',['ML']) for i in range(50)}
        items['rare']=item('rare',['ETL'])
        pools=[{'name':'ML','courses':[],'books':list(items.values())[:-1]},
               {'name':'ETL','courses':[],'books':[items['rare']]}]
        before=deepcopy(pools)
        selected,catalog=books.common_pool(pools,items,limit=30)
        self.assertEqual(len(catalog),30)
        self.assertEqual(len({r['id'] for r in catalog}),30)
        self.assertIn('rare',{r['id'] for r in catalog})
        self.assertEqual([r['id'] for r in selected[1]['books']],['rare'])
        self.assertEqual(pools,before)

    def test_shared_book_metadata_appears_once_and_uses_actual_selected_tags(self):
        row=item('shared',['RAG','NLP','unselected'])
        pools=[{'name':name,'courses':[],'books':[row]} for name in ('RAG','NLP')]
        selected,catalog=books.common_pool(pools,{'shared':row})
        payload=books.model_catalog(catalog,{'shared':row},['RAG','NLP'])
        self.assertEqual(len(payload),1)
        self.assertEqual(payload[0]['eligibleSkills'],['RAG','NLP'])
        self.assertLessEqual(len(payload[0]['content']),books.DESCRIPTION_CHARS)
        self.assertNotIn('id',payload[0])
        self.assertEqual(selected[0]['books'][0]['id'],selected[1]['books'][0]['id'])

    def test_book_retrieved_for_other_skill_can_be_shared_only_by_actual_tags(self):
        row=item('rag',['RAG','Python'])
        pools=[{'name':'RAG','courses':[],'books':[row]},
               {'name':'Python','courses':[],'books':[]}, {'name':'NLP','courses':[],'books':[]}]
        selected,catalog=books.common_pool(pools,{'rag':row})
        self.assertEqual([r['id'] for r in selected[1]['books']],['rag'])
        self.assertTrue(selected[1]['books'][0]['sharedCandidate'])
        self.assertNotIn('retrievalScore',selected[1]['books'][0])
        self.assertEqual(selected[2]['books'],[])

    def test_model_reads_common_book_catalog_and_returns_shared_key(self):
        row=item('same',['RAG','NLP'])
        pools=[{'name':n,'application':n,'courses':[],'books':[row]} for n in ('RAG','NLP')]
        def generate(system,payload):
            self.assertEqual(len(payload['bookCatalog']),1)
            self.assertEqual(payload['skills'][0]['books'],[{'choiceKey':'B1'}])
            self.assertNotIn('content',payload['skills'][0]['books'][0])
            return {'skills':[{'name':n,'courses':[],'books':[{'key':'B1'}]} for n in ('RAG','NLP')]}
        result=recommend_resources({'goal':'RAG'},{'skills':[{'name':'RAG'},{'name':'NLP'}]}, {'same':row},generate,
                                   course={'id':'A3'},retrieved_pools=pools)
        self.assertEqual([p['selectedBooks'] for p in result['skills']],[['same'],['same']])

    def test_course_reference_from_another_pool_requires_actual_target_tag(self):
        row=item('course',['RAG','NLP'],kind='course',cost=0)
        pools=[{'name':'RAG','courses':[],'books':[]},{'name':'NLP','courses':[row],'books':[]}]
        raw={'skills':[{'name':'RAG','courses':[{'key':'S2-C1'}],'books':[]},
                       {'name':'NLP','courses':[{'key':'S2-C1'}],'books':[]}]}
        result=recommend_resources({'goal':'RAG'},{'skills':[{'name':'RAG'},{'name':'NLP'}]}, {'course':row},lambda *_:raw,
                                   course={'id':'A3'},retrieved_pools=pools)
        self.assertEqual(result['skills'][0]['selectedCourse'],'course')
        self.assertTrue(result['skills'][0]['courses'][0]['sharedCandidate'])
        changed=deepcopy(row);changed['skills']=['NLP']
        with self.assertRaises(RecommendationError):
            recommend_resources({'goal':'RAG'},{'skills':[{'name':'RAG'},{'name':'NLP'}]}, {'course':changed},lambda *_:raw,
                                course={'id':'A3'},retrieved_pools=pools)

    def test_shared_book_cannot_be_borrowed_into_an_unlinked_skill_or_wrong_kind(self):
        row=item('only-rag',['RAG'])
        pools=[{'name':'RAG','courses':[],'books':[row]},{'name':'NLP','courses':[],'books':[]}]
        for raw in ({'skills':[{'name':'RAG','courses':[],'books':[]},{'name':'NLP','courses':[],'books':[{'key':'B1'}]}]},
                    {'skills':[{'name':'RAG','courses':[{'key':'B1'}],'books':[]},{'name':'NLP','courses':[],'books':[]}]}):
            with self.assertRaises(RecommendationError):
                recommend_resources({'goal':'RAG'},{'skills':[{'name':'RAG'},{'name':'NLP'}]}, {'only-rag':row},lambda *_:raw,
                                    course={'id':'A3'},retrieved_pools=pools)

    def test_duplicate_aliases_of_the_same_resource_are_still_rejected(self):
        row=item('same',['RAG'])
        raw={'skills':[{'name':'RAG','courses':[],'books':[{'key':'B1'},{'key':'B1'}]}]}
        with self.assertRaises(RecommendationError):
            recommend_resources({'goal':'RAG'},{'skills':[{'name':'RAG'}]}, {'same':row},lambda *_:raw,
                                course={'id':'A1'},retrieved_pools=[{'name':'RAG','courses':[],'books':[row]}])

    def test_two_course_aliases_do_not_duplicate_one_resource_within_one_skill(self):
        row=item('same',['RAG','NLP'],kind='course')
        pools=[{'name':name,'courses':[row],'books':[]} for name in ('RAG','NLP')]
        raw={'skills':[{'name':'RAG','courses':[{'key':'S1-C1'},{'key':'S2-C1'}],'books':[]},
                       {'name':'NLP','courses':[],'books':[]}]}
        with self.assertRaises(RecommendationError):
            recommend_resources({'goal':'RAG'},{'skills':[{'name':'RAG'},{'name':'NLP'}]}, {'same':row},lambda *_:raw,
                                course={'id':'A3'},retrieved_pools=pools)

    def test_same_course_has_one_key_across_skills_and_can_be_selected_once_for_each(self):
        row=item('same',['RAG','NLP'],kind='course')
        pools=[{'name':name,'courses':[row],'books':[]} for name in ('RAG','NLP')]
        def generate(system,payload):
            keys=[p['courses'][0]['choiceKey'] for p in payload['skills']]
            self.assertEqual(keys,['S1-C1','S1-C1'])
            return {'skills':[{'name':p['name'],'courses':[{'key':keys[0]}],'books':[]} for p in payload['skills']]}
        result=recommend_resources({'goal':'RAG'},{'skills':[{'name':'RAG'},{'name':'NLP'}]}, {'same':row},generate,
                                   course={'id':'A3'},retrieved_pools=pools)
        self.assertEqual([p['selectedCourse'] for p in result['skills']],['same','same'])

    def test_book_thirty_uses_one_search_and_one_embedding_without_a_free_price_filter(self):
        from unittest.mock import Mock
        from app.services import resource_rag as rag
        items={f'book_{i}':item(f'book_{i}',['RAG']) for i in range(40)}
        search=Mock(side_effect=lambda kind,ids,vector,limit,free:
                    [{'resource_id':str(i),'similarity':.8,'current_cost':100} for i in range(limit)])
        embed=Mock(side_effect=lambda texts:[[1.]+[0.]*(rag.DIMENSIONS-1) for _ in texts])
        pools,meta=rag.retrieve({'goal':'RAG'},{'skills':[{'name':'RAG'}]},items,{'id':'A1'},embed=embed,search=search)
        self.assertEqual(len(pools[0]['books']),30)
        self.assertEqual(search.call_count,1)
        self.assertEqual(search.call_args.args[3],30)
        self.assertFalse(search.call_args.args[4])
        embed.assert_called_once()
        self.assertEqual(meta['maxUniqueBooks'],books.LIMIT)


if __name__=='__main__':unittest.main()

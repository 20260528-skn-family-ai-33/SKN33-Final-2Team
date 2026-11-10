from datetime import datetime, timezone, timedelta
from unittest import TestCase
from unittest.mock import patch

from src.shared.skill_matching import SkillMatcher
from src.database.ingestion.real_data_ingestor import RealDataIngestor, SourceError
from src.database.ingestion import catalog_details

SKILLS=[{'skill_id':1,'name':'SQL 기본 문법 & 조인','category':'IT'}]

def ing():
    obj=RealDataIngestor(config={'library':{'base_url':'https://data4library.kr/api/srchBooks',
        'max_pages':1,'page_size':50},'ingestion':{'book_keywords':['데이터베이스']},
        'kmooc':{'detail_url':'https://apis.data.go.kr/B552881/kmooc_v2_0/courseDetail_v2_0'}})
    obj.matcher=SkillMatcher(SKILLS,rules={'SQL 기본 문법 & 조인':['SQL']})
    return obj

class CatalogExpansionTests(TestCase):
    def test_resource_images_use_only_official_payload_urls(self):
        image=catalog_details.resource_image_url
        self.assertEqual(image('courses','API_KMOOC',{'course_image':'https://example.org/course.jpg'}),'https://example.org/course.jpg')
        self.assertEqual(image('courses','API_MS_LEARN',{'social_image_url':'javascript:bad','icon_url':'https://example.org/icon.svg'}),'https://example.org/icon.svg')
        self.assertEqual(image('books','API_DATA4LIBRARY',{'detail_record':{'bookImageURL':'https://example.org/book.jpg'}}),'https://example.org/book.jpg')
        self.assertEqual(image('certifications','API_MS_CERT',{'certification':{'icon_url':'https://example.org/badge.svg'}}),'https://example.org/badge.svg')
        self.assertIsNone(image('books','API_DATA4LIBRARY',{}))
        self.assertIsNone(image('jobs','API_CAREERNET',{'icon_url':'https://example.org/icon.svg'}))
        self.assertIsNone(image('courses','API_KMOOC',{'course_image':'https://user:password@example.org/a.jpg'}))

    def test_description_can_match_without_title_keyword(self):
        obj=ing()
        row=obj._record('books','API_DATA4LIBRARY','123',
            {'title':'현업의 문제 해결','description':'SQL 조인과 PostgreSQL 실습'}, {})
        self.assertIn(1,row['matches'])

    def test_zero_limit_keeps_all_matches(self):
        obj=ing()
        rows=[{'source':'real','external_key':str(i),'matches':{1:['SQL']}} for i in range(6)]
        self.assertEqual(len(obj._select('courses',rows,0)),6)
        self.assertFalse(obj.selection_reports['courses']['limit_reached'])

    def test_detail_is_fetched_before_book_skill_filter(self):
        obj=ing()
        with patch.object(obj,'_key',return_value='test'), patch.object(obj,'_request',return_value={
            'response':{'numFound':1,'docs':[{'doc':{'isbn13':'9781234567890','bookname':'현업의 문제 해결'}}]}}) as request:
            with patch.object(catalog_details,'enrich_books',side_effect=lambda _,rows: rows) as detail:
                rows=obj.fetch_books_from_api(1)
        self.assertEqual(len(detail.call_args.args[1]),1)
        self.assertFalse(rows[0]['matches'])
        self.assertIn('keyword',request.call_args.args[1])
        self.assertNotIn('title',request.call_args.args[1])

    def test_list_quota_failure_keeps_completed_candidates(self):
        obj=ing();obj.config['ingestion']['book_keywords']=['SQL','데이터베이스']
        data={'response':{'numFound':1,'docs':[{'doc':{'isbn13':'9781234567890','bookname':'SQL 실무'}}]}}
        with patch.object(obj,'_key',return_value='test'), patch.object(obj,'_request',side_effect=[data,SourceError('LIBRARY_REQUEST_BUDGET_REACHED')]):
            with patch.object(catalog_details,'enrich_books',side_effect=lambda _,rows: rows):
                rows=obj.fetch_books_from_api(10)
        self.assertEqual(len(rows),1)
        self.assertEqual(obj.reports['library']['status'],'INCOMPLETE')

    def test_page_size_follows_actual_total_not_requested_size(self):
        obj=ing();obj.max_pages=10
        payloads=[{'resultCode':'00','items':[{'id':'first'}],'totalCount':2},
                  {'resultCode':'00','items':[{'id':'second'}],'totalCount':2}]
        payloads[0]['items'][0]['id']='first'
        with patch.object(obj,'_request',side_effect=payloads) as request:
            rows=obj._pages('kmooc','https://apis.data.go.kr/list',{},page_key='Page',size_key='Size',size=50,list_key='items')
        self.assertEqual(len(rows),2)
        self.assertEqual(request.call_args.args[1]['Page'],2)
        self.assertFalse(obj.reports['kmooc']['page_limit_reached'])

    def test_kmooc_detail_rejects_generic_title(self):
        obj=ing();now=datetime.now(timezone.utc)
        raw={'id':'123','public_yn':'Y','enrollment_start':(now-timedelta(days=1)).isoformat(),
             'enrollment_end':(now+timedelta(days=1)).isoformat(),'study_end':(now+timedelta(days=2)).isoformat()}
        row=obj._record('courses','API_KMOOC','123',{'title':'현업의 문제 해결','url':'https://www.kmooc.kr/x',
            'org_name':'실제 대학'},raw)
        with patch.object(obj,'_key',return_value='test'),patch.object(obj,'_request',return_value={
            'resultCode':'00','results':{**raw,'summary':'SQL 조인과 인덱스를 직접 작성하여 데이터베이스 성능을 개선합니다.','week':'5'}}) as request:
            rows=catalog_details.enrich_kmooc(obj,[row])
        valid=catalog_details.finalize(obj,'courses',rows)
        self.assertEqual(valid,[])  # No explicit IT subject/title: keyword mention is insufficient.
        self.assertEqual(request.call_args.args[1]['CourseId'],'123')

    def test_closed_kmooc_not_fetched(self):
        obj=ing()
        row=obj._record('courses','API_KMOOC','closed',{'title':'SQL 실습'},{'public_yn':'N'})
        with patch.object(obj,'_key',return_value='test'),patch.object(obj,'_request') as request:
            self.assertEqual(catalog_details.enrich_kmooc(obj,[row]),[])
        request.assert_not_called()

    def test_long_course_keeps_source_and_bounds_only_embedding_input(self):
        from src.database.vectors.resource_vectors import embedding_text
        row={'course_id':'real','title':'SQL 실습','syllabus_summary':'SQL 실습 내용 '*5000}
        original=row['syllabus_summary']
        value=embedding_text('courses',row)
        self.assertLessEqual(len(value.encode('utf-8')),8000)
        self.assertEqual(row['syllabus_summary'],original)

    def test_library_budget_counts_retries_and_prevents_extra_network_call(self):
        from unittest.mock import MagicMock
        obj=ing();obj.config['library']['request_budget']=2
        obj.client=MagicMock()
        failed=MagicMock(status_code=503,headers={})
        obj.client.get.return_value=failed
        with patch.object(obj,'_library_cache_read',return_value=None),patch('src.database.ingestion.real_data_ingestor.time.sleep'):
            with self.assertRaisesRegex(SourceError,'LIBRARY_REQUEST_BUDGET_REACHED'):
                obj._request('https://data4library.kr/api/srchBooks',{'keyword':'SQL'})
        self.assertEqual(obj.client.get.call_count,2)


    def test_configured_library_budget_keeps_existing_cap(self):
        from src.shared.config_loader import get_paths_config
        self.assertEqual(get_paths_config()['api']['library']['request_budget'],400)

    def test_kmooc_unix_seconds_are_valid_dates(self):
        from src.shared.catalog_eligibility import timestamp
        now=datetime.now(timezone.utc).replace(microsecond=0)
        self.assertEqual(timestamp(str(int(now.timestamp()))),now)
        self.assertEqual(timestamp(str(int(now.timestamp())*1000)),now)
        self.assertIsNone(timestamp('not-a-date'))

    def test_clothing_patterns_do_not_match_software_design(self):
        m=SkillMatcher([{'skill_id':26,'name':'객체지향 설계(OOP) & 디자인 패턴'}],
            rules={'객체지향 설계(OOP) & 디자인 패턴':['디자인.*패턴','오브젝트']})
        self.assertFalse(m.match('디자인 전문 인력을 양성합니다. 의복 생산의 기본이 되는 패턴 설계'))
        self.assertFalse(m.match('패션 디자인 패턴 실습'))
        self.assertIn(26,m.match('객체지향 프로그래밍과 디자인 패턴을 구현합니다.'))

    def test_latin_terms_adjacent_to_korean_are_recognized(self):
        self.assertIn(1,ing().matcher.match('SQL기초부터 PostgreSQL실습까지'))
        self.assertFalse(ing().matcher.match('nosqlstorage'))

    def test_sql_tuning_requires_specific_body_evidence(self):
        from src.shared.catalog_scope import scoped_matches
        matcher = SkillMatcher([{'skill_id':2, 'name':'SQL 쿼리 튜닝 & 인덱스 최적화'}])
        for description in ('오라클 SQL 튜닝을 실습합니다.', 'SQL 성능 최적화 기법을 다룹니다.',
                            'SQL 문을 분석하고 튜닝하는 과정을 설명합니다.', 'SQL튜닝을 연습합니다.'):
            with self.subTest(description=description):
                self.assertIn(2, scoped_matches(matcher, {'title':'데이터베이스 실습', 'description':description}))
        for description in ('NoSQL 튜닝과 클러스터 운영을 실습합니다.',
                            'PL/SQL 기초 문법과 저장 프로시저를 학습합니다.',
                            'PL/SQL 튜닝과 프로시저 관리를 학습합니다.',
                            'SELECT와 조인 기초를 연습합니다.', ''):
            with self.subTest(description=description):
                self.assertNotIn(2, scoped_matches(matcher, {'title':'SQL 튜닝', 'description':description}))

    def test_legacy_non_it_rows_are_excluded_without_deleting_them(self):
        from unittest.mock import MagicMock
        from src.shared.catalog_eligibility import eligible_keys
        now=datetime.now(timezone.utc).isoformat()
        rows=[{'job_id':1,'title':'SQL 데이터베이스 관리자','description':'SQL 조인과 데이터베이스 설계 및 운영 업무를 수행하며 데이터베이스 성능을 분석하고 최적화합니다.',
               'content_status':'ready','source_url':'https://www.career.go.kr','source_verified_at':now},
              {'job_id':2,'title':'경비원','description':'시설의 출입을 관리하고 순찰하여 안전을 확보하는 업무를 수행합니다.',
               'content_status':'ready','source_url':'https://www.career.go.kr','source_verified_at':now}]
        sources=[{'resource_type':'jobs','entity_key':str(r['job_id']),'source':'API_CAREERNET',
                  'payload':{'detail_record':{'baseInfo':{'job_cd':r['job_id']}}},'fetched_at':now} for r in rows]
        def query(sql):
            result=MagicMock()
            result.fetchall.return_value=SKILLS if 'SELECT skill_id' in sql else sources if 'catalog_api_sources' in sql else [{'record':r} for r in rows] if 'public.jobs ' in sql else []
            return result
        conn=MagicMock();conn.execute.side_effect=query
        usable,report=eligible_keys(conn)
        self.assertIn(('jobs','1'),usable)
        self.assertNotIn(('jobs','2'),usable)
        self.assertEqual(report['jobs']['excluded']['no_it_skill_evidence'],1)
        self.assertFalse(any('DELETE' in str(call) for call in conn.execute.call_args_list))

    def test_only_ready_internal_lesson_plans_are_eligible_for_indexing(self):
        from unittest.mock import MagicMock
        from src.shared.catalog_eligibility import eligible_keys
        valid = dict(course_id='INTERNAL_CRASH_2401', platform='사내교육', record_source='INTERNAL_TRAINING_PILOT',
                     content_status='ready', curriculum=dict(source='internal_training_pilot_v1',
                                                           outcome='요청 검증', items=[{'title':'DRF API 실습'}]))
        records = [valid, dict(valid,course_id='INTERNAL_CRASH_2402',curriculum={}),
                   dict(valid,course_id='external'),dict(valid,course_id='INTERNAL_CRASH_2403',content_status='inactive')]
        def query(sql):
            rows = SKILLS if 'SELECT skill_id' in sql else [{'record':r} for r in records] if 'public.courses ' in sql else []
            return MagicMock(fetchall=lambda:rows)
        conn=MagicMock();conn.execute.side_effect=query
        usable,report=eligible_keys(conn)
        self.assertEqual(usable,{('courses',valid['course_id'])})
        self.assertEqual(report['courses']['excluded']['incomplete_internal_curriculum'],3)


    def test_listed_kdc_outside_004_005_skips_only_doomed_detail_calls(self):
        obj=ing()
        docs=[{'doc':{'isbn13':'9788900000011','bookname':'SQL 소설','class_no':'813.7'}},
              {'doc':{'isbn13':'9788900000012','bookname':'SQL 실무','class_no':' 005.75 '}},
              {'doc':{'isbn13':'9788900000013','bookname':'SQL 입문'}}]
        with patch.object(obj,'_key',return_value='test'), patch.object(obj,'_request',return_value={
            'response':{'numFound':3,'docs':docs}}):
            with patch.object(catalog_details,'enrich_books',side_effect=lambda _,rows: rows) as detail:
                obj.fetch_books_from_api(0)
        # A missing list class_no still gets detail: the detail record may carry 004/005.
        self.assertEqual(sorted(r['external_key'] for r in detail.call_args.args[1]),['9788900000012','9788900000013'])
        self.assertEqual(obj.reports['library']['detail_skipped_outside_kdc'],1)

    def test_kdc_pre_filter_uses_the_catalog_scope_rule(self):
        from src.shared.catalog_scope import BOOK_KDC, scope_reason
        for code,allowed in (('004',True),('005.133',True),('004.73',True),('0045',False),('006.3',False),('813.6',False)):
            with self.subTest(code=code):
                self.assertEqual(bool(BOOK_KDC.fullmatch(code)),allowed)
                fields={'isbn':'9788900000021','title':'SQL 데이터베이스 실무','description':'SQL 조인과 데이터베이스 설계를 실습하며 쿼리를 작성하고 성능을 분석하는 방법을 학습합니다.'}
                reason=scope_reason('books',fields,'API_DATA4LIBRARY',{'list_record':{'class_no':code}})
                self.assertEqual(reason=='scope_book_not_kdc_004_005',not allowed)

    def test_short_skill_keywords_are_searched_before_broad_ones(self):
        from src.shared.config_loader import get_paths_config
        keywords=get_paths_config()['api']['ingestion']['book_keywords']
        self.assertEqual(len(keywords),len(set(keywords)))
        # The library list budget can run out on broad keywords, so #83 keywords go first.
        for short in ('SQL 튜닝','SQL 최적화','쿼리 튜닝','도커','Docker','시스템 프로그래밍','POSIX','시스템 보안','리눅스 보안',
                      'ETL','데이터 웨어하우스','운영체제','RESTful','레디스','멀티스레드','모의해킹','데이터 거버넌스'):
            with self.subTest(keyword=short):
                self.assertLess(keywords.index(short),keywords.index('컴퓨터 비전'))

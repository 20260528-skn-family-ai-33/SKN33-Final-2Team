import unittest
from src.shared.catalog_scope import scope_reason, scoped_matches
from src.shared.catalog_eligibility import exclusion_reason

class CatalogScopeTests(unittest.TestCase):
    def book(self):
        return dict(title="파이썬 프로그래밍 실습", isbn="9791191234567", description="파이썬 프로그래밍 실습으로 데이터베이스와 SQL 쿼리를 작성하고 소프트웨어를 개발하는 방법을 학습합니다.")
    def test_reported_childrens_literature_is_never_admitted(self):
        f=dict(title="할머니, 어디 가요? 밤 주우러 간다! :옥이네 가을 이야기", isbn="9788984286269",
               description="옥이네 이야기 시리즈. 컴퓨터에 갇힌 도시 아이들에게 자연과 건강한 먹을거리를 함께 보여준다.")
        self.assertEqual(scope_reason("books",f,"API_DATA4LIBRARY",{"class_no":"813.7"}),"scope_title_not_it_specialty")
    def test_technical_korean_book(self):
        self.assertIsNone(scope_reason("books",self.book(),"API_DATA4LIBRARY",{"class_no":"005.13"}))
    def test_literature_rejected_even_with_technical_description(self):
        f=self.book();f["title"]="문학 데이터 분석 파이썬"
        self.assertEqual(scope_reason("books",f,"API_DATA4LIBRARY",{"class_no":"005.13"}),"scope_outside_it_subject")
    def test_wrong_or_missing_kdc_rejected(self):
        for raw in ({"class_no":"813.7"},{}, {"detail_record":{"class_no":"813.7"},"list_record":{"class_no":"005"}}):
            self.assertEqual(scope_reason("books",self.book(),"API_DATA4LIBRARY",raw),"scope_book_not_kdc_004_005")
    def test_keyword_only_and_unknown_sources_rejected(self):
        f=self.book();f["description"]="IT AI Python"
        self.assertIsNotNone(scope_reason("books",f,"API_DATA4LIBRARY",{"class_no":"005"}))
        self.assertIsNotNone(scope_reason("books",self.book(),"UNTRUSTED",{"class_no":"005"}))
    def test_foreign_publication_rejected(self):
        f=self.book();f["isbn"]="9780131234567"
        self.assertEqual(scope_reason("books",f,"API_DATA4LIBRARY",{"class_no":"005"}),"scope_not_korean_publication")
    def test_kmooc_humanities_class_rejected(self):
        self.assertEqual(scope_reason("courses",self.book(),"API_KMOOC",{"classfy_name":"인문","middle_classfy_name":"문학"}),"scope_course_not_it_classification")
    def test_kmooc_engineering_accepted(self):
        self.assertIsNone(scope_reason("courses",self.book(),"API_KMOOC",{"classfy_name":"공학","middle_classfy_name":"컴퓨터"}))
    def test_automation_is_not_fairy_tale_subject(self):
        for title in ("DevOps & CI/CD 자동화 입문 기초 과정", "파이썬 업무 자동화", "시스템 자동화 프로그래밍"):
            with self.subTest(title=title):
                fields=self.book();fields['title']=title
                self.assertIsNone(scope_reason('courses',fields,'API_KMOOC',{'classfy_name':'공학','middle_classfy_name':'컴퓨터 자동화'}))
    def test_actual_fairy_tales_remain_excluded_with_automation(self):
        for title in ('파이썬으로 만드는 동화', '파이썬 전래동화', '파이썬 자동화와 동화 제작', '파이썬 어린이 학습 동화'):
            with self.subTest(title=title):
                fields=self.book();fields['title']=title
                self.assertEqual(scope_reason('books',fields,'API_DATA4LIBRARY',{'class_no':'005.13'}),'scope_outside_it_subject')
    def test_english_technical_terms_allow_korean_particles(self):
        for term in ('SQL로', 'Python으로', 'AWS에서', 'Azure를', 'NoSQL을', 'QGIS로'):
            with self.subTest(term=term):
                fields=self.book();fields['title']=term+' 배우는 실무 개발'
                self.assertIsNone(scope_reason('books',fields,'API_DATA4LIBRARY',{'class_no':'005.13'}))
    def test_english_substrings_are_not_technical_terms(self):
        for title in ('pythonic 생활 지침', 'sqlish 활용 안내', 'storage 활용 안내', 'qgisish 활용 안내'):
            with self.subTest(title=title):
                fields=self.book();fields['title']=title
                self.assertEqual(scope_reason('books',fields,'API_DATA4LIBRARY',{'class_no':'005.13'}),'scope_title_not_it_specialty')
    def test_existing_technical_skill_aliases_in_title_and_body(self):
        body='LLM을 구성하고 모델 미세 조정, 검색 증강 생성, 양자화와 배포를 실습하는 기술 학습 과정입니다.'
        for title in ('LLM 모델 구축', '생성형 AI API 활용', 'AI 보안 컨트롤', 'AI 엔지니어 자격 과정', '생성형 AI 서비스 설계', '개발자를 위한 생성형 AI 활용 가이드'):
            with self.subTest(title=title):
                fields=self.book();fields.update(title=title,description=body)
                self.assertIsNone(scope_reason('books',fields,'API_DATA4LIBRARY',{'class_no':'005.13'}))
    def test_ai_mentions_and_nontechnical_productivity_stay_excluded(self):
        for title in ('생성형 AI 사진 만들기', '일상적인 작업에 AI 사용', '인사 전문가를 위한 프롬프트 활용', 'AI 마케팅 자동화', 'AI로 사업계획서 작성하기', 'GitHub 인증: 에이전틱 AI 비즈니스 전문가 (베타)'):
            with self.subTest(title=title):
                fields=self.book();fields['title']=title
                self.assertIsNotNone(scope_reason('books',fields,'API_DATA4LIBRARY',{'class_no':'005.13'}))
    def test_agent_skill_requires_explicit_body_evidence(self):
        from src.shared.skill_matching import SkillMatcher
        matcher=SkillMatcher([{'skill_id':13,'name':'RAG & 생성형 AI 에이전트','category':'인공지능'}],rules={'RAG & 생성형 AI 에이전트':[]})
        for body in ('AI 에이전트를 빌드하고 배포합니다.', 'AI agents 개발을 실습합니다.', '에이전틱 AI 솔루션을 구축합니다.'):
            with self.subTest(body=body):
                self.assertIn(13,scoped_matches(matcher,{'description':body}))
        self.assertEqual(scoped_matches(matcher,{'title':'AI 에이전트 개발','description':'일반적인 일정 관리 안내입니다.'}),{})
        self.assertEqual(scoped_matches(matcher,{'description':'보험 에이전트가 고객 상담을 진행합니다.'}),{})
    def test_agent_platform_requires_agent_in_same_body_sentence(self):
        from src.shared.skill_matching import SkillMatcher
        matcher=SkillMatcher([{'skill_id':13,'name':'RAG & 생성형 AI 에이전트','category':'인공지능'}],rules={'RAG & 생성형 AI 에이전트':[]})
        self.assertIn(13,scoped_matches(matcher,{'description':'Copilot Studio에서 에이전트를 만들고 구성합니다.'}))
        self.assertEqual(scoped_matches(matcher,{'description':'Copilot Studio를 소개합니다. 보험 에이전트의 일정을 정리합니다.'}),{})
        self.assertEqual(scoped_matches(matcher,{'description':'Copilot Studio에서 일정을 정리합니다.'}),{})
    def test_applied_ai_fusion_course_requires_model_building_curriculum(self):
        fields=dict(title='AI 기반 헬스케어 데이터 가치 발굴 실무',
                    syllabus_summary='Python 기반 데이터 처리 및 시각화 기초를 익히고 머신러닝과 딥러닝을 활용하여 시계열 예측 모델을 구현하는 프로젝트 실습입니다.')
        raw={'classfy_name':'융 · 복합','middle_classfy_name':'융 · 복합'}
        self.assertIsNone(scope_reason('courses',fields,'API_KMOOC',raw))
        for body in ('의료 데이터와 AI 서비스의 활용 사례를 살펴보고 조직의 업무를 관리하는 일반적인 안내 과정입니다.',
                     '머신러닝과 딥러닝으로 예측 모델을 구현하는 실습을 통해 의료 데이터 분석 기술을 학습하는 과정입니다.',
                     'Python 기반 데이터 처리를 배우고 의료 데이터 활용 사례를 분석하는 일반 실무 과정입니다.',
                     'Python 및 머신러닝 기초 개념을 소개하고 데이터와 AI 기술의 활용 사례를 검토합니다.'):
            with self.subTest(body=body):
                self.assertEqual(scope_reason('courses',{**fields,'syllabus_summary':body},'API_KMOOC',raw),'scope_title_not_it_specialty')
        for classification in ('인문 문학','의약 간호','기타',''):
            with self.subTest(classification=classification):
                self.assertEqual(scope_reason('courses',fields,'API_KMOOC',{'classfy_name':classification}),'scope_course_not_it_classification')
        self.assertEqual(scope_reason('courses',{**fields,'title':'어린이 AI 데이터 실무'},'API_KMOOC',raw),'scope_outside_it_subject')
    def test_applied_ai_exception_does_not_bypass_open_enrollment(self):
        from datetime import datetime, timezone
        fields=dict(title='AI 기반 헬스케어 데이터 가치 발굴 실무',org_name='교육기관',
                    url='https://www.kmooc.kr/view/course/detail/1',
                    source_url='https://www.kmooc.kr/view/course/detail/1',source_verified_at='2026-10-26T00:00:00+00:00',
                    syllabus_summary='Python 기반 데이터 처리와 머신러닝 및 딥러닝을 활용하여 시계열 예측 모델을 구현하고 학습하는 프로젝트 실습 과정입니다.')
        now=datetime(2026,10,26,tzinfo=timezone.utc)
        raw=dict(classfy_name='융 · 복합',public_yn='Y',enrollment_start='2026-09-28T00:00:00+09:00',
                 enrollment_end='2026-10-25T23:59:00+09:00',study_end='2026-11-15T23:59:00+09:00')
        self.assertEqual(exclusion_reason('courses',fields,'API_KMOOC',raw,now,now=now),'course_not_confirmed_open')
    def test_security_copilot_agent_management_is_technical_training(self):
        from src.shared.skill_matching import SkillMatcher
        matcher=SkillMatcher([{'skill_id':13,'name':'RAG & 생성형 AI 에이전트','category':'인공지능'}],rules={'RAG & 생성형 AI 에이전트':[]})
        fields=dict(title='Microsoft Security Copilot 플러그 인 및 에이전트 관리',
                    url='https://learn.microsoft.com/ko-kr/training/modules/manage-plugins-agents-security-copilot/',
                    syllabus_summary='플러그 인 거버넌스 설정을 구성하고 보안 Copilot 에이전트 수명 주기를 관리하며 에이전트 구성과 실행 상태를 관리하는 방법을 알아봅니다.')
        self.assertIsNone(scope_reason('courses',fields,'API_MS_LEARN',{}))
        self.assertIn(13,scoped_matches(matcher,fields))
        for body in ('Security Copilot을 소개합니다. 보험 에이전트의 일정을 관리합니다.',
                     '보안 Copilot을 소개합니다. 보험 에이전트와 상담합니다.',
                     'Copilot으로 보험 에이전트의 회의 일정을 정리합니다.'):
            with self.subTest(body=body):
                self.assertEqual(scoped_matches(matcher,{'description':body}),{})
    def test_ai_service_administrator_has_existing_iam_skill_evidence(self):
        from src.shared.skill_matching import SkillMatcher
        matcher=SkillMatcher([{'skill_id':18,'name':'클라우드 IAM & 네트워크 보안','category':'클라우드'},
                              {'skill_id':13,'name':'RAG & 생성형 AI 에이전트','category':'인공지능'}],
                             rules={'클라우드 인프라 보안 & IAM':[],'RAG & 생성형 AI 에이전트':[]})
        fields=dict(title='Microsoft 365 인증: Microsoft 365 및 AI 서비스 관리자 어소시에이트(베타)',
                    source_url='https://learn.microsoft.com/ko-kr/credentials/certifications/ai-services-administrator-associate/',
                    description='Microsoft 365 Copilot, 에이전트 및 연결된 AI 기능을 포함하여 테넌트와 AI 서비스를 구성, 관리, 보안 및 관리합니다. Microsoft Entra ID 및 Defender XDR 기능을 이해하고 Microsoft Graph PowerShell로 관리합니다.')
        self.assertIsNone(scope_reason('certifications',fields,'API_MS_CERT',{}))
        self.assertIn(18,scoped_matches(matcher,fields))
        self.assertIn(13,scoped_matches(matcher,fields))
        self.assertEqual(scoped_matches(matcher,{'title':'Microsoft Entra ID 관리','description':'Microsoft 365로 회의 자료를 정리합니다.'}),{})
        self.assertEqual(scoped_matches(matcher,{'description':'Microsoft Entra identity와 상담 고객 ID를 소개합니다.'}),{})
        for body in ('Microsoft 365 Copilot을 소개합니다. 보험 에이전트의 일정을 관리합니다.',
                     'Microsoft 365 Copilot에서 에이전트와 회의합니다.',
                     'Microsoft 365 Copilot 및 에이전트를 소개합니다. 다음 문장에서 일반 일정을 관리합니다.'):
            with self.subTest(body=body):
                self.assertEqual(scoped_matches(matcher,{'description':body}),{})
    def test_sales_ai_functional_configuration_is_outside_current_technical_skills(self):
        from src.shared.skill_matching import SkillMatcher
        matcher=SkillMatcher([{'skill_id':13,'name':'RAG & 생성형 AI 에이전트','category':'인공지능'},
                              {'skill_id':18,'name':'클라우드 IAM & 네트워크 보안','category':'클라우드'}],
                             rules={'RAG & 생성형 AI 에이전트':[],'클라우드 인프라 보안 & IAM':[]})
        fields=dict(title='Microsoft Certified: Dynamics 365 Sales AI 컨설턴트 어소시에이트',
                    description='Dynamics 365 Sales Copilot 및 에이전트 기능을 사용하여 판매 솔루션을 설계하고 구성합니다. 잠재 고객 한정과 판매 기회 관리 및 가격표를 구성하고 Power Automate 흐름을 만듭니다.')
        self.assertEqual(scoped_matches(matcher,fields),{})
        self.assertEqual(scope_reason('certifications',fields,'API_MS_CERT',{}),'scope_title_not_it_specialty')
    def test_technical_title_still_requires_substantive_technical_body(self):
        fields=self.book();fields.update(title='AI 보안 컨트롤',description='일상 업무의 시간을 계획하고 회의 일정을 정리하는 일반적인 활용 사례를 소개하는 안내 과정입니다.')
        self.assertEqual(scope_reason('courses',fields,'API_MS_LEARN',{}),'scope_no_substantive_it_training_or_work')
    def test_microsoft_korean_locale_and_actual_language_required(self):
        f=self.book();f["url"]="https://learn.microsoft.com/en-us/training/"
        self.assertEqual(scope_reason("courses",f,"API_MS_LEARN",{}),"scope_no_korean_localization")
        f["url"]="https://learn.microsoft.com/ko-kr/training/"
        self.assertIsNone(scope_reason("courses",f,"API_MS_LEARN",{}))
        f["description"]="Develop Python software and implement database queries in a training project."
        self.assertEqual(scope_reason("courses",f,"API_MS_LEARN",{}),"scope_no_korean_content")
    def test_title_only_skill_is_not_linked(self):
        class Matcher:
            def match(self,text):return {1:["SQL"]} if "SQL" in text else {}
        self.assertEqual(scoped_matches(Matcher(),{"title":"SQL","description":"일반 교양"}),{})
    def test_book_cannot_bypass_retrieval_guard(self):
        f=self.book();f["title"]="문학 데이터 분석"
        self.assertEqual(exclusion_reason("books",f,"API_DATA4LIBRARY",{"class_no":"005"},None),"scope_outside_it_subject")
    def test_non_it_job_and_major_rejected(self):
        for kind,source,title in [("jobs","API_CAREERNET","경비원"),("majors","API_CAREERNET_MAJOR","방사선학과")]:
            f=self.book();f["title"]=title
            self.assertIsNotNone(scope_reason(kind,f,source,{"detail_record":{}}))

if __name__ == "__main__":unittest.main()

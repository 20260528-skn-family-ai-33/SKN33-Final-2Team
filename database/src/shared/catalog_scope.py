"""Korean IT catalog boundary. Classification, title, substantive content all required."""
import re
from urllib.parse import urlsplit
from src.shared.instructional_content import teaching_text

POLICY_VERSION = "kr-it-2026-10-27-v7"
SOURCES = {"books": {"API_DATA4LIBRARY"}, "courses": {"API_KMOOC", "API_MS_LEARN", "WEB_KOCW", "WEB_INFLEARN", "WEB_OPENTUTORIALS", "WEB_STEP"},
           "certifications": {"API_ODCLOUD_KDATA", "API_MS_CERT"},
           "jobs": {"API_CAREERNET"}, "majors": {"API_CAREERNET_MAJOR"}}
# ASCII boundaries accept SQL로/AWS에서 while rejecting sqlish and rag in storage.
# These are aliases for existing DB skills, not permission to admit AI mentions alone.
TECH_WORD = (
    r"(?<![A-Za-z0-9_])(?:python|sql|rdbms|dbms|nosql|etl|olap|llm|nlp|posix|"
    r"restful|api|sdk|java|c\+\+|c\#|linux|docker|kubernetes|pytorch|tensorflow|azure|aws|devops|"
    r"mlops|rag|fastapi|django|qgis|pyqgis|geoai|github\s+copilot|microsoft\s+foundry|"
    r"copilot\s+studio|security\s+copilot|보안\s+copilot|entra\s+id)(?![A-Za-z0-9_])"
)
IT = re.compile(
    r"파이썬|데이터베이스|자료구조|알고리즘|프로그래밍|프로그래머|소프트웨어|"
    r"컴퓨터\s*(공학|과학|구조|비전|네트워크)|전산|정보\s*(보안|보호|통신|시스템)|"
    r"머신\s*러닝|딥\s*러닝|기계\s*학습|자연어\s*처리|인공지능|"
    r"데이터\s*(분석|과학|공학|엔지니어|보안|웨어하우스)|클라우드|리눅스|도커|쿠버네티스|"
    r"네트워크\s*(보안|설계|운영)|운영체제|객체지향|웹\s*(개발|프레임워크|서버)|"
    r"마이크로\s*서비스|데이터\s*거버넌스|Windows\s*보안|인터넷\s*정보\s*서비스|"
    r"웹\s*(?:해킹|취약점)|멀티\s*(?:스레드|쓰레드)|"
    r"웹\s*애플리케이션[^\n.!?。]{0,30}(?:취약점|보안|개발)|"
    r"(?<![A-Za-z0-9_])(?:OWASP|ASP\.NET)(?![A-Za-z0-9_])|"
    r"네트워크\s*(?:구성|모니터링|트래픽)|쿼리\s*(?:성능\s*)?(?:최적화|튜닝)|IP\s*주소|"
    r"시스템\s*(개발|프로그래밍)|정보처리|빅데이터|리팩터링|검색\s*증강|"
    r"(?:대규모|거대)\s*언어\s*모델|프롬프트\s*엔지니어링|"
    r"(?<![A-Za-z0-9_])AI\s*(?:에이전트|보안|엔지니어)|"
    r"(?:생성형\s*AI|AI)\s*(?:서비스|시스템|앱|애플리케이션)\s*(?:개발|설계|구축)|"
    r"(?<![A-Za-z0-9_])AI\s*서비스\s*(?:관리|운영|보안)|"
    r"개발자(?:를\s*위한|용)\s*생성형\s*AI|"
    r"에이전틱\s*AI[^.!?。\n]{0,16}(?:솔루션|아키텍트|개발|설계)|"
    r"에이전트\s*AI[^.!?。\n]{0,16}(?:개발|설계|구축)|"
    r"(?:다중|멀티)\s*에이전트\s*(?:AI|시스템|솔루션)|" + TECH_WORD,
    re.I,
)
# Keep actual fairy-tale subjects excluded without matching the suffix of 자동화.
OUTSIDE = re.compile(r"문학|소설|사유|시집|(?<!자)동화|수필|에세이|인문|철학|종교|역사|예술|미술|음악|요리|여행|육아|어린이|유아|초등|중학생|고등학생|교양|리터러시|마케팅|재테크|주식|방사선|간호|경비원|청렴")
PRACTICE = re.compile(r"구현|개발|설계|실습|프로그래밍|코딩|학습|훈련|쿼리|분석|알고리즘|모델링|구축|배포|운영|디버깅|최적화|처리|보안|작성|관리|컴파일|테스트|프로토콜[^\n.!?。]{0,30}이해|\b(?:implement|develop|design|build|deploy|configure|train|query|code|programming|manage|analy[sz]|secure|test)\w*", re.I)

def body_text(fields):
    # The normalized course JSON is UI/model evidence, not a change to the
    # original text used by reviewed skill links and vector eligibility.
    # Legacy text curricula (for example majors) retain their existing meaning.
    body = "\n".join(dict.fromkeys(str(fields.get(k) or "") for k in
                       ("syllabus_summary", "description", "test_subjects", "curriculum", "ncs_units")
                       if not (k == "curriculum" and isinstance(fields.get(k), dict))))
    return teaching_text(body) if fields.get('syllabus_summary') else body

def applied_ai_course(title, body):
    # Cross-disciplinary classification can contain real model-building training.
    # Require code, ML/DL and model implementation together, beyond an AI title.
    return (bool(re.search(r"\bAI\b", title, re.I | re.ASCII))
            and "데이터" in title and "실무" in title
            and bool(re.search(r"\bpython\b|파이썬", body, re.I | re.ASCII))
            and bool(re.search(r"머신\s*러닝|기계\s*학습|딥\s*러닝", body))
            and bool(re.search(r"모델[^\n.!?。]{0,40}(?:구현|훈련|학습|개발)", body)))

def scope_reason(kind, fields, source, raw):
    if source not in SOURCES.get(kind, set()):
        return "scope_unsupported_source"
    if not isinstance(raw, dict):
        return "scope_missing_official_evidence"
    title = str(fields.get("title") or "")
    body = body_text(fields)
    if not re.search(r"[가-힣]", title) or not re.search(r"[가-힣]", body):
        return "scope_no_korean_content"
    if OUTSIDE.search(title):
        return "scope_outside_it_subject"
    applied_ai = kind == "courses" and source == "API_KMOOC" and applied_ai_course(title, body)
    # Some official SQL modules use a generic title such as 성능 향상 평가.
    # Product classification plus actual query/index training supplies the context.
    sql_module = (kind == "courses" and source == "API_MS_LEARN" and raw.get("type") == "module"
                  and bool(set(raw.get("products") or []) & {"sql-server", "azure-sql-database", "azure-sql-managed-instance"})
                  and bool(re.search(r"쿼리|인덱스|실행\s*계획", body)))
    if not IT.search(title) and not applied_ai and not sql_module:
        return "scope_title_not_it_specialty"
    if len(body.strip()) < 40 or not IT.search(body) or not PRACTICE.search(body):
        return "scope_no_substantive_it_training_or_work"
    if source in ("API_MS_LEARN", "API_MS_CERT"):
        try:
            url = urlsplit(str(fields.get("url") or fields.get("source_url") or ""))
            if url.hostname != "learn.microsoft.com" or not url.path.lower().startswith("/ko-kr/"):
                return "scope_no_korean_localization"
        except ValueError:
            return "scope_no_korean_localization"
    elif not re.search(r"[가-힣]", body):
        return "scope_no_korean_content"
    if kind == "books":
        isbn = str(fields.get("isbn") or "").replace("-", "")
        if not re.fullmatch(r"(?:97889|97911)\d{8}", isbn):
            return "scope_not_korean_publication"
        records = [raw.get("detail_record"), raw.get("list_record"), raw]
        codes = [str(r.get("class_no") or "").strip() for r in records if isinstance(r, dict) and r.get("class_no")]
        if not codes or any(not re.fullmatch(r"00[45](?:\.\d+)?", code) for code in codes):
            return "scope_book_not_kdc_004_005"
    if source == "API_KMOOC":
        classification = " ".join(str(raw.get(k) or "") for k in ("classfy_name", "middle_classfy_name"))
        technical_class = re.search(r"공학|컴퓨터|정보|소프트웨어|전산|데이터|인공지능", classification)
        applied_class = applied_ai and re.search(r"융\s*[·ㆍ]?\s*복합", classification)
        if OUTSIDE.search(classification) or not (technical_class or applied_class):
            return "scope_course_not_it_classification"
    if kind in ("jobs", "majors") and not isinstance(raw.get("detail_record"), dict):
        return "scope_missing_official_detail"
    return None

def scoped_matches(matcher, fields):
    # A skill mentioned only in the title is insufficient to attach a learning link.
    return matcher.match(body_text(fields))

"""세 코스의 실제 학습 근거·관련 단원. 태그와 선수지식만으로 학습 내용을 단정하지 않는다."""
from __future__ import annotations

from functools import lru_cache
import math
import re
import unicodedata
from app import catalog_candidates as evidence
from app import course_levels
from app.english_patterns import english_token as _en
from app.services.course_skills import crash_core_fields
from app.services.technology_mentions import applied_technologies, canonical_versions, technology_pattern


_generic = {'기초', '실무', '활용', '학습', '이해', '환경', '프로그래밍', '아키텍처', '컴퓨팅',
            '프로젝트', '역량', '적용', '구현', '개발', '기술', '지식', '및', '기반',
            '사내', '업무', '만들기', '만들', '하기', '개선', '단계별', '정리', '정리하기',
            '단계', '정리한', '정리한다', '정리해', '따라하기', '쉽게', '한번', '한눈', '완성', '완성하기', '마스터', '핵심', '요약', '가이드',
            '입문', '초급', '고급', '심화', '종합', '전체', '빠르게', '간단히', '실전', '과정', '강의',
            'course', 'guide', 'step', 'summary', 'advanced', 'beginner', 'masterclass'}

_aliases = {
    'Python': ('python', '파이썬', 'asyncio'),
    'RAG': ('rag', '검색 증강', '검색증강', 'retrieval', 'langchain', '랭체인'),
    '자연어': ('nlp', '자연어', 'llm', '언어 모델', '언어모델', '토큰화', '임베딩', 'chatbot', '챗봇'),
    'RESTful': ('rest', 'restful', 'api', 'fastapi'),
    '웹 프레임워크': ('fastapi', 'django', '장고', 'flask', '플라스크', 'spring', '스프링',
                    'express.js', 'nestjs', '프레임워크', 'framework'),
    'Docker': ('docker', '도커', '컨테이너', 'container'),
    '클라우드': ('aws', 'azure', '클라우드', 'cloud', 'gcp'),
    'CI/CD': ('ci', 'cd', 'gitlab', 'github actions', '젠킨스', 'jenkins', '지속적 통합', '지속적 배포'),
    'MLOps': ('mlops', '모델 서빙', '모델서빙', '모델 배포', '모델배포', 'model serving', 'model deployment',
              '머신러닝 파이프라인', '기계학습 파이프라인'),
    'RDBMS': ('rdbms', '모델링', '정규화', '관계형', '데이터베이스 설계'),
    'NoSQL': ('nosql', 'mongodb', '몽고db', '몽고디비', 'dynamodb', 'cassandra', '분산 db', '분산 데이터베이스'),
    'SQL': ('sql', '조인', '쿼리'),
    'EDA': ('eda', '탐색적', '전처리', 'pandas', '판다스', '데이터 분석'),
    'ETL': ('etl', 'elt', 'dbt', 'airflow', '에어플로우', '데이터 파이프라인', 'data pipeline', '데이터 적재', '데이터 수집', '데이터 변환'),
    '대용량 트래픽': ('캐시', '캐싱', 'cache', 'caching', '트래픽', '부하 테스트', 'load balancing'),
    '웨어하우스': ('olap', '웨어하우스', 'warehouse', '차원 모델', '차원 키', '분석 마트', 'scd', '데이터 계보'),
    'POSIX': ('posix', '시스템 호출', '시스템 콜', 'ipc', 'fork', 'waitpid', 'mmap', 'sem_wait', 'sem_post', '세마포어', '공유 메모리'),
    '시스템 & OS 보안': ('os 보안', '시스템 보안', '하드닝', '보안 강화', '권한 변경', '파일 권한', '감사 로그', 'linux audit', 'auditd', '접근 제어'),
    '리눅스': ('linux', '리눅스', 'bash', 'shell', '쉘'),
    '멀티스레딩': ('멀티스레딩', '스레드', '동시성', 'threading', 'multithreading', 'concurrency', 'asyncio',
                'race condition', '경쟁 상태', '경쟁 조건', '동기화', 'synchronization'),
    '머신러닝': ('머신러닝', '기계학습', 'machine learning', '분류', '회귀', '지도 학습', '비지도 학습'),
}

# 특정 학습 주제가 명시됐을 때만 구분한다. 긴 본문의 일반 단어 일치율을 문턱으로 삼지 않는다.
_analysis_scope = re.compile(r'데이터\s*분석|전처리|탐색적|' + _en(r'(?:data\s+analysis|pandas|eda)'), re.I)
_analysis_evidence = re.compile(r'데이터\s*분석|전처리|탐색적|시각화|' + _en(r'(?:data\s+analysis|pandas|eda|dataframe)'), re.I)
_depth = re.compile(r'설계|비교|검증|측정|평가|최적화|문제\s*해결|트러블슈팅|' + _en(r'(?:design|compar\w*|validat\w*|measur\w*|evaluat\w*|optimi\w*|benchmark|troubleshoot\w*)'), re.I)
_admin = re.compile(r'만족도|수강\s*후기|강의\s*평가|과정\s*평가|설문\s*조사|' + _en(r'(?:course evaluation|feedback survey)'), re.I)
_log_word = r'(?:(?<![가-힣])|(?:운영|서버|배치|시스템|보안|이벤트|웹)\s*)로그(?!인|아웃|손실|우도|함수|리즘)'
_log_topic = re.compile(_log_word + r'|' + _en(r'(?:logs?|logging)'), re.I)
_log_learning = re.compile(_log_word + r'|파싱|정규\s*표현|파일.{0,15}(?:읽|처리)|예외.{0,15}테스트|' + _en(r'(?:logging|parsing|pytest|fixture|stderr|batch)'), re.I)
_log_operation = re.compile(r'집계|읽기|파싱|aggregate|parse', re.I)
_audit_records = re.compile(r'(?:접근|접속|인증|인가|권한|보안|감사)\s*(?:로그|기록|이벤트)|'
                           + _en(r'(?:access|auth(?:entication|orization)?|security|audit)\s+(?:logs?|events?|records?)'), re.I)
_audit_analysis = re.compile(r'분류|분석|집계|조인|전처리|조회|해석|수집|라벨|탐지|거절|거부|허용|'
                            + _en(r'classif\w*|analy\w*|aggregat\w*|query|join|filter\w*|detect\w*|denied'), re.I)
_access_denial = re.compile(r'거절|거부|차단|' + _en(r'denied|denials?|forbidden|403'), re.I)

_build = re.compile(r'만들|구현|구축|개발|실습|연동|실행|구성|빌드|코드\s*작성|파싱|조회|데이터\s*(?:변환|적재)|(?:예외|오류)\s*처리|작업\s*취소|' + _en(r'(?:build\w*|implement\w*|develop\w*|integrat\w*|hands[- ]on|labs?|execut\w*)'), re.I)
_operate = re.compile(r'배포|서빙|모니터링|롤백|복구|' + _en(r'(?:deploy\w*|serving|monitor\w*|rollback|recover\w*)'), re.I)
_concept = re.compile(r'개념|원리|이론|구조|이해|설명|무엇|개요|소개|' + _en(r'(?:concept\w*|theory|principle\w*|understand\w*|overview|introduct\w*)'), re.I)
_intro_only = re.compile(r'소개|개요|이론|무엇|' + _en(r'(?:overview|introduct\w*|theory)'), re.I)
_practice = re.compile(r'실습|직접|코드.{0,12}(?:작성|구현|실행)|' + _en(r'(?:hands[- ]on|labs?)'), re.I)
_discussion = re.compile(r'경험\s*공유|경험담|(?:개발|활용)\s*팁|발표\s*세션|질의\s*응답\s*세션|Q\s*&\s*A|' + _en(r'(?:experience sharing|panel discussion|development tips)'), re.I)
_question = re.compile(r'^\s*(?:Q\s*[.:]|질문\s*[:.])|궁금(?:해|하|한)', re.I)
_foundations = re.compile(r'문법|자료형|함수|조인|정규화|쿼리|토큰|컨텍스트|임베딩|벡터|자료\s*구조|' + _en(r'(?:syntax|types?|joins?|queries|tokens?|context|embeddings?|vectors?)'), re.I)
_security = re.compile(r'보안|공격|권한|가드레일|신뢰\s*경계|레드\s*티밍|' + _en(r'(?:security|attack\w*|guardrails?|red\s*team\w*|permission\w*)'), re.I)
_security_action = re.compile(r'검증|시험|진단|관찰|점검|지도|분석|실습|테스트|' + _en(r'(?:test\w*|audit\w*|inspect\w*|map\w*)'), re.I)
_design = re.compile(r'설계|아키텍처|전략|' + _en(r'(?:design(?:s|ed|ing|\d+)?|architect\w*|strateg\w*)'), re.I)
_business = re.compile(r'서비스\s*디자인|비즈니스|고객\s*여정|(?<![a-z0-9])(?:UX|UI)(?![a-z0-9])|페르소나|아이데이션|시장|수익|' + _en(r'(?:business|customer journey|ideation)'), re.I)
_rag_objects = re.compile(_en(r'rag') + r'|검색\s*증강|챗봇|벡터|임베딩|색인|검색|재순위화|청크|지식\s*원본|' + _en(r'(?:retriev\w*|embeddings?|vector\w*|chatbot\w*|indexing|rerank\w*|chunk\w*)'), re.I)
_document_target = re.compile(r'문서|' + _en(r'(?:pdf|documents?)'), re.I)
_document_evidence = re.compile(r'문서|텍스트|지식\s*베이스|' + _en(r'(?:pdf|documents?|text|textual|knowledge base)'), re.I)
_media_search = re.compile(r'(?:이미지|영상|비디오|음성|' + _en(r'(?:images?|videos?|audio)') + r').{0,14}(?:검색|검색기|' + _en(r'(?:search|retrieval)') + r')', re.I)
_rag_retrieval_practice = re.compile(_en(r'rag', right=False) + r'\s*(?:실습|구성|구축|조회|검색)|벡터\s*(?:db|데이터베이스).{0,14}(?:구성|구축|적재|저장)|'
                                    r'(?:검색|' + _en(r'retrieval') + r').{0,14}(?:효율|전처리|키워드)|' + _en(r'(?:build|configure|query)\s+(?:a\s+)?(?:rag|vector (?:db|database))'), re.I)
_nlp_objects = re.compile(r'토큰|컨텍스트|언어\s*모델|임베딩|자연어|프롬프트|' + _en(r'(?:tokens?|context|embeddings?|nlp|prompts?|language models?)'), re.I)
_nlp_topics = re.compile(r'챗봇|' + _en(r'(?:llms?|chatbots?)'), re.I)
_async_io = r'비동기|코루틴|이벤트\s*루프|' + _en(r'async(?:io)?|await|coroutines?|event loop')
_async_context = re.compile(_async_io + r'|동시성|병행성|병렬성|멀티\s*(?:스레딩|프로세싱)|' + _en(r'(?:concurrency|parallelism|multithreading|multiprocessing)'), re.I)
_io_workload = re.compile(_en(r'(?:i/o|io)[ -]+bound') + r'|입출력\s*병목', re.I)
_async_comparison = re.compile(r'(?=.*(?:비교|' + _en(r'(?:vs\.?|versus|compar\w*)') + r'))(?=.*(?:스레드|프로세스|' + _en(r'(?:threading|multiprocessing|synchronous)') + r'))', re.I)
_linux = re.compile(r'리눅스|유닉스|' + _en(r'(?:linux|unix|posix)'), re.I)
_linux_controls = re.compile(_en(r'(?:setuid|setgid|chmod|chown|selinux|apparmor|systemd)'), re.I)
_os_controls = re.compile(r'권한|접근\s*제어|격리|보안|방화벽|' + _en(r'(?:permissions?|access control|isolation|sandbox\w*|hardening|firewall|iptables)'), re.I)
_windows = re.compile(r'윈도우|' + _en(r'(?:windows|win32|ntfs|powershell|iis)'), re.I)
_linux_security_topics = (
    ('Linux 권한 설정', re.compile(r'권한|' + _en(r'permissions?'), re.I),
     re.compile(r'권한|접근\s*제어|' + _en(r'(?:permissions?|access control|chmod|chown|setuid|setgid|sudo)'), re.I)),
    ('Linux 서비스 격리', re.compile(r'격리|' + _en(r'isolation'), re.I),
     re.compile(r'격리|' + _en(r'(?:isolation|sandbox\w*|namespaces?|seccomp|apparmor)'), re.I)),
)
_dbt = re.compile(_en('dbt'), re.I)
_etl_targets = tuple((re.compile(request, re.I), re.compile(unit, re.I)) for request, unit in (
    (r'모델|' + _en(r'models?'), r'모델|' + _en(r'models?')),
    (r'품질|테스트|검증|' + _en(r'quality|tests?|freshness'), r'품질|테스트|검증|' + _en(r'quality|tests?|freshness')),
    (r'증분|' + _en(r'incremental'), r'증분|' + _en(r'incremental')),
    (r'재처리|백필|' + _en(r'backfill|reprocess\w*'), r'재처리|백필|' + _en(r'back[ -]?fill|reprocess\w*')),
))

# 스킬 태그가 넓어도 명시된 기술/학습 대상은 실제 학습 근거에서 찾는다.
# label이 있는 대상은 요구 단계의 학습 근거에서 다시 확인한다. dbt는 아래 세부 대상으로 확인한다.
_scope_topics = (
    ('데이터 계보', r'웨어하우스|거버넌스', r'계보|' + _en('lineage'), r'계보|변환 경로|' + _en('lineage')),
    (None, r'POSIX|동시성', r'세마포어|' + _en('semaphores?'), r'세마포어|' + _en('semaphores?|sem_wait|sem_post')),
    (None, r'ETL|파이프라인', _dbt.pattern, _dbt.pattern),
    ('SQL 조인', _en('sql|rdbms'), r'조인|' + _en(r'joins?'), r'조인|' + _en(r'joins?')),
    ('토큰화', r'RAG|NLP|자연어', r'토큰화|' + _en(r'tokeniz\w*'), r'토큰|' + _en(r'tokens?|tokeniz\w*')),
    ('Kubernetes', r'클라우드|cloud|Docker', r'쿠버네티스|' + _en(r'kubernetes|k8s'), r'쿠버네티스|' + _en(r'kubernetes|k8s')),
    ('비동기 I/O', r'Python|파이썬', _async_io, _async_io),
)
_ETL_TARGET_LABELS = ('dbt 모델', 'dbt 품질 테스트', 'dbt 증분 처리', 'dbt 재처리·백필')

# 명시한 구현 도구만 해당 스킬에 적용한다. SQL 이론 등에 목표의 모든 영문 단어를 요구하지 않는다.
_stacks = {
    'fastapi': r'fastapi|패스트\s*API', 'django': r'django|장고', 'flask': r'flask|플라스크',
    'spring': r'spring(?:[ .-]*(?:boot|framework|ai|mvc|webflux|security|data|batch|cloud))?|스프링(?:\s*(?:부트|프레임워크|시큐리티|클라우드|배치))?',
    'express': r'express(?:\.js)?|익스프레스', 'nestjs': r'nest\.?js',
    'python': r'python|파이썬|asyncio', 'java': r'java|자바(?!스크립트)',
    'javascript': r'javascript|typescript|node\.?js|자바스크립트|타입스크립트',
    'aws': r'aws|아마존\s*웹', 'azure': r'azure|애저', 'gcp': r'gcp|google\s*cloud',
    'pytorch': r'pytorch|파이토치|torchvision|torch\.(?:nn|optim|utils\.data)',
    'tensorflow': r'tensorflow|텐서플로(?:우)?',
}
_stack_patterns = {name: re.compile(r'(?<![a-z0-9])(?:' + pattern + r')(?![a-z0-9])', re.I)
                   for name, pattern in _stacks.items()}
_web_stacks = {'fastapi', 'django', 'flask', 'spring', 'express', 'nestjs'}
_runtime = {'fastapi': 'python', 'django': 'python', 'flask': 'python', 'spring': 'java',
            'express': 'javascript', 'nestjs': 'javascript'}
_framework_after = re.compile(r'^[ \t]*(?:[/:-][ \t]*)?(?:' + _en(r'(?:rest(?:ful)?|api|framework|server|middleware|router|routing|backend|web|rag)', left=False) + r'|으로|로|을|를|과|와|기반|기초|입문|설치|설정|활용|실습|구현|개발|서버|프레임워크)', re.I)
_framework_before = re.compile(r'(?:' + _en(r'(?:java|javascript|typescript|node\.?js|framework)', right=False) + r'|프레임워크|백엔드)[ \t]*(?:[/·:+-][ \t]*)?$', re.I)


def _stack_names(text: str) -> set[str]:
    """동사 express·계절 spring은 주변의 명시적 프레임워크 표현 없이 스택으로 단정하지 않는다."""
    found = set()
    for name, rx in _stack_patterns.items():
        for match in rx.finditer(text):
            if name in ('spring', 'express') and match.group().casefold() == name:
                line = text[:match.start()].rsplit('\n', 1)[-1] + match.group() + text[match.end():].split('\n', 1)[0]
                if (line.strip().casefold() != name
                        and not _framework_after.search(text[match.end():])
                        and not _framework_before.search(text[:match.start()])):
                    continue
            found.add(name)
            break
    return found


def normalize(value: object) -> str:
    """조합형 한글도 검색과 원문 발췌에서 같은 문자로 비교한다."""
    return unicodedata.normalize('NFKC', str(value or ''))


# Cosmos DB·Redis는 여러 용도로 쓰인다. 제품과 함께 가르치는 자료 접근이 있어야 NoSQL 근거로 쓴다.
_nosql_model = re.compile(r'키\s*[-·–]?\s*값\s*(?:저장소|데이터베이스)|문서\s*(?:형|지향)\s*(?:데이터베이스|저장소)'
                          + '|' + _en(r'key[- ]value (?:stores?|databases?)|document(?:[- ]oriented)? databases?|document stores?'), re.I)
_nosql_platform = re.compile(_en(r'cosmos\s*db|redis') + r'|레디스', re.I)
_record_access = (r'(?:컨테이너|컬렉션|문서|항목|키\s*[-·–]?\s*값)\s*(?:을|를|의|에서)?\s*'
                  r'(?:쿼리|질의|조회|읽기|쓰기|저장|갱신|삭제)|' + _en(r'point reads?|(?:query|read|write) (?:items?|documents?|containers?)'))
_nosql_access = re.compile(_record_access, re.I)
_direct_query = r'\s*(?:에서|로|의)?\s*(?:쿼리|질의|' + _en(r'queries|query|GET\s*/\s*SET') + ')'
_named_nosql_access = re.compile(
    rf'(?:{_nosql_platform.pattern})(?:{_direct_query}|[^.!?\n]{{0,60}}?(?:{_record_access}))', re.I)

_sql_engines = {
    'postgresql': re.compile(r'postgres(?:ql)?|포스트그레', re.I),
    'mysql': re.compile(r'mysql|마이에스큐엘', re.I),
    'oracle': re.compile(r'oracle|오라클', re.I),
    'sqlserver': re.compile(r'mssql|sql\s*server|transact.sql', re.I),
    'sqlite': re.compile(r'sqlite', re.I),
}


def crash_core_scope(skill: dict) -> dict:
    """유효한 Crash 계획에서 자료가 충족해야 할 범위만 읽는다."""
    try:
        core = crash_core_fields(skill)
    except ValueError:
        return {}
    return {key: core[key] for key in ('coreOutcome', 'coreCriteria')} if core else {}


def _target_texts(skill: dict, core: dict) -> list[str]:
    if core:
        return [core['coreOutcome'], *core['coreCriteria']]
    return ([str(skill.get(key) or '') for key in ('application', 'targetOutcome')]
            + [str(value) for value in skill.get('completionCriteria') or []])


def _core_stack_names(texts: list[str]) -> set[str]:
    """Crash 요구와 자료의 적용 기술을 같은 경계·문맥 규칙으로 읽는다."""
    found = set()
    for text in texts:
        text = canonical_versions(normalize(text)).casefold()
        patterns = {}
        for name in _stack_names(text):
            # 정규식 별칭(Spring Boot·Express.js 등)은 유지하고 단어 경계는 생성 검증과 맞춘다.
            variants = tuple(sorted({match[0] for match in _stack_patterns[name].finditer(text)}))
            patterns[name] = technology_pattern(variants[0], variants[1:])
        found.update(applied_technologies([text], patterns))
    return found


def _skill_context(skill: dict) -> str:
    return normalize(' '.join(_target_texts(skill, crash_core_scope(skill)))).casefold()


@lru_cache(maxsize=1)
def _known_skill_terms():
    return tuple(pattern for family in _aliases for pattern in skill_terms({'name': family}))


def course_selection(project: dict, selection: dict, course: dict | None) -> dict:
    """강좌 관련성은 직원의 목표와 스킬로 판단한다. 생성된 코스 문장은 정렬·설명용이다."""
    skill_labels = {normalize(skill['name']).casefold() for skill in selection['skills']}
    fields = list(dict.fromkeys(str(project.get(k) or '').strip()
                                  for k in ('goal', 'desiredCompetencies', 'projectSummary')
                                  if k != 'desiredCompetencies'
                                  or normalize(project.get(k)).casefold() not in skill_labels))
    goal = ' '.join(filter(None, fields))
    scoped = bool((course or {}).get('learningSkills'))
    if not scoped:
        return {'skills': [dict(name=s['name'], fromEmployeeGoal=False, application=s.get('application') or goal)
                           for s in selection['skills']]}
    # 코스 생성 전 공통 사전점검의 스킬별 적용 범위만 사용한다. 그 값이 없는 이전 입력도
    # 직원이 다른 기술에 명시한 행동(예: Docker 배포)을 Python의 요구 단계로 옮기지 않는다.
    clauses = []
    for field in fields:
        for clause in re.split(r'(?<=[.!?;])\s+|\n+|(?<=하고)\s+|(?<=하며)\s+|,\s+|\s+and\s+', field, flags=re.I):
            if clause.strip():
                value = normalize(clause.strip()).casefold()
                clauses.append((clause.strip(), value, bool(evidence.matches(value, _known_skill_terms()))))
    applications = selection.get('commonApplications') or {}
    skills = []
    for skill in selection['skills']:
        name = skill['name']
        terms = skill_terms(skill)
        own = [bool(evidence.matches(value, terms)) for _, value, _ in clauses]
        # 형제 스킬의 선택 여부와 무관하게 같은 목표·스킬이면 같은 범위를 사용한다.
        kept = [c for (c, _, named), match in zip(clauses, own) if match or not named]
        relevant = ' '.join(kept) if any(own) and len(kept) < len(clauses) else goal
        application = applications.get(name) or ''
        skills.append(dict(name=name, fromEmployeeGoal=True, application=relevant,
                           stageApplication=application or relevant))
    return {'skills': skills}


def _task_topics(skill):
    from app.services import course_focus
    return course_focus.task_topics(skill['name'], skill.get('stageApplication') or _skill_context(skill))


def requested_topics(skill):
    from app.services import course_focus
    return course_focus.requested(skill['name'], _skill_context(skill)) + _task_topics(skill)


def focus_priority(info, name):
    profile = info.get('suitability', {}).get(name, {})
    if (name not in info['supported'] or not info.get('scopeEvidence', {}).get(name, True)
            or profile.get('missingStack') or profile.get('conflictingStack') or target_gaps(info, name)):
        return 0
    return info.get('focusScores', {}).get(name, 0)


def _goal_context(project: dict, skill: dict) -> str:
    return '' if crash_core_scope(skill) or skill.get('fromEmployeeGoal') else normalize(project.get('goal')).casefold()


def _dbt_targets(skill: dict) -> tuple[re.Pattern, ...]:
    context = _skill_context(skill)
    if not (_dbt.search(context) and re.search(r'ETL|파이프라인', skill['name'], re.I)):
        return ()
    return tuple(unit for request, unit in _etl_targets if request.search(context))


def _dbt_target_labels(skill: dict) -> list[tuple[str, re.Pattern]]:
    context = _skill_context(skill)
    if not (_dbt.search(context) and re.search(r'ETL|파이프라인', skill['name'], re.I)):
        return []
    return [(label, unit) for label, (request, unit) in zip(_ETL_TARGET_LABELS, _etl_targets) if request.search(context)]


def _missing_targets(skill: dict, name: str, stage: str, applied: list[str]) -> list[str]:
    """목표에 명시한 세부 대상이 요구 단계의 단원·소개에 없으면 표시한다. 부분 자료를 전체 충족으로 세지 않는다."""
    if stage == 'conceptual':
        return []
    context = _skill_context(skill)
    missing = [label for label, skill_pattern, request, proof in _scope_topics
               if label and re.search(skill_pattern, name, re.I) and re.search(request, context, re.I)
               and not any(re.search(proof, value, re.I) for value in applied)]
    missing += [label for label, unit in _dbt_target_labels(skill) if not any(unit.search(value) for value in applied)]
    return missing


def target_gaps(info: dict, skill: str) -> list[str]:
    return list(((info.get('suitability') or {}).get(skill) or {}).get('unverifiedTargetTopics') or [])


def _dbt_facets(row: dict, value: str, targets: tuple[re.Pattern, ...]) -> set[int]:
    if not targets or not _dbt.search(value + ' ' + normalize(row.get('section'))):
        return set()
    return {index for index, target in enumerate(targets) if target.search(value)}


def _linux_security_target(skill: dict) -> bool:
    return bool(re.search(r'보안|security', skill['name'], re.I) and _linux.search(_skill_context(skill)))


def _stage(project: dict, skill: dict) -> str:
    core = crash_core_scope(skill)
    local = normalize(skill.get('stageApplication') or ' '.join(_target_texts(skill, core))).casefold()
    goal = _goal_context(project, skill)
    name = normalize(skill['name'])
    # 핵심 기준에 보안 검증을 명시했다면 개념 설명만으로 충족할 수 없다.
    if core and _security.search(local) and _security_action.search(local):
        return 'security'
    # 입문·원리 학습은 구현 프로젝트에서도 독립적인 학습 단계로 남긴다.
    if _concept.search(local) and not (_build.search(local) or _operate.search(local)):
        return 'conceptual'
    if _linux_security_target(skill):
        return 'security'
    if _security.search(local or goal) and _security_action.search(local or goal):
        return 'security'
    if _operate.search(local) or ('MLOps' in name and _operate.search(goal)):
        return 'operate'
    if _build.search(local) or (_log_topic.search(local) and _log_operation.search(local)):
        return 'build'
    if _design.search(local):
        return 'design'
    if re.search(r'기초|개론|이론', name) and not re.search(r'Python|파이썬', name, re.I):
        return 'conceptual'
    if _build.search(goal) or _operate.search(goal):
        return 'build'
    return 'conceptual'


def _stack_evidence(text: str, applied: list[str], project: dict, skill: dict, stage: str) -> tuple[list[str], list[str], list[str]]:
    core = crash_core_scope(skill)
    local = normalize(' '.join(_target_texts(skill, core))).casefold()
    context = local if core else normalize(project.get('goal')) + ' ' + local
    employee_scope = skill.get('fromEmployeeGoal')
    requested = _core_stack_names(_target_texts(skill, core)) if core or employee_scope else _stack_names(context)
    # Crash는 요구 단계의 긍정적 학습 근거만 기술 충족과 런타임 충돌에 사용한다.
    actual = _core_stack_names(applied) if core or employee_scope else _stack_names(text)
    name = normalize(skill['name'])
    web_skill = bool(re.search(r'웹\s*프레임워크|RESTful|API|백엔드', name, re.I))
    programming = bool(re.search(r'Python|파이썬|프로그래밍', name, re.I))
    cloud_skill = bool(re.search(r'클라우드|cloud', name, re.I))
    # 다른 스킬의 구현 스택은 개념 학습에 전파하지 않는다. 자체 도구를 명시한 학습은 예외다.
    if not core and not employee_scope and stage in ('conceptual', 'design', 'security'):
        required = _stack_names(local) & ({'aws', 'azure', 'gcp'} if cloud_skill else set())
        return sorted(required), sorted(required - set().union(*(_stack_names(value) for value in applied))), []
    if core:
        # 핵심 기준이 직접 명시한 기술은 스킬 태그가 넓거나 보안 검증 단계여도 확인한다.
        required = requested
    else:
        required = requested & _web_stacks if web_skill else set()
        if programming:
            required |= requested & {'python', 'java', 'javascript'}
        if cloud_skill:
            required |= requested & {'aws', 'azure', 'gcp'}
        if re.search(r'pytorch|tensorflow|파이토치|텐서플로', name, re.I):
            required |= _stack_names(local) & {'pytorch', 'tensorflow'}
    taught = actual if core or employee_scope else set().union(*(_stack_names(value) for value in applied))
    missing = required - taught
    conflicts = set()
    # RAG 구현은 다른 언어의 개념을 전이할 수 있으나 전용 구현을 동일한 실습으로 세지 않는다.
    if web_skill or re.search(r'RAG|MLOps|ETL|자연어|NLP', name, re.I):
        target_runtime = {_runtime.get(stack, stack) for stack in requested
                          if stack in _runtime or stack in {'python', 'java', 'javascript'}}
        actual_runtime = {_runtime.get(stack, stack) for stack in actual
                          if stack in _runtime or stack in {'python', 'java', 'javascript'}}
        if target_runtime and actual_runtime and not target_runtime & actual_runtime:
            conflicts |= actual_runtime
    return sorted(required), sorted(missing), sorted(conflicts)


def suitable(info: dict, skill: str) -> bool:
    profile = (info.get('suitability') or {}).get(skill)
    if profile is not None:
        return profile['suitable']
    return (skill in info['supported'] and info.get('scopeEvidence', {}).get(skill, True)
            and not (info.get('hasAnchors') and not info.get('anchorHits')))


def course_applicable(info: dict, skill: dict, *, allow_audit_gap: bool = False) -> bool:
    """세 코스가 공유하는 목표·스킬·실제 학습 근거 문턱. 계획의 코스별 예시는 요구하지 않는다."""
    name = skill['name']
    profile = info['suitability'][name]
    foundation = allow_audit_gap and profile.get('auditScopeFoundation', False)
    return bool(name in info['supported']
                and (foundation or (info['scopeEvidence'][name] and profile['evidenceLevel'] in ('applied', 'conceptual')))
                and not profile['missingStack'] and not profile['conflictingStack']
                and (not requested_topics(skill) or info.get('focusScores', {}).get(name, 0)))


def suitability_key(info: dict, skill: str) -> tuple:
    profile = (info.get('suitability') or {}).get(skill)
    if profile is None:
        return (skill not in info['supported'], False, bool(info.get('hasAnchors') and not info.get('anchorHits')),
                not info.get('scopeEvidence', {}).get(skill, True), 0)
    return (skill not in info['supported'], bool(profile['conflictingStack']),
            not info['scopeEvidence'].get(skill, True), profile['stageGap'], bool(profile['missingStack']))


def _profile(skill: dict, project: dict, rows: list, descriptions: list[str], text: str, supported: bool, scope: bool,
             *, terms, discussion_context: bool = False, focused_units=frozenset(), audit_only_gap=False) -> dict:
    stage = _stage(project, skill)
    name = normalize(skill['name'])
    etl_targets = _dbt_targets(skill)
    concurrency_skill = bool(re.search(r'Python|파이썬|멀티스레딩|동시성', name, re.I))
    linux_security = _linux_security_target(skill)
    course_related = bool(evidence.matches(text, terms))
    def related(value, section=''):
        if etl_targets:
            return bool(_dbt.search(value) or (_dbt.search(section) and any(target.search(value) for target in etl_targets)))
        if linux_security:
            return bool(not _windows.search(value + ' ' + section)
                        and (_linux_controls.search(value) or _os_controls.search(value)))
        if value in focused_units or evidence.matches(value, terms):
            return True
        if course_related and concurrency_skill and re.search(_async_io, value, re.I):
            return True
        if course_related and stage == 'security' and _security.search(value):
            return True
        if course_related and re.search(r'자연어|NLP', name, re.I) and (_nlp_objects.search(value) or _nlp_topics.search(value)):
            return True
        return bool(course_related and re.search(r'RAG', name, re.I) and _rag_objects.search(value))

    units = [(index, value) for index, row, value in rows if related(value, normalize(row.get('section')))]
    discussion_units = {index for index, row, value in rows if _question.search(value)
                        or (_discussion.search(normalize(row.get('section')) + ' ' + value)
                            and not _practice.search(value))}
    claims = [value.casefold() for value in descriptions if related(value.casefold())]
    # LLM·chatbot이라는 주제명만으로 UI·비즈니스 수업을 NLP 학습 근거로 바꾸지 않는다.
    if re.search(r'자연어|NLP', name, re.I):
        units = [(index, value) for index, value in units if not _business.search(value) or _nlp_objects.search(value)]
        claims = [value for value in claims if not _business.search(value) or _nlp_objects.search(value)]
    learning = [value for _, value in units] + claims
    def satisfies(value, stage):
        if stage in ('build', 'operate', 'security') and _intro_only.search(value) and not _practice.search(value):
            return False
        # 구체적인 주제와 작업을 함께 가르치는 차시는 '설계/구현'이라는 특정 낱말 없이도 근거다.
        # 보안·운영은 별도의 실제 검증·운영 행동 검사를 유지한다.
        if value in focused_units and stage in ('conceptual', 'design', 'build'):
            return True
        if stage == 'security':
            if linux_security:
                return bool((_os_controls.search(value) or _linux_controls.search(value))
                            and (_security_action.search(value) or _build.search(value) or _operate.search(value)))
            return bool(_security.search(value) and _security_action.search(value))
        if stage == 'operate':
            return bool(_operate.search(value) and not (_concept.search(value) and not _build.search(value)))
        if stage == 'design':
            return bool(_design.search(value))
        if stage == 'build':
            if value in focused_units and re.search(r'웹\s*프레임워크|RESTful', name, re.I):
                from app.services.course_focus import drf_practice
                if drf_practice(value):
                    return True
            return bool(_build.search(value) or (_log_topic.search(value) and _log_operation.search(value)) or (re.search(_async_io, value, re.I)
                        and (re.search(r'사용|취소|병렬\s*처리|' + _en(r'(?:cancell?\w*|await|asyncio\.\w+)'), value, re.I)
                             or (concurrency_skill and _io_workload.search(value) and _async_comparison.search(value)))))
        return bool(_concept.search(value) or _design.search(value) or _foundations.search(value)
                    or re.search(r'정합성 검증|성능 측정|부하 테스트|변경 모델링', value)
                    or _discussion.search(value) or _question.search(value)
                    or _build.search(value) or _operate.search(value) or _security.search(value))
    # '구현이 궁금해요'라는 질문과 '개발 팁'이라는 발표 소개는 구현 수업의 증거가 아니다.
    # 같은 강좌의 실제 실습 단원은 유지하며 개념 학습 목표에는 설명·토론도 허용한다.
    def applied_evidence(stage):
        allow_discussion = stage in ('conceptual', 'design')
        return ([(index, value) for index, value in units if satisfies(value, stage)
                 and (allow_discussion or index not in discussion_units)],
                [value for value in claims if satisfies(value, stage)
                 and (allow_discussion or (not _question.search(value)
                      and (not (_discussion.search(value) or discussion_context) or _practice.search(value))))])

    applied_units, applied_claims = applied_evidence(stage)
    applied = [value for _, value in applied_units] + applied_claims
    required, missing, conflicts = _stack_evidence(text, applied, project, skill, stage)
    if stage == 'security' and applied and missing and (core := crash_core_scope(skill)):
        # 명사형 결과물의 기술도 별도 구현 실습에서 확인한다. 보안에 명시된 기술은 보안 차시에서 확인한다.
        build_stacks, security_stacks = set(), set()
        for target in _target_texts(skill, core):
            if _security.search(target):
                security_stacks.update(_core_stack_names([target]))
            elif target == core['coreOutcome'] or _build.search(target):
                build_stacks.update(_core_stack_names([target]))
        separate_stacks = set(missing) & (build_stacks - security_stacks)
        if separate_stacks:
            build_units, build_claims = applied_evidence('build')
            practice = [value for _, value in build_units] + build_claims
            taught = _core_stack_names([value for value in practice
                                        if not _concept.search(value) or _practice.search(value)])
            missing = sorted(set(missing) - (separate_stacks & taught))
    task = _task_topics(skill)
    conceptual = [value for value in learning if _concept.search(value) or _design.search(value)
                  or _foundations.search(value) or _security.search(value)
                  or _discussion.search(value) or _question.search(value)
                  or (task and value in focused_units)]
    gap = 0 if applied else 1 if conceptual else 2 if supported else 3
    result = {'requiredStage': stage, 'evidenceLevel': ('applied' if applied and stage != 'conceptual'
            else 'conceptual' if applied or conceptual else 'mention' if supported else 'missing'),
            'stageGap': gap, 'requiredStack': required, 'missingStack': missing, 'conflictingStack': conflicts,
            'unitIndices': [index for index, value in applied_units][:3],
            'appliedDescription': applied_claims,
            'suitable': bool(supported and scope and gap == 0 and not missing and not conflicts)}
    missing_targets = _missing_targets(skill, name, stage, applied)
    if audit_only_gap:
        # 보안 실습 단계에서는 일반 SQL 조회 실습도 mention이 된다. 기초 차시·설명의 근거를 따로 확인한다.
        result['auditScopeFoundation'] = any(applied_evidence('conceptual'))
    if linux_security or missing_targets:
        result['unverifiedTargetTopics'] = [label for label, request, proof in _linux_security_topics
            if linux_security and request.search(_skill_context(skill))
            and not any(proof.search(value) for value in learning)] + missing_targets
    return result

def hours(item: dict) -> float | None:
    value = item.get('hours')
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None

def skill_terms(skill: dict):
    skill = dict(skill, name=normalize(skill['name']))
    for name, aliases in _aliases.items():
        if name.casefold() in skill['name'].casefold():
            return [re.compile(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])')
                    if re.fullmatch(r'[a-z0-9 ]+', term) else re.compile(re.escape(term)) for term in aliases]
    words = re.findall(r'[a-z0-9+#.]{2,}|[가-힣]{2,}', str(skill['name']).casefold())
    return evidence.query_terms([' '.join(word for word in words if word not in _generic)])


def _course_terms(skill: dict, title: str):
    terms = skill_terms(skill)
    if 'nosql' in skill['name'].casefold():
        # 제목에 제품명이 있으면 차시가 제품명을 반복할 필요가 없다.
        terms.extend((_nosql_model, _named_nosql_access))
        if _nosql_platform.search(title):
            terms.append(_nosql_access)
    return terms

def project_terms(project: dict):
    text = normalize(' '.join(str(project.get(key) or '') for key in ('goal', 'projectSummary', 'desiredCompetencies')))
    words = re.findall(r'[a-z0-9+#.]{2,}|[가-힣]{2,}', text.casefold())
    normalized = []
    for word in words:
        for ending in ('으로', '에서', '과', '와', '을', '를', '은', '는', '로'):
            if re.fullmatch(r'[가-힣]+', word) and len(word) > len(ending) + 1 and word.endswith(ending):
                word = word[:-len(ending)]
                break
        if word not in _generic:
            normalized.append(word)
    return evidence.query_terms([' '.join(normalized)])

def learning_rows(item: dict) -> list[tuple[int, dict, str]]:
    result = []
    for index, row in enumerate((item.get('curriculum') or {}).get('items') or []):
        if not isinstance(row, dict) or row.get('suspended') or row.get('title_missing'):
            continue
        parts = [normalize(row.get(key)) for key in ('section', 'title', 'description')]
        if any(_admin.search(part) for part in parts):
            continue
        if any(part.strip() and not evidence.learning_lines(part) for part in parts):
            continue
        # 섹션 이름을 모든 하위 단원의 학습 근거로 반복 인정하지 않는다.
        text = ' '.join(' '.join(evidence.learning_lines(part)) for part in parts[1:]).strip().casefold()
        if text:
            result.append((index, row, text))
    return result

def facts(item: dict, project: dict, selection: dict) -> dict:
    from app.services.course_focus import claims, lesson_score, profile_descriptions
    rows = learning_rows(item)
    # 수집 소개문에는 전체 목차가 붙기도 한다. 섹션명·중단 단원이 소개 근거로 재진입하지 않게 한다.
    outline_lines = {line.strip() for row in (item.get('curriculum') or {}).get('items') or [] if isinstance(row, dict)
                     for key in ('section', 'title', 'description') for line in normalize(row.get(key)).splitlines()}
    descriptions = [line for line in evidence.learning_lines(normalize(item.get('_learning_description') or item.get('content')),
                                                             description=True)
                    if not _admin.search(line) and line.strip() not in outline_lines]
    learning = '\n'.join([*descriptions, *(row[2] for row in rows)]).casefold()
    title = normalize(item.get('title')).casefold()
    text = title + '\n' + learning
    dbt_scoped = {skill['name'] for skill in selection['skills'] if (targets := _dbt_targets(skill))
                  and any(_dbt_facets(row, value, targets) for _, row, value in rows)}
    terms = {skill['name']: _course_terms(skill, title) for skill in selection['skills']}
    supported = [skill['name'] for skill in selection['skills'] if skill['name'] in (item.get('skills') or [])
                 and (skill['name'] in dbt_scoped or evidence.matches(text, terms[skill['name']]))]
    focused = {}
    focus_scores = {}
    for skill in selection['skills']:
        name = skill['name']
        topics = requested_topics(skill)
        units = [row[2] for row in rows] + list(claims(descriptions)) if topics else []
        scores = [(lesson_score(topics, title, unit), unit) for unit in units] if topics else []
        focus_scores[name] = max((score for score, _ in scores), default=0)
        focused[name] = {unit for score, unit in scores if score}
        if focused[name] and name in (item.get('skills') or []) and name not in supported:
            supported.append(name)
    topics = project_terms(project)
    hits = evidence.matches(text, topics)
    goal = normalize(project.get('goal')).casefold()
    anchors = set(re.findall(r'[a-z][a-z0-9+#./-]{1,}', goal)) - {'api', 'ai', 'db', 'data', 'model', 'server', 'web'}
    anchor_terms = evidence.query_terms([' '.join(anchors)])
    scope = {}
    document_gaps = set()
    audit_gaps = set()
    missing_audit = set()
    for skill in selection['skills']:
        context = _goal_context(project, skill) + ' ' + _skill_context(skill)
        scoped_analysis = bool(re.search(r'python|파이썬|EDA|탐색적', skill['name'], re.I) and _analysis_scope.search(context))
        scope[skill['name']] = not scoped_analysis or bool(_analysis_evidence.search(text))
        if (re.search(r'EDA|탐색적|머신러닝|\bSQL\b', skill['name'], re.I)
                and _audit_records.search(context) and _audit_analysis.search(context)):
            # 태그가 넓은 분석 강좌는 권한 로그를 실제로 다루는 차시·학습목표가 있어야 한다.
            # 다른 단원의 보안 단어와 일반 분석 실습을 이어 붙이지 않는다.
            audit_units = [unit for _, _, unit in rows
                           if _audit_analysis.search(unit) and (_audit_records.search(unit) or _audit_records.search(title))]
            audit_units.extend(line for line in claims(descriptions)
                               if _audit_records.search(line) and _audit_analysis.search(line))
            if not audit_units:
                missing_audit.add(skill['name'])
            elif _access_denial.search(context) and not any(_access_denial.search(u) for u in audit_units):
                audit_gaps.add(skill['name'])
        if skill.get('fromEmployeeGoal') and re.search(_en('sql|rdbms'), skill['name'], re.I):
            wanted = {k for k, pattern in _sql_engines.items() if pattern.search(context)}
            if wanted:
                covered = {k for k, pattern in _sql_engines.items() if pattern.search(text)}
                # 제품 비교 한 차시가 주된 실습 환경을 뒤집지 않게 제목·개별 차시를 확인한다.
                teaching = [title, *(value for _, _, value in rows)] if rows else [title, *descriptions]
                primary = {next(iter(engines)) for unit in teaching
                           if len(engines := {k for k in covered if _sql_engines[k].search(unit)}) == 1}
                platforms = primary or covered
                scope[skill['name']] &= not platforms or bool(wanted & platforms)
                if wanted & primary and focus_scores[skill['name']]:
                    focus_scores[skill['name']] += 1
        if re.search(r'python|파이썬', skill['name'], re.I) and _log_topic.search(context):
            scope[skill['name']] &= bool(_log_learning.search(text))
        if re.search(r'RAG|NLP|자연어', skill['name'], re.I) and _document_target.search(_skill_context(skill)):
            explicit = bool(_document_evidence.search(learning))
            # 문서 파서를 가정하지 않는다. 입력 매체에 종속되지 않는 실제 RAG 검색·구성은 핵심 일부에 해당한다.
            transferable = (not explicit and re.search(r'RAG', skill['name'], re.I) and not _media_search.search(title)
                            and (any(_rag_retrieval_practice.search(value)
                                     and not _media_search.search(normalize(row.get('section')) + ' ' + value)
                                     for _, row, value in rows)
                                 or any(_rag_retrieval_practice.search(line) and not _media_search.search(line)
                                        for line in descriptions)))
            scope[skill['name']] &= bool(explicit or transferable)
            if transferable:
                document_gaps.add(skill['name'])
        for _, skill_pattern, request, proof in _scope_topics:
            if re.search(skill_pattern, skill['name'], re.I) and re.search(request, _skill_context(skill), re.I):
                section_proof = proof == _dbt.pattern and skill['name'] in dbt_scoped
                scope[skill['name']] &= bool(re.search(proof, learning, re.I) or section_proof)
        if _linux_security_target(skill):
            linux_context = title + '\n' + '\n'.join(descriptions[:1]).casefold()
            scoped_units = [value + ' ' + normalize(row.get('section')) for _, row, value in rows] + descriptions
            scope[skill['name']] &= any(not _windows.search(unit) and (_linux_controls.search(unit)
                or (_os_controls.search(unit) and (_linux.search(unit) or _linux.search(linux_context))))
                for unit in scoped_units)
        if _linux.search(context) and re.search(r'멀티스레딩|동시성', skill['name'], re.I):
            # Windows 전용 GUI·시스템 동기화는 POSIX 서비스의 적용 근거로 공유하지 않는다.
            scope[skill['name']] &= not (_windows.search(title) and not _linux.search(title))
    # 다른 범위 검사까지 실패한 강좌는 접근 로그 차시만 미확인인 보충 후보에 넣지 않는다.
    audit_only_gaps = {name for name in missing_audit if scope[name]}
    for name in missing_audit:
        scope[name] = False
    discussion_context = bool(_discussion.search(normalize(item.get('title')) + '\n' + '\n'.join(descriptions)))
    profiles = {skill['name']: _profile(skill, project, rows, profile_descriptions(descriptions, focused[skill['name']]), text,
                                       skill['name'] in supported, scope[skill['name']], terms=terms[skill['name']],
                                       discussion_context=discussion_context, focused_units=focused[skill['name']],
                                       audit_only_gap=skill['name'] in audit_only_gaps) for skill in selection['skills']}
    for name in document_gaps:
        profiles[name]['unverifiedTargetTopics'] = [*target_gaps({'suitability': profiles}, name), '문서 입력·전처리']
    for name in audit_gaps:
        profiles[name].setdefault('unverifiedTargetTopics', []).append('접근 거절 사례 판별')
    for name in missing_audit:
        profiles[name].setdefault('unverifiedTargetTopics', []).append('접근 로그 분석')
    return {'rows': rows, 'descriptions': descriptions, 'title': title, 'supported': supported,
            'focusScores': focus_scores, 'focusedUnits': focused,
            'scopeEvidence': scope, 'suitability': profiles, 'topicHits': hits,
            'topicCoverage': hits / len(topics) if topics else 1,
            'hasAnchors': bool(anchor_terms), 'anchorHits': evidence.matches(text, anchor_terms)}

def focus_terms(project: dict, skill: dict, *, goal_only=False):
    """일반 행동어보다 문서·로그 같은 학습 대상을 찾고 표현 차이를 보완한다."""
    core = crash_core_scope(skill)
    texts = [] if core else [str(project.get('goal') or '')]
    if not goal_only:
        texts += _target_texts(skill, core)
    normalized = []
    for text in texts:
        words = re.findall(r'[a-z0-9+#.]{2,}|[가-힣]{2,}', normalize(text).casefold())
        for index, word in enumerate(words):
            for ending in ('으로', '에서', '까지', '하는', '하고', '과', '와', '을', '를', '은', '는', '의', '로'):
                if re.fullmatch(r'[가-힣]+', word) and len(word) > len(ending) + 1 and word.endswith(ending):
                    words[index] = word[:-len(ending)]
                    break
        normalized.append(' '.join(word for word in words if word not in _generic))
    terms = evidence.depth_terms(normalized)
    context = ' '.join(normalized)
    aliases = {'문서': ('pdf', 'document', '텍스트'), '질의': ('질문', 'query', 'qa'),
               '로그': ('logging', 'log'), '배치': ('batch',), '임베딩': ('embedding', 'embeddings')}
    for word, synonyms in aliases.items():
        if word in context:
            terms += evidence.query_terms(list(synonyms))
    if re.search(_async_io, context, re.I):
        terms.append(re.compile(_async_io, re.I))
    if re.search(r'동기화|경쟁\s*(?:상태|조건)|' + _en(r'(?:synchronization|race condition)'), context, re.I):
        terms.append(re.compile(r'동기화|경쟁\s*(?:상태|조건)|교착\s*상태|' + _en(r'(?:synchronization|race conditions?|locks?|mutex|deadlocks?|semaphores?)'), re.I))
    return list({term.pattern: term for term in terms}.values())


def outline(item: dict, project: dict, selection: dict, skill: dict, course=None, *, info=None) -> list[dict]:
    info = facts(item, project, selection) if info is None else info
    local = focus_terms({}, skill) or focus_terms(project, skill)
    if _linux_security_target(skill):
        local = [*local, _os_controls, _linux_controls]
    topic = focus_terms(project, skill, goal_only=True)
    terms = _course_terms(skill, info['title'])
    challenge = (course.get('id') if isinstance(course, dict) else course) == 'A3'
    profile = (info.get('suitability') or {}).get(skill['name']) or {}
    stage_units = set(profile.get('unitIndices') or []) if profile.get('requiredStage') != 'conceptual' else set()
    dbt_targets = _dbt_targets(skill)
    facets = {index: _dbt_facets(row, text, dbt_targets) for index, row, text in info['rows']} if dbt_targets else {}

    def score(row):
        text = row[2]
        focused, tagged = evidence.matches(text, local), evidence.matches(text, terms)
        targeted = facets.get(row[0], set())
        direct = text in info.get('focusedUnits', {}).get(skill['name'], ())
        related = direct or focused or tagged or targeted or evidence.matches(text, topic) or row[0] in stage_units
        depth = len(_depth.findall(text)) if challenge and (focused or tagged) and _depth_evidence(text) else 0
        return (4 * min(focused, 4) + 2 * min(tagged, 2) + min(evidence.matches(text, topic), 3)
                + 3 * min(depth, 2) + 4 * (row[0] in stage_units) + 6 * len(targeted)
                + 3 * bool(targeted and not _concept.search(text)) + 4 * direct) if related else 0

    remaining = [row for row in info['rows'] if score(row) > 0]
    ordered, covered, covered_facets = [], set(), set()
    # 실제 적용 단원이 있는데 소개 발췌만 보여 모델이 근거를 재확인하지 못하는 경우를 피한다.
    from app.services.course_focus import lesson_score
    task = _task_topics(skill)
    def task_score(row):
        return lesson_score(task, info['title'], row[2]) if task else 0
    task_rows = [row for row in remaining if task_score(row)]
    grounded = task_rows or [row for row in remaining if row[0] in stage_units]
    if grounded:
        chosen = max(grounded, key=lambda row: (task_score(row), score(row), -row[0]))
        ordered.append(chosen)
        covered.update(i for i, term in enumerate(local) if term.search(chosen[2]))
        covered_facets.update(facets.get(chosen[0], ()))
        remaining.remove(chosen)
    # 같은 '이미지 검색 구현' 단원 세 개가 문서 QA·임베딩 근거를 밀어내지 않도록 새 주제도 우선한다.
    while remaining and len(ordered) < 3:
        chosen = max(remaining, key=lambda row: (len(facets.get(row[0], set()) - covered_facets),
                                                len({i for i, term in enumerate(local) if term.search(row[2])} - covered),
                                                score(row), -row[0]))
        ordered.append(chosen)
        covered.update(i for i, term in enumerate(local) if term.search(chosen[2]))
        covered_facets.update(facets.get(chosen[0], ()))
        remaining.remove(chosen)
    return [{'index': index, 'section': normalize(row.get('section'))[:100], 'title': normalize(row.get('title'))[:100],
             **({'description': evidence.excerpt(' '.join(evidence.learning_lines(normalize(row['description']))),
                                                 local + terms, 160)} if row.get('description') else {})}
            for index, row, text in ordered if score((index, row, text)) > 0][:3]


def _depth_evidence(text: str) -> bool:
    return bool(_depth.search(text) and not (_admin.search(text) or _discussion.search(text) or _question.search(text))
                and (not _intro_only.search(text) or _practice.search(text)))


def description_excerpt(info: dict, project: dict, skill: dict, course=None) -> str:
    """순위에 사용한 학습 소개를 모델에 발췌한다. 선수지식·목차 복제본은 제외한다."""
    local = focus_terms({}, skill) or focus_terms(project, skill)
    terms = _course_terms(skill, info['title'])
    applied = set(info['suitability'][skill['name']]['appliedDescription'])
    challenge = (course.get('id') if isinstance(course, dict) else course) == 'A3'
    async_target = bool(re.search(_async_io, _skill_context(skill), re.I))
    dbt_targets = _dbt_targets(skill)
    from app.services.course_focus import lesson_score, profile_descriptions
    task = _task_topics(skill)
    descriptions = profile_descriptions(info['descriptions'], info['focusedUnits'][skill['name']])
    lines = sorted(dict.fromkeys(descriptions), key=lambda line: (
        -len(_dbt_facets({}, line, dbt_targets)),
        -lesson_score(task, info['title'], line.casefold()) if task else 0,
        -bool(async_target and _async_context.search(line)),
        -evidence.matches(line.casefold(), local),
        -bool(challenge and _depth_evidence(line) and evidence.matches(line.casefold(), local + terms)),
        -evidence.matches(line.casefold(), terms), line.casefold() not in applied,
        not (async_target and len(line) >= 60)))
    picked = lines[:1]
    if applied and not any(line.casefold() in applied for line in picked):
        picked.append(next(line for line in lines if line.casefold() in applied))
    budget = 350 if len(picked) == 1 else 170
    return '\n'.join(evidence.excerpt(line, local + terms, budget) for line in picked)


def _rank_signals(info: dict, project: dict, skill: dict, challenge: bool) -> tuple[int, int, int]:
    local = focus_terms({}, skill) or focus_terms(project, skill)
    tagged = _course_terms(skill, info['title'])
    learning = {text for _, _, text in info['rows']} | {line.casefold() for line in info['descriptions']}
    # 같은 홍보 문구와 일반 행동어의 반복은 점수가 되지 않는다. 서로 다른 대상의 동시 근거만 센다.
    focus = max((min(evidence.matches(text, local), 2) for text in learning), default=0)
    depth = int(challenge and any(_depth_evidence(text) and evidence.matches(text, local or tagged)
                                  and evidence.matches(text, tagged) for text in learning))
    title = min(evidence.matches(info['title'], local), 2)
    return focus, depth, title


def rank_applicable(rows: list[dict], project: dict, selection: dict, skill: dict, course,
                    *, limit: int, sources: dict, cache: dict) -> list[dict]:
    """단계·스택·범위 다음으로 단원/소개 근거와 벡터 순위를 비교한다."""
    challenge = (course.get('id') if isinstance(course, dict) else course) == 'A3'

    def key(row):
        if row['id'] not in cache:
            cache[row['id']] = facts(sources.get(row['id'], row), project, selection)
        info = cache[row['id']]
        focus, depth, title = _rank_signals(info, project, skill, challenge)
        band = course_levels.preference(sources.get(row['id'], row), 'A3') if challenge else 0
        practice = focus_priority(info, skill['name'])
        # 같은 목표 실습을 다루면 Challenge에서는 키워드 일치 횟수보다 심화 차시와 수준을 앞세운다.
        return (band, not bool(practice), not suitable(info, skill['name']), -depth, -practice, *suitability_key(info, skill['name']),
                len(target_gaps(info, skill['name'])), -focus,
                -float(row.get('retrievalScore') or 0), -title, row['id'])

    from app.services.course_focus import distinct_courses
    track = (course.get('id') if isinstance(course, dict) else course)
    eligible = []
    for row in rows:
        source = {**sources.get(row['id'], row), 'cost': row.get('cost')}
        if not course_levels.eligible(source, track):
            continue
        if row['id'] not in cache:
            cache[row['id']] = facts(sources.get(row['id'], row), project, selection)
        if course_applicable(cache[row['id']], skill, allow_audit_gap=True):
            eligible.append(row)
    return distinct_courses(sorted(eligible, key=key))[:limit]

"""세 코스의 실제 학습 근거·관련 단원. 태그와 선수지식만으로 학습 내용을 단정하지 않는다."""
from __future__ import annotations

import math
import re
import unicodedata
from app import catalog_candidates as evidence

_generic = {'기초', '실무', '활용', '학습', '이해', '환경', '프로그래밍', '아키텍처', '컴퓨팅',
            '프로젝트', '역량', '적용', '구현', '개발', '기술', '지식', '및', '기반',
            '사내', '업무', '만들기', '만들', '하기', '개선'}

_aliases = {
    'Python': ('python', '파이썬', 'asyncio'),
    'RAG': ('rag', '검색 증강', '검색증강', 'retrieval', 'langchain', '랭체인'),
    '자연어': ('nlp', '자연어', 'llm', '언어 모델', '언어모델', '토큰화', '임베딩', 'chatbot', '챗봇'),
    'RESTful': ('rest', 'restful', 'api', 'fastapi'),
    '웹 프레임워크': ('fastapi', 'django', '장고', '프레임워크', 'framework'),
    'Docker': ('docker', '도커', '컨테이너', 'container'),
    '클라우드': ('aws', 'azure', '클라우드', 'cloud', 'gcp'),
    'CI/CD': ('ci', 'cd', 'gitlab', 'github actions', '젠킨스', 'jenkins', '지속적 통합', '지속적 배포'),
    'MLOps': ('mlops', '모델 서빙', '모델서빙', '모델 배포', '모델배포', 'model serving', 'model deployment',
              '머신러닝 파이프라인', '기계학습 파이프라인'),
    'RDBMS': ('rdbms', '모델링', '정규화', '관계형', '데이터베이스 설계'),
    'SQL': ('sql', '조인', '쿼리'),
    'EDA': ('eda', '탐색적', '전처리', 'pandas', '판다스', '데이터 분석'),
    'ETL': ('etl', 'elt', '파이프라인', 'pipeline', '데이터 적재', '데이터 수집', '데이터 변환'),
    '리눅스': ('linux', '리눅스', 'bash', 'shell', '쉘'),
    '머신러닝': ('머신러닝', '기계학습', 'machine learning', '분류', '회귀', '지도 학습', '비지도 학습'),
}

# 특정 학습 주제가 명시됐을 때만 구분한다. 긴 본문의 일반 단어 일치율을 문턱으로 삼지 않는다.
_analysis_scope = re.compile(r'데이터\s*분석|전처리|탐색적|\b(?:data\s+analysis|pandas|eda)\b', re.I)
_analysis_evidence = re.compile(r'데이터\s*분석|전처리|탐색적|시각화|\b(?:data\s+analysis|pandas|eda|dataframe)\b', re.I)
_depth = re.compile(r'설계|비교|검증|측정|평가|최적화|문제\s*해결|트러블슈팅|\b(?:design|compar\w*|validat\w*|evaluat\w*|optimi\w*|benchmark|troubleshoot\w*)\b', re.I)
_admin = re.compile(r'만족도|수강\s*후기|강의\s*평가|과정\s*평가|설문\s*조사|\b(?:course evaluation|feedback survey)\b', re.I)
_log_word = r'(?:(?<![가-힣])|(?:운영|서버|배치|시스템|보안|이벤트|웹)\s*)로그(?!인|아웃|손실|우도|함수|리즘)'
_log_topic = re.compile(_log_word + r'|\b(?:logs?|logging)\b', re.I)
_log_learning = re.compile(_log_word + r'|파싱|정규\s*표현|파일.{0,15}(?:읽|처리)|예외.{0,15}테스트|\b(?:logging|parsing|pytest|fixture|stderr|batch)\b', re.I)

_build = re.compile(r'만들|구현|구축|개발|실습|연동|실행|구성|빌드|코드\s*작성|파싱|조회|\b(?:build\w*|implement\w*|develop\w*|integrat\w*|hands[- ]on|labs?|execut\w*)\b', re.I)
_operate = re.compile(r'배포|서빙|모니터링|롤백|복구|\b(?:deploy\w*|serving|monitor\w*|rollback|recover\w*)\b', re.I)
_concept = re.compile(r'개념|원리|이론|구조|이해|설명|무엇|개요|소개|\b(?:concept\w*|theory|principle\w*|understand\w*|overview|introduct\w*)\b', re.I)
_intro_only = re.compile(r'소개|개요|이론|무엇|\b(?:overview|introduct\w*|theory)\b', re.I)
_practice = re.compile(r'실습|직접|코드.{0,12}(?:작성|구현|실행)|\b(?:hands[- ]on|labs?)\b', re.I)
_discussion = re.compile(r'경험\s*공유|경험담|(?:개발|활용)\s*팁|발표\s*세션|질의\s*응답\s*세션|Q\s*&\s*A|\b(?:experience sharing|panel discussion|development tips)\b', re.I)
_question = re.compile(r'^\s*(?:Q\s*[.:]|질문\s*[:.])|궁금(?:해|하|한)', re.I)
_foundations = re.compile(r'문법|자료형|함수|조인|정규화|쿼리|토큰|컨텍스트|임베딩|벡터|자료\s*구조|\b(?:syntax|types?|joins?|queries|tokens?|context|embeddings?|vectors?)\b', re.I)
_security = re.compile(r'보안|공격|권한|가드레일|신뢰\s*경계|레드\s*티밍|\b(?:security|attack\w*|guardrails?|red\s*team\w*|permission\w*)\b', re.I)
_security_action = re.compile(r'검증|시험|진단|관찰|점검|지도|분석|실습|테스트|\b(?:test\w*|audit\w*|inspect\w*|map\w*)\b', re.I)
_design = re.compile(r'설계|아키텍처|전략|\b(?:design|architect\w*|strateg\w*)\b', re.I)
_business = re.compile(r'서비스\s*디자인|비즈니스|고객\s*여정|(?<![a-z0-9])(?:UX|UI)(?![a-z0-9])|페르소나|아이데이션|시장|수익|\b(?:business|customer journey|ideation)\b', re.I)
_rag_objects = re.compile(r'\brag\b|검색\s*증강|챗봇|벡터|임베딩|색인|검색|재순위화|청크|지식\s*원본|\b(?:retriev\w*|embeddings?|vector\w*|chatbot\w*|indexing|rerank\w*|chunk\w*)\b', re.I)
_nlp_objects = re.compile(r'토큰|컨텍스트|언어\s*모델|임베딩|자연어|프롬프트|\b(?:tokens?|context|embeddings?|nlp|prompts?|language models?)\b', re.I)
_nlp_topics = re.compile(r'챗봇|\b(?:llms?|chatbots?)\b', re.I)

# 명시한 구현 도구만 해당 스킬에 적용한다. SQL 이론 등에 목표의 모든 영문 단어를 요구하지 않는다.
_stacks = {
    'fastapi': r'fastapi|패스트\s*API', 'django': r'django|장고', 'flask': r'flask|플라스크',
    'spring': r'spring(?:[ .-]*(?:boot|framework|ai|mvc|webflux|security|data|batch|cloud))?|스프링',
    'express': r'express(?:\.js)?|익스프레스', 'nestjs': r'nest\.?js',
    'python': r'python|파이썬', 'java': r'java|자바(?!스크립트)',
    'javascript': r'javascript|typescript|node\.?js|자바스크립트|타입스크립트',
    'aws': r'aws|아마존\s*웹', 'azure': r'azure|애저', 'gcp': r'gcp|google\s*cloud',
}
_stack_patterns = {name: re.compile(r'(?<![a-z0-9])(?:' + pattern + r')(?![a-z0-9])', re.I)
                   for name, pattern in _stacks.items()}
_web_stacks = {'fastapi', 'django', 'flask', 'spring', 'express', 'nestjs'}
_runtime = {'fastapi': 'python', 'django': 'python', 'flask': 'python', 'spring': 'java',
            'express': 'javascript', 'nestjs': 'javascript'}
_framework_after = re.compile(r'^[ \t]*(?:[/:-][ \t]*)?(?:(?:rest(?:ful)?|api|framework|server|middleware|router|routing|backend|web|rag)\b|으로|로|을|를|과|와|기반|기초|입문|설치|설정|활용|실습|구현|개발|서버|프레임워크)', re.I)
_framework_before = re.compile(r'(?:\b(?:java|javascript|typescript|node\.?js|framework)|프레임워크|백엔드)[ \t]*(?:[/·:+-][ \t]*)?$', re.I)


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


def _skill_context(skill: dict) -> str:
    return normalize(' '.join([str(skill.get(key) or '') for key in ('application', 'targetOutcome')]
                              + [str(value) for value in skill.get('completionCriteria') or []])).casefold()


def _stage(project: dict, skill: dict) -> str:
    local = _skill_context(skill)
    goal = normalize(project.get('goal')).casefold()
    name = normalize(skill['name'])
    # 입문·원리 학습은 구현 프로젝트에서도 독립적인 학습 단계로 남긴다.
    if _concept.search(local) and not (_build.search(local) or _operate.search(local)):
        return 'conceptual'
    if _security.search(local or goal) and _security_action.search(local or goal):
        return 'security'
    if _operate.search(local) or ('MLOps' in name and _operate.search(goal)):
        return 'operate'
    if _build.search(local):
        return 'build'
    if _design.search(local):
        return 'design'
    if re.search(r'기초|개론|이론', name) and not re.search(r'Python|파이썬', name, re.I):
        return 'conceptual'
    if _build.search(goal) or _operate.search(goal):
        return 'build'
    return 'conceptual'


def _stack_evidence(text: str, applied: list[str], project: dict, skill: dict, stage: str) -> tuple[list[str], list[str], list[str]]:
    if stage in ('conceptual', 'design', 'security'):
        return [], [], []
    context = normalize(project.get('goal')) + ' ' + _skill_context(skill)
    requested = _stack_names(context)
    actual = _stack_names(text)
    name = normalize(skill['name'])
    web_skill = bool(re.search(r'웹\s*프레임워크|RESTful|API|백엔드', name, re.I))
    programming = bool(re.search(r'Python|파이썬|프로그래밍', name, re.I))
    cloud_skill = bool(re.search(r'클라우드|cloud', name, re.I))
    required = (requested & _web_stacks if web_skill else set())
    if programming:
        required |= requested & {'python', 'java', 'javascript'}
    if cloud_skill:
        required |= requested & {'aws', 'azure', 'gcp'}
    taught = set().union(*(_stack_names(value) for value in applied))
    missing = required - taught
    conflicts = set()
    # RAG 구현은 다른 언어의 개념을 전이할 수 있으나 전용 구현을 동일한 실습으로 세지 않는다.
    if web_skill or re.search(r'RAG|MLOps|ETL|자연어', name, re.I):
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


def suitability_key(info: dict, skill: str) -> tuple:
    profile = (info.get('suitability') or {}).get(skill)
    if profile is None:
        return (skill not in info['supported'], False, bool(info.get('hasAnchors') and not info.get('anchorHits')),
                not info.get('scopeEvidence', {}).get(skill, True), 0)
    return (skill not in info['supported'], bool(profile['conflictingStack']), bool(profile['missingStack']),
            not info['scopeEvidence'].get(skill, True), profile['stageGap'])


def _profile(skill: dict, project: dict, rows: list, descriptions: list[str], text: str, supported: bool, scope: bool,
             *, discussion_context: bool = False) -> dict:
    stage = _stage(project, skill)
    terms = skill_terms(skill)
    name = normalize(skill['name'])
    course_related = bool(evidence.matches(text, terms))
    def related(value):
        if evidence.matches(value, terms):
            return True
        if course_related and stage == 'security' and _security.search(value):
            return True
        if course_related and re.search(r'자연어|NLP', name, re.I) and (_nlp_objects.search(value) or _nlp_topics.search(value)):
            return True
        return bool(course_related and re.search(r'RAG', name, re.I) and _rag_objects.search(value))

    units = [(index, value) for index, _, value in rows if related(value)]
    discussion_units = {index for index, row, value in rows if _question.search(value)
                        or (_discussion.search(normalize(row.get('section')) + ' ' + value)
                            and not _practice.search(value))}
    claims = [value.casefold() for value in descriptions if related(value.casefold())]
    # LLM·chatbot이라는 주제명만으로 UI·비즈니스 수업을 NLP 학습 근거로 바꾸지 않는다.
    if re.search(r'자연어|NLP', name, re.I):
        units = [(index, value) for index, value in units if not _business.search(value) or _nlp_objects.search(value)]
        claims = [value for value in claims if not _business.search(value) or _nlp_objects.search(value)]
    learning = [value for _, value in units] + claims
    def satisfies(value):
        if stage in ('build', 'operate', 'security') and _intro_only.search(value) and not _practice.search(value):
            return False
        if stage == 'security':
            return bool(_security.search(value) and _security_action.search(value))
        if stage == 'operate':
            return bool(_operate.search(value) and not (_concept.search(value) and not _build.search(value)))
        if stage == 'design':
            return bool(_design.search(value))
        if stage == 'build':
            return bool(_build.search(value))
        return bool(_concept.search(value) or _design.search(value) or _foundations.search(value)
                    or _discussion.search(value) or _question.search(value)
                    or _build.search(value) or _operate.search(value) or _security.search(value))
    # '구현이 궁금해요'라는 질문과 '개발 팁'이라는 발표 소개는 구현 수업의 증거가 아니다.
    # 같은 강좌의 실제 실습 단원은 유지하며 개념 학습 목표에는 설명·토론도 허용한다.
    applied_units = [(index, value) for index, value in units if satisfies(value)
                     and (stage in ('conceptual', 'design') or index not in discussion_units)]
    applied_claims = [value for value in claims if satisfies(value)
                      and (stage in ('conceptual', 'design')
                           or (not _question.search(value)
                               and (not (_discussion.search(value) or discussion_context) or _practice.search(value))))]
    applied = [value for _, value in applied_units] + applied_claims
    required, missing, conflicts = _stack_evidence(text, applied, project, skill, stage)
    conceptual = [value for value in learning if _concept.search(value) or _design.search(value)
                  or _foundations.search(value) or _security.search(value)
                  or _discussion.search(value) or _question.search(value)]
    gap = 0 if applied else 1 if conceptual else 2 if supported else 3
    return {'requiredStage': stage, 'evidenceLevel': ('applied' if applied and stage != 'conceptual'
            else 'conceptual' if applied or conceptual else 'mention' if supported else 'missing'),
            'stageGap': gap, 'requiredStack': required, 'missingStack': missing, 'conflictingStack': conflicts,
            'unitIndices': [index for index, value in applied_units][:3],
            'suitable': bool(supported and scope and gap == 0 and not missing and not conflicts)}

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
        result.append((index, row, ' '.join('\n'.join(evidence.learning_lines(part)) for part in parts[1:]).casefold()))
    return result

def facts(item: dict, project: dict, selection: dict) -> dict:
    rows = learning_rows(item)
    # 수집 소개문에는 전체 목차가 붙기도 한다. 섹션명·중단 단원이 소개 근거로 재진입하지 않게 한다.
    outline_lines = {line.strip() for row in (item.get('curriculum') or {}).get('items') or [] if isinstance(row, dict)
                     for key in ('section', 'title', 'description') for line in normalize(row.get(key)).splitlines()}
    descriptions = [line for line in evidence.learning_lines(normalize(item.get('_learning_description') or item.get('content')))
                    if not _admin.search(line) and line.strip() not in outline_lines]
    text = normalize(item.get('title')) + '\n' + '\n'.join(descriptions) + '\n' + '\n'.join(row[2] for row in rows)
    text = text.casefold()
    supported = [skill['name'] for skill in selection['skills'] if skill['name'] in (item.get('skills') or [])
                 and evidence.matches(text, skill_terms(skill))]
    topics = project_terms(project)
    hits = evidence.matches(text, topics)
    goal = normalize(project.get('goal')).casefold()
    anchors = set(re.findall(r'[a-z][a-z0-9+#./-]{1,}', goal)) - {'api', 'ai', 'db', 'data', 'model', 'server', 'web'}
    anchor_terms = evidence.query_terms([' '.join(anchors)])
    scope = {}
    for skill in selection['skills']:
        context = goal + ' ' + _skill_context(skill)
        scoped_analysis = bool(re.search(r'python|파이썬|EDA|탐색적', skill['name'], re.I) and _analysis_scope.search(context))
        scope[skill['name']] = not scoped_analysis or bool(_analysis_evidence.search(text))
        if re.search(r'python|파이썬', skill['name'], re.I) and _log_topic.search(context):
            scope[skill['name']] &= bool(_log_learning.search(text))
    discussion_context = bool(_discussion.search(normalize(item.get('title')) + '\n' + '\n'.join(descriptions)))
    profiles = {skill['name']: _profile(skill, project, rows, descriptions, text,
                                       skill['name'] in supported, scope[skill['name']],
                                       discussion_context=discussion_context) for skill in selection['skills']}
    return {'rows': rows, 'supported': supported, 'scopeEvidence': scope, 'suitability': profiles, 'topicHits': hits,
            'topicCoverage': hits / len(topics) if topics else 1,
            'hasAnchors': bool(anchor_terms), 'anchorHits': evidence.matches(text, anchor_terms)}

def focus_terms(project: dict, skill: dict, *, goal_only=False):
    """일반 행동어보다 문서·로그 같은 학습 대상을 찾고 표현 차이를 보완한다."""
    texts = [str(project.get('goal') or '')]
    if not goal_only:
        texts += [str(skill.get('application') or ''), str(skill.get('targetOutcome') or '')]
        texts += list(skill.get('completionCriteria') or [])
    normalized = []
    for text in texts:
        words = re.findall(r'[a-z0-9+#.]{2,}|[가-힣]{2,}', normalize(text).casefold())
        for index, word in enumerate(words):
            for ending in ('으로', '에서', '까지', '하는', '하고', '과', '와', '을', '를', '은', '는', '의', '로'):
                if re.fullmatch(r'[가-힣]+', word) and len(word) > len(ending) + 1 and word.endswith(ending):
                    words[index] = word[:-len(ending)]
                    break
        normalized.append(' '.join(words))
    terms = evidence.depth_terms(normalized)
    context = ' '.join(normalized)
    aliases = {'문서': ('pdf', 'document', '텍스트'), '질의': ('질문', 'query', 'qa'),
               '로그': ('logging', 'log'), '배치': ('batch',), '임베딩': ('embedding', 'embeddings')}
    for word, synonyms in aliases.items():
        if word in context:
            terms += evidence.query_terms(list(synonyms))
    return terms


def outline(item: dict, project: dict, selection: dict, skill: dict, course=None, *, info=None) -> list[dict]:
    info = facts(item, project, selection) if info is None else info
    local = focus_terms(project, skill)
    topic = focus_terms(project, skill, goal_only=True)
    terms = skill_terms(skill)
    challenge = (course.get('id') if isinstance(course, dict) else course) == 'A3'
    profile = (info.get('suitability') or {}).get(skill['name']) or {}
    stage_units = set(profile.get('unitIndices') or []) if profile.get('requiredStage') != 'conceptual' else set()

    def score(row):
        text = row[2]
        focused, tagged = evidence.matches(text, local), evidence.matches(text, terms)
        related = focused or tagged or evidence.matches(text, topic) or row[0] in stage_units
        depth = len(_depth.findall(text)) if challenge and related else 0
        return (4 * min(focused, 4) + 2 * min(tagged, 2) + min(evidence.matches(text, topic), 3)
                + 3 * min(depth, 2) + 4 * (row[0] in stage_units)) if related else 0

    remaining = [row for row in info['rows'] if score(row) > 0]
    ordered, covered = [], set()
    # 실제 적용 단원이 있는데 소개 발췌만 보여 모델이 근거를 재확인하지 못하는 경우를 피한다.
    grounded = [row for row in remaining if row[0] in stage_units]
    if grounded:
        chosen = max(grounded, key=lambda row: (score(row), -row[0]))
        ordered.append(chosen)
        covered.update(i for i, term in enumerate(local) if term.search(chosen[2]))
        remaining.remove(chosen)
    # 같은 '이미지 검색 구현' 단원 세 개가 문서 QA·임베딩 근거를 밀어내지 않도록 새 주제도 우선한다.
    while remaining and len(ordered) < 3:
        chosen = max(remaining, key=lambda row: (len({i for i, term in enumerate(local) if term.search(row[2])} - covered),
                                                score(row), -row[0]))
        ordered.append(chosen)
        covered.update(i for i, term in enumerate(local) if term.search(chosen[2]))
        remaining.remove(chosen)
    return [{'index': index, **{key: normalize(row.get(key))[:100] for key in ('section', 'title')}}
            for index, row, text in ordered if score((index, row, text)) > 0][:3]


def rank_applicable(rows: list[dict], project: dict, selection: dict, skill: dict, course,
                    *, limit: int, sources: dict, cache: dict) -> list[dict]:
    """Free/Challenge는 같은 단원의 적용 근거를 평가하고 벡터 순위로 동률을 정한다."""
    local = focus_terms(project, skill)
    challenge = (course.get('id') if isinstance(course, dict) else course) == 'A3'

    def key(row):
        if row['id'] not in cache:
            cache[row['id']] = facts(sources[row['id']], project, selection)
        info = cache[row['id']]
        scores = [(evidence.matches(text, local), min(len(_depth.findall(text)), 2))
                  for _, _, text in info['rows']]
        focused = [score for score in scores if score[0]]
        # 한 단원에 함께 나타난 근거만 사용하며 강좌 길이·전체 단어 수로 가점하지 않는다.
        scope = min(max((score[0] for score in focused), default=0), 4)
        depth = max((score[1] for score in focused), default=0) if challenge else 0
        return (*suitability_key(info, skill['name']), -scope, -depth, -min(len(focused), 3),
                -float(row.get('retrievalScore') or 0), row['id'])

    return sorted(rows, key=key)[:limit]

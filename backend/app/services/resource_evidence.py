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
    '자연어': ('nlp', '자연어', 'llm', '언어 모델', '언어모델', '토큰화', '임베딩'),
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
    for name, aliases in _aliases.items():
        if name.casefold() in skill['name'].casefold():
            return [re.compile(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])')
                    if re.fullmatch(r'[a-z0-9 ]+', term) else re.compile(re.escape(term)) for term in aliases]
    words = re.findall(r'[a-z0-9+#.]{2,}|[가-힣]{2,}', str(skill['name']).casefold())
    return evidence.query_terms([' '.join(word for word in words if word not in _generic)])

def project_terms(project: dict):
    text = ' '.join(str(project.get(key) or '') for key in ('goal', 'projectSummary', 'desiredCompetencies'))
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
        parts = [str(row.get(key) or '') for key in ('section', 'title', 'description')]
        if any(_admin.search(part) for part in parts):
            continue
        if any(part.strip() and not evidence.learning_lines(part) for part in parts):
            continue
        # 섹션 이름을 모든 하위 단원의 학습 근거로 반복 인정하지 않는다.
        result.append((index, row, ' '.join('\n'.join(evidence.learning_lines(part)) for part in parts[1:]).casefold()))
    return result

def facts(item: dict, project: dict, selection: dict) -> dict:
    rows = learning_rows(item)
    introduction = '\n'.join(evidence.learning_lines(item.get('_learning_description') or item.get('content') or ''))
    text = unicodedata.normalize('NFKC', str(item.get('title') or '') + '\n' + introduction + '\n' + '\n'.join(row[2] for row in rows)).casefold()
    supported = [skill['name'] for skill in selection['skills'] if skill['name'] in (item.get('skills') or [])
                 and evidence.matches(text, skill_terms(skill))]
    topics = project_terms(project)
    hits = evidence.matches(text, topics)
    goal = str(project.get('goal') or '').casefold()
    anchors = set(re.findall(r'[a-z][a-z0-9+#./-]{1,}', goal)) - {'api', 'ai', 'db', 'data', 'model', 'server', 'web'}
    anchor_terms = evidence.query_terms([' '.join(anchors)])
    scope = {}
    for skill in selection['skills']:
        context = goal + ' ' + str(skill.get('application') or '').casefold()
        scoped_analysis = bool(re.search(r'python|파이썬|EDA|탐색적', skill['name'], re.I) and _analysis_scope.search(context))
        scope[skill['name']] = not scoped_analysis or bool(_analysis_evidence.search(text))
        if re.search(r'python|파이썬', skill['name'], re.I) and _log_topic.search(context):
            scope[skill['name']] &= bool(_log_learning.search(text))
    return {'rows': rows, 'supported': supported, 'scopeEvidence': scope, 'topicHits': hits,
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
        words = re.findall(r'[a-z0-9+#.]{2,}|[가-힣]{2,}', text.casefold())
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

    def score(row):
        text = row[2]
        focused, tagged = evidence.matches(text, local), evidence.matches(text, terms)
        related = focused or tagged or evidence.matches(text, topic)
        depth = len(_depth.findall(text)) if challenge and related else 0
        return (4 * min(focused, 4) + 2 * min(tagged, 2) + min(evidence.matches(text, topic), 3)
                + 3 * min(depth, 2)) if related else 0

    remaining = [row for row in info['rows'] if score(row) > 0]
    ordered, covered = [], set()
    # 같은 '이미지 검색 구현' 단원 세 개가 문서 QA·임베딩 근거를 밀어내지 않도록 새 주제도 우선한다.
    while remaining and len(ordered) < 3:
        chosen = max(remaining, key=lambda row: (len({i for i, term in enumerate(local) if term.search(row[2])} - covered),
                                                score(row), -row[0]))
        ordered.append(chosen)
        covered.update(i for i, term in enumerate(local) if term.search(chosen[2]))
        remaining.remove(chosen)
    return [{'index': index, **{key: str(row.get(key) or '')[:100] for key in ('section', 'title')}}
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
        return (skill['name'] not in info['supported'], -scope, -depth, -min(len(focused), 3),
                -float(row.get('retrievalScore') or 0), row['id'])

    return sorted(rows, key=key)[:limit]

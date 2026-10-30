"""스킬별 후보 검색. 정규화는 캐시 갱신 때만, 안별 순위와 근거는 요청마다 계산한다."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from .catalog_evidence import content_text
from . import track_policy

PER_SKILL = 20
MAX_SKILLS = 5
DEFAULT_COUNT = 32
MAX_COUNT = 40
# DB Fast/Challenge 정책의 학습 행동. 제목의 홍보 문구만으로 실무 깊이를 판정하지 않는다.
_actions = {
    'build': re.compile(r'만들|구현|구축|연결|개발|실습|프로젝트|\b(?:build\w*|implement\w*|develop\w*|integrat\w*|project|hands[- ]on|labs?)\b', re.I),
    'verify': re.compile(r'테스트|평가|검증|벤치마크|품질|\b(?:test\w*|evaluat\w*|validat\w*|benchmark\w*)\b', re.I),
    'improve': re.compile(r'최적화|개선|문제\s*해결|트러블슈팅|디버깅|성능\s*튜닝|\b(?:optimi\w*|troubleshoot\w*|debug\w*|improv\w*)\b', re.I),
    'operate': re.compile(r'배포|모니터링|운영|복구|롤백|\b(?:deploy\w*|monitor\w*|production|observability|rollback|recover\w*)\b', re.I),
}
# 구현/배포 횟수와 구별하는 심화 근거. 목표에 맞는 개별 단원에서만 인정한다.
_depth_actions = {
    'design': re.compile(r'아키텍처|설계|트레이드\s*오프|대안\s*비교|전략\s*비교|배포\s*전략|모델.*?수명\s*주기|\b(?:architect\w*|design|trade[- ]?offs?|compar\w*)\b', re.I),
    'measure': re.compile(r'평가\s*(?:지표|기준)|성능\s*(?:평가|측정|비교|검증)|(?:부하|스트레스)\s*테스트|벤치마크|정확도|재현율|지연\s*(?:측정|분석)|(?:배포된\s*)?모델.*?모니터링|(?<![a-z0-9])(?:benchmark[a-z]*|metrics?|recall|precision|mrr|ndcg|latency|evaluation|load test[a-z]*)(?![a-z0-9])', re.I),
    'solve': re.compile(r'최적화|문제\s*해결|트러블슈팅|디버깅|(?:오류|장애|실패|병목|오답).*?(?:분석|원인|해결|대응|복구)|성능\s*(?:튜닝|개선)|(?:복구|권한|보안|공격).*?(?:검증|테스트)|(?:모델|배포).*?(?:승격|롤백)|\b(?:optimi\w*|troubleshoot\w*|debug\w*|root cause|performance tun\w*|failure analys\w*)\b', re.I),
}
_intro_lesson = re.compile(r'입문|첫걸음|맛보기|따라\s*하기|무엇인가|개념\s*(?:소개|설명|이해)|\b(?:introduct\w*|overview|step[- ]by[- ]step)\b', re.I)
_generic_topics = set('공개 샘플 예제 작은 기본 기초 전체 이전 이후 생성 결과 기능 연결 기록 환경 설정 구성 사용 적용 모델 데이터 개발 서비스 서버 입력 출력 도구 코드 처리 확인 내용 방법 목표 학습 업무 구현 실습 배포 운영 평가 검증 개선 분석 테스트 보강 성능 버전 기준 제한 부족 함께 위한 가능한 만들기 만들어요 해요 각각 관련 무료 등급 합성 보여 주는 나누고 분리해 찾아 사용한 없는 여부 기록해요 확인해요 제공하고 시험해요 묶어요 받는 표시하고 표시해요'.split())
_generic_topics.update('the and for with from into using use build implement develop test evaluate improve model data code example sample system service server'.split())
_context_topics = {'점검', '상태', '권한', '실행', '추론', '이미지', '접근', '지연', '오픈소스'}
_course_admin = re.compile(r'만족도|수강\s*후기|강의\s*평가|과정\s*평가|설문\s*조사|\b(?:course evaluation|feedback survey)\b', re.I)

_blocked = re.compile(r'^(?:학습자의\s*)?(?:선수\s*(?:지식|능력|학습)|선행\s*(?:지식|학습)|수강\s*대상|학습\s*대상|추천\s*대상|강사\s*(?:소개|경력)|prerequisites?|requirements?|target audience|instructor)\b', re.I)
_learning = re.compile(r'^(?:과정\s*소개|강좌\s*소개|수업\s*(?:소개|내용|목표)|학습\s*(?:목표|내용)|교육\s*(?:목표|내용)|커리큘럼|강의\s*계획|목차|개요|소개|overview|description|learning objectives?|curriculum|syllabus)\b', re.I)
_lock = threading.Lock()
_source: dict | None = None
_index: dict = {}


def learning_lines(value: str) -> list[str]:
    """명시된 선수지식/대상/강사 구역을 다음 학습 구역 전까지 제외한다."""
    result, blocked = [], False
    for line in content_text(value).splitlines():
        line = line.strip()
        if not line:
            continue
        if _blocked.search(line):
            blocked = True
        elif _learning.search(line):
            blocked = False
        if not blocked:
            result.append(line)
    return result


def cached_index(records: dict[str, dict]) -> dict:
    global _source, _index
    with _lock:
        if _source is not records:
            index = {}
            for key, r in records.items():
                lines = [line for line in learning_lines(r.get('_learning_description') or r.get('content') or '')
                         if not _course_admin.search(line)]
                outline = r.get('curriculum') or {}
                rows, lesson_units, own_rows = [], [], {}
                for number, row in enumerate(outline.get('items') or []):
                    if row.get('suspended') or row.get('title_missing'):
                        continue
                    parts = [str(row.get(k) or '').strip() for k in ('section', 'title', 'description')]
                    # 섹션 접두사 때문에 선수지식/과정 평가 제목이 숨지 않도록 각 필드를 검사한다.
                    if any(_blocked.search(line.strip()) or _course_admin.search(line)
                           for part in parts for line in part.splitlines()):
                        continue
                    text = ' · '.join(dict.fromkeys(part for part in parts if part))
                    if text:
                        rows.append((number, text, text.casefold()))
                        # 섹션명은 검색 문맥으로만 사용한다. 'RAG 실습'을 모든 하위 수업의 행동으로 세지 않는다.
                        own = ' · '.join(dict.fromkeys(part for part in parts[1:] if part))
                        if own:
                            lesson_units.append(own)
                            own_rows[number] = own
                # 단원 제목을 확보했으면 긴 소개/광고 문장으로 실무 근거를 추가하지 않는다.
                units = list(dict.fromkeys(lesson_units)) if rows else list(dict.fromkeys(lines))
                index[key] = {'record': r, 'skills': set(r.get('skills') or []), 'lines': lines,
                              'description': '\n'.join(lines).casefold(), 'rows': rows,
                              'own_rows': own_rows,
                              'own_outline': '\n'.join(lesson_units).casefold(),
                              'units': [(text.casefold(), {name for name, rx in _actions.items() if rx.search(text)},
                                         {name for name, rx in _depth_actions.items() if rx.search(text)}
                                         if not _intro_lesson.search(text) else set()) for text in units],
                              'query_profiles': {},
                              'outline': '\n'.join(row[2] for row in rows),
                              'dedup': (' '.join(r['title'].casefold().split()), r.get('provider', '').casefold(), r.get('type'))}
            _source, _index = records, index
        return _index


def query_terms(texts: list[str]) -> list[re.Pattern]:
    words = sorted(set(re.findall(r'[a-z0-9+#.]{2,}|[가-힣]{2,}', ' '.join(texts).casefold())))
    return [re.compile(r'(?<![a-z0-9])' + re.escape(w) + r'(?![a-z0-9])')
            if re.fullmatch(r'[a-z0-9+#.]+', w) else re.compile(re.escape(w))
            for w in words if re.search(r'[a-z가-힣]', w)]


def matches(text: str, terms: list[re.Pattern]) -> int:
    return sum(bool(term.search(text)) for term in terms)


def depth_terms(texts: list[str]) -> list[re.Pattern]:
    """'구현·개선·모델' 같은 일반어 일치만으로 무관한 심화 수업에 가점하지 않는다."""
    words = re.findall(r'[a-z0-9+#.]{2,}|[가-힣]{2,}', ' '.join(texts).casefold())
    ignored = _generic_topics | {word for word in _context_topics if word not in (texts[0] if texts else '')}
    # 조사만 붙은 일반어도 제외한다. 목표 자체의 권한·지연 같은 주제는 남긴다.
    ignored = ignored | {word + ending for word in ignored for ending in ('은', '는', '이', '가', '을', '를', '의', '로', '으로', '과', '와', '에', '에서')}
    terms = query_terms([word for word in words if word not in ignored
                        and not any(rx.search(word) for rx in (*_actions.values(), *_depth_actions.values()))])
    # '모델' 단독 오탐을 막으면서 실제 목표인 모델 배포·추론·운영의 결합 주제는 보존한다.
    if re.search(r'(?:모델|model).{0,30}(?:배포|서빙|추론|deploy|serving|inference)', ' '.join(texts), re.I):
        terms.extend(re.compile(pattern, re.I) for pattern in (
            r'(?:모델|model).{0,30}(?:배포|서빙|추론|모니터링|수명\s*주기|deploy|serving|inference|monitor|lifecycle)',
            r'(?:배포|서빙|deploy|serving).{0,30}(?:모델|model|아키텍처|설계|전략|롤백|승격|모니터링|architecture|design|rollback|monitor)',
        ))
    return terms


def excerpt(text: str, terms: list[re.Pattern], limit: int) -> str:
    positions = [m.start() for term in terms if (m := term.search(text.casefold()))]
    start = max(0, min(positions) - limit // 3) if positions and len(text) > limit else 0
    return text[start:start + limit]


@dataclass
class Selection:
    records: list[dict]
    skills: list[str]
    terms: list[re.Pattern]
    required: list[str]
    per_skill: dict[str, int]
    excluded: list[str]
    index: dict
    track: str = 'A1'
    assessments: dict = field(default_factory=dict)
    topics: list[re.Pattern] = field(default_factory=list)


def track_fit(x: dict, terms: list[re.Pattern], track: str, topics: list[re.Pattern]) -> dict:
    """목표 관련 학습 단원의 집중도(Fast) / 구현 후 검증·개선 깊이(Challenge).

    점수는 0~1이며 관련성에 최대 같은 크기만 가산한다. 후보 사이의 중복 여부는 사용하지 않는다.
    실습 한 단어·난이도·시간만으로 Challenge 적합도를 높이지 않는다.
    """
    key = (tuple(term.pattern for term in terms), tuple(term.pattern for term in topics))
    with _lock:
        profile = x['query_profiles'].get(key) if track != 'A1' else None
    if profile is None:
        units = x['units']
        related = [(text, actions, depth) for text, actions, depth in units if any(term.search(text) for term in terms)] if track != 'A1' else []
        relevant = [actions for text, actions, depth in related]
        practical = [actions for actions in relevant if actions]
        depth = [depth for text, actions, depth in related if depth and any(term.search(text) for term in topics)]
        profile = {'relatedUnits': len(relevant), 'totalUnits': len(units), 'practiceUnits': len(practical),
                   'buildUnits': sum('build' in actions for actions in relevant),
                   'depthUnits': len(depth), 'depthActions': sorted(set().union(*depth)) if depth else [],
                   'actions': sorted(set().union(*practical)) if practical else []}
        if track != 'A1':
            # 안별 같은 목표를 다시 스캔하지 않는다. 카탈로그 갱신 시 함께 폐기하고 자료당 4개 질의로 제한한다.
            with _lock:
                if len(x['query_profiles']) >= 4:
                    x['query_profiles'].pop(next(iter(x['query_profiles'])))
                x['query_profiles'][key] = profile
    focus = profile['relatedUnits'] / profile['totalUnits'] if profile['totalUnits'] else 0
    actions = set(profile['actions'])
    if track == 'A2':
        build_ratio = profile['buildUnits'] / profile['relatedUnits'] if profile['relatedUnits'] else 0
        hours = x['record'].get('hours')
        compact = 1 / (1 + max(0, hours) / 10) if hours is not None else 0
        confidence = 1 if x['rows'] else .25
        fit = confidence * (.55 * focus + .15 * build_ratio) + .3 * compact
    elif track == 'A3':
        # 여러 번 따라 만드는 과정과 설계·측정·문제 해결을 구별한다.
        lifecycle = len(actions & {'verify', 'improve', 'operate'}) / 3
        practice = min(profile['practiceUnits'], 6) / 6
        depth = min(profile['depthUnits'], 4) / 4 * (.5 + .5 * len(profile['depthActions']) / 3)
        # 난이도 표시는 보조 근거다. 확인된 심화 단원이 둘 이상일 때만 가산한다.
        difficulty = str(x['record'].get('difficulty') or '').upper()
        level = {'INTERMEDIATE': .8, 'ADVANCED': 1}.get(difficulty, 0)
        level_bonus = .25 * level * depth if x['rows'] and profile['depthUnits'] >= 2 else 0
        confidence = 1 if x['rows'] else .25
        fit = confidence * (.1 * lifecycle + .1 * practice + .55 * depth) + level_bonus
    else:
        fit = 0
    return {**profile, 'fit': round(fit, 6), 'focus': round(focus, 6),
            'basis': 'outline' if x['rows'] else 'introduction'}


def select(records: dict[str, dict], skills: list[str], texts: list[str], track: str,
           required: list[str] | None = None, hints: list[str] | None = None) -> Selection:
    if track not in ('A1', 'A2', 'A3'):
        raise ValueError('알 수 없는 로드맵 관점입니다.')
    skills = list(dict.fromkeys(skills))[:track_policy.FAST_SKILLS if track == 'A2' else MAX_SKILLS]
    index, terms = cached_index(records), query_terms(texts)
    topics = depth_terms(texts)
    required = list(dict.fromkeys(k for k in required or [] if k))
    excluded = [k for k in required if k in records and track == 'A1' and records[k].get('cost') != 0]
    required = [k for k in required if k not in excluded]
    if any(k not in records or not records[k].get('usable') for k in required):
        raise ValueError('선택한 자료가 삭제되었거나 추천 불가 상태입니다. 자료를 다시 선택해 주세요.')
    if len(required) > MAX_COUNT:
        raise ValueError('선택한 자료가 40개를 넘습니다. 자료 수를 줄여 주세요.')
    hints = set(hints or [])
    scored = []
    assessments = {}
    for key, x in index.items():
        r = x['record']
        if not r.get('usable') or r.get('type') == 'cert' or not x['skills'].intersection(skills):
            continue
        if track == 'A1' and r.get('cost') != 0:
            continue
        learning_outline = x['outline'] if track == 'A1' else x['own_outline']
        relevance = 3 * matches(r['title'].casefold(), terms) + 2 * min(5, matches(learning_outline, terms)) + min(3, matches(x['description'], terms))
        # 태그만 같은 자료로 수를 채우지 않는다. 제목·학습 본문 근거가 있어야 후보가 된다.
        if relevance == 0:
            continue
        assessment = track_fit(x, terms, track, topics)
        # 표시 난이도와 관계없이 충분한 목차에서 심화 근거가 부족한 과정을 후순위로 둔다.
        shallow_outline = (track == 'A3' and bool(x['rows'])
                           and assessment['totalUnits'] >= 6 and assessment['depthUnits'] < 2)
        depth_factor = .8 if shallow_outline else 1
        score = relevance * (1 + assessment['fit']) * depth_factor
        assessments[key] = dict(assessment, relevance=relevance, score=round(score, 6),
                                shallowOutline=shallow_outline)
        # 단과 집중 과정: 확보된 목차가 충분한데 목표 관련 단원이 1/3 미만이면 Fast에서 제외한다.
        # 짧은 강좌/시간 미확인/목차 미확보라는 이유만으로 제외하지 않으며 Challenge에는 적용하지 않는다.
        if track == 'A2' and r.get('type') == 'course' and x['rows'] and len(x['units']) >= track_policy.FAST_MIN_OUTLINE_UNITS \
                and assessment['relatedUnits'] < assessment['totalUnits'] * track_policy.FAST_MIN_FOCUS:
            continue
        # 관련성과 안별 커리큘럼 적합도를 함께 반영한다. 시간은 Fast의 동점 우선순위다.
        preference = 0.0
        if track == 'A2':
            hours = r.get('hours')
            preference = 1 / (1 + max(0, hours) / 10) if hours is not None else 0
        scored.append(((-score, -relevance, -preference, key not in hints, r['title'], key), x))
    scored.sort(key=lambda pair: pair[0])
    ranks = {x['record']['id']: rank for rank, x in scored}
    groups = {s: [] for s in skills}
    duplicates = {s: set() for s in skills}
    other = []
    for _, x in scored:
        if x['record'].get('type') != 'course':
            if len(other) < 4 and x['dedup'] not in {v['dedup'] for v in other}:
                other.append(x)
            continue
        for s in skills:
            if s in x['skills'] and x['dedup'] not in duplicates[s]:
                groups[s].append(x)
                duplicates[s].add(x['dedup'])
    ordered = [index[k] for k in required]
    seen_ids = set(required)
    seen = {x['dedup'] for x in ordered}
    positions = {s: 0 for s in skills}
    reviewed = {s: 0 for s in skills}
    # 각 스킬을 번갈아 읽어 희소 스킬 후보도 앞쪽에서 전달한다.
    for position in range(PER_SKILL):
        for s in skills:
            while positions[s] < len(groups[s]) and groups[s][positions[s]]['dedup'] in seen:
                positions[s] += 1
            if positions[s] < len(groups[s]):
                x = groups[s][positions[s]]
                positions[s] += 1
                reviewed[s] += 1
                ordered.append(x)
                seen_ids.add(x['record']['id'])
                seen.add(x['dedup'])
    # 보조 자료도 같은 적합도 순위로 넣는다. 소개 한 줄짜리 도서에 앞쪽 고정 슬롯을 주지 않는다.
    for x in other:
        key = x['record']['id']
        if key in seen_ids or x['dedup'] in seen:
            continue
        insertion = next((i for i in range(len(required), len(ordered))
                          if ranks[ordered[i]['record']['id']] > ranks[key]), len(ordered))
        ordered.insert(insertion, x)
        seen_ids.add(key)
        seen.add(x['dedup'])
    return Selection([x['record'] for x in ordered], skills, terms, required,
                     reviewed, excluded, index, track, assessments, topics)


def entry(r: dict, selection: Selection) -> dict:
    x = selection.index[r['id']]
    def evidence_order(row):
        own = x['own_rows'].get(row[0], '')
        hits = matches(own.casefold(), selection.terms)
        actions = {name for name, rx in _actions.items() if rx.search(own)}
        fit = (len(actions & {'verify', 'improve', 'operate'}) + bool('build' in actions)) if selection.track == 'A3' else bool('build' in actions)
        if selection.track == 'A3' and not _intro_lesson.search(own) and matches(own.casefold(), selection.topics):
            fit += 2 * sum(bool(rx.search(own)) for rx in _depth_actions.values())
        return (-(hits * (1 + min(fit, 2) / 2)), -hits, row[0])

    rows = sorted([row for row in x['rows'] if matches(x['own_rows'].get(row[0], '').casefold(), selection.terms)], key=evidence_order) \
        if selection.track != 'A1' else sorted(x['rows'], key=lambda row: (-matches(row[2], selection.terms), row[0]))
    excerpts = [(number, excerpt(text, selection.terms, 50)) for number, text, folded in rows if matches(folded, selection.terms)][:2]
    content = ''
    if not excerpts and x['lines']:
        content = excerpt(max(x['lines'], key=lambda line: matches(line.casefold(), selection.terms)), selection.terms, 100)
    outline = r.get('curriculum') or {}
    result = {'id': r['id'], 'title': r['title'][:100],
              'hours': round(float(r['hours']), 2) if r.get('hours') is not None else None, 'cost': r.get('cost'),
              'skills': [f'S{i + 1}' for i, s in enumerate(selection.skills) if s in x['skills']],
              'curriculum': [[number, text] for number, text in sorted(excerpts)]}
    if content:
        result['content'] = content
    if not content and not excerpts:
        result['evidenceStatus'] = 'unavailable'
    if r.get('kind') != '강좌':
        result['kind'] = r.get('kind')
    if r.get('timeStatus') != 'confirmed':
        result['timeStatus'] = r.get('timeStatus') or 'unknown'
    if outline.get('coverage') != 'public_outline':
        result['curriculumCoverage'] = outline.get('coverage') or 'description_only'
    if r.get('difficulty'):
        result['difficulty'] = r['difficulty']
    if r.get('format') and 'format' not in (r.get('estimated') or []):
        result['format'] = r['format']
    if r.get('durationKind'):
        result['durationKind'] = r['durationKind']
    if r.get('timeStatus') == 'estimated':
        result['timeNote'] = str(r.get('timeNote') or '계획용 추정 시간')[:80]
    return result

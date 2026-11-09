"""명시적 필수 기술을 Crash 핵심에서 누락하지 않게 한다. 자유 문장 전체의 의미 판정은 아니다."""
from __future__ import annotations

from bisect import bisect_right
import re
import unicodedata
from app.english_patterns import english_token
from app.services.technology_mentions import applied_technologies, technology_pattern

# 한글 표기와 영문 표기를 같은 요구로 읽는다. 모르는 영문 기술명도 명시적 의무 구문에서 받는다.
ALIASES = {
    'django': ('장고', 'django 프레임워크'), 'fastapi': ('패스트API', '패스트 API'),
    'python': ('파이썬', 'python3', 'python3.10', 'python3.11', 'python3.12', 'python3.13'),
    'java': ('자바', 'java8', 'java11', 'java17', 'java21'), 'javascript': ('자바스크립트',),
    'vue': ('vue.js', 'vuejs', 'vue2', 'vue3'),
    'typescript': ('타입스크립트',), 'docker': ('도커',),
    'kubernetes': ('쿠버네티스', 'k8s'), 'postgresql': ('포스트그레스큐엘', 'postgres'),
    'react': ('리액트',), 'spring': ('스프링',), 'flask': ('플라스크',),
    'redis': ('레디스',), 'linux': ('리눅스',),
    'spring boot': ('스프링 부트', '스프링부트', 'springboot'),
    'sql server': ('microsoft sql server', 'mssql', 'SQL 서버'),
    'github actions': ('깃허브 액션',),
    'django rest framework': ('drf',),
    'oracle db': ('oracle', '오라클'), 'node.js': ('nodejs',),
}
_alias_names = {alias.casefold(): name for name, aliases in ALIASES.items() for alias in (name, *aliases)}
_particle = r'(?:으로만|로만|으로|로|을|를|은|는|이|가|만|도)?'
_known = '|'.join(english_token(re.escape(alias)) if alias.isascii() else
                  re.escape(alias) + rf'(?=$|[^가-힣]|(?:{_particle}|와|과|이나|나)(?=$|[^가-힣]))'
                  for alias in sorted(_alias_names, key=len, reverse=True))
_name = rf'(?:(?:{_known})(?![.-][a-z0-9_+#])|CI/CD|[a-z][a-z0-9_+#]*(?:[.-][a-z0-9_+#]+)*)'
_version = r'(?:[ \t]++v?[0-9]++(?:\.(?:[0-9]++|x))*+(?![a-z0-9_])(?:[ \t]++이상)?)?'
_term = re.compile(rf'(?<![a-z0-9_가-힣])(?P<name>{_name}){_version}', re.I)
# 구분자 뒤에서는 'Django와FastAPI'처럼 띄어쓰기 없이 이어진 다음 기술도 받는다.
_joined_term = re.compile(rf'(?<![a-z0-9_])(?P<name>{_name}){_version}', re.I)
_join =re.compile(r'\s*+(?:(?P<alternative>또는|이나|나|\bor\b)|,|/|·|및|와|과|\band\b|&)\s*+', re.I)
_marker = (
    r'(?:(?:사용|활용|도입|적용|구현|개발|학습)\s*+(?:은|는|이|가)?\s*+)?'
    r'(?:필수|반드시|꼭|해야|must\s+be\s+used|(?:is\s+)?required|(?:is\s+)?mandatory)')
_suffix = re.compile(
    rf'\s*+{_particle}\s*+(?:(?:framework|database|db|프레임워크|데이터베이스)(?![a-z0-9_])\s*+{_particle}\s*+)?{_marker}', re.I)
# 'Django REST API 필수'는 Django의 요구다. 'User API 필수'의 user는 기술이 아니므로 아는 기술에만 넓힌다.
_known_suffix = re.compile(
    rf'\s*+{_particle}\s*+(?:(?:rest(?:ful)?|api|서버|앱|프로젝트)(?![a-z0-9_])\s*+)++{_particle}\s*+{_marker}', re.I)
_prefix = re.compile(
    r'(?:반드시|꼭|필수\s*+(?:기술|스택|도구)?\s*+[:：]|must\s+(?:use|include)|required\s+(?:stack|technologies)\s*:)\s*+', re.I)
_not_required = re.compile(
    rf'\s*+{_particle}\s*+(?:(?:(?:기술|도구|스택|요구사항|조건)\s*+)?(?:(?:은|는|이|가)\s*+)?(?:아니|아님|아닙|없|않|not\b)'
    r'|(?:쓸|사용할|활용할)\s*+필요\s*+(?:는|가)?\s*+없'
    r'|필요한\s*+(?:건|것은|게|것이)?\s*+아니)', re.I)
_negated_action = re.compile(r'\s*+(?:(?:사용|활용|구현)\s*+)?(?:하지\s*않|쓰지|안\s*)')
_non_core = re.compile(r'후속|나중|추후|선택\s*(?:사항|적)|제외|미사용|없이|대신|사용하지|필요\s*없|쓰지|안\s*(?:함|하|해|쓰|사용)|않|아니|아닌|아닙|아님|\b(?:later|optional|without|instead|not|exclude\w*)\b', re.I)
# 의무를 취소하는 표현은 대상 기술에 걸린 것만 본다. "오류 없이 처리"는 품질 조건이고 "Django 없이"가 제외다.
_excluded_next = re.compile(rf'\s*+{_particle}\s*+(?:대신|없이|말고|빼고|제외|미사용|아닌)', re.I)
_deferred_next = re.compile(rf'\s*+{_particle}\s*+(?:후속|나중|추후|\blater\b)', re.I)
_cancelled_scope = re.compile(
    r'후속|나중|추후|선택\s*(?:사항|적)|\(\s*선택\s*\)|(?:사용|도입|적용|구현|활용)\s*하지\s*않|쓰지|필요\s*없|'
    r'(?<![가-힣])안\s*(?:함|하|해|쓰|사용)|\b(?:later|optional)\b', re.I)
# 의무 표현 뒤에서 끝맺는 부정이다. "Django는 필수까지는 아닙니다". "않도록·않은"은 다른 대상의 조건이다.
_denied = re.compile(r'아니|아닌|아님|아닙|않(?:음|습|아|는다|다)|어렵(?:습|다)|없(?:습|어요|다)')
_clauses = re.compile(r'[\n;!?]|\.(?:\s|$)|(?:한\s*뒤|한\s*후|구현\s*후|그리고|하지만)|(?<=하고)\s+|(?<=하며)\s+|(?<=이며)\s+|(?<=이고)\s+|(?<=이지만)\s+|(?<=아니고)\s+|(?<=아니라)\s+')
_stop = {'a', 'an', 'the', 'must', 'use', 'using', 'used', 'include', 'required', 'mandatory',
         'is', 'be', 'not', 'and', 'or', 'of', 'api', 'key', 'db', 'framework', 'x', 'rest', 'restful',
         'login', 'logout', 'token', 'tokens', 'auth', 'authentication', 'authorization', 'password',
         'code', 'review', 'test', 'tests', 'testing', 'documentation', 'docs', 'english', 'korean'}
_stop_only = re.compile(r'[\s을를은는이가의]*+')
_excluded_before = re.compile(r'\b(?:instead\s+of|without)\s++(?:using\s++)?', re.I)
_python_version = re.compile(r'python3(?:\.(?:[0-9]++|x))*+', re.I)
_alias_pairs = []
for _canonical, _aliases in ALIASES.items():
    _variants = '|'.join(re.escape(alias) for alias in sorted((_canonical, *_aliases), key=len, reverse=True))
    _alias_pairs.append((_canonical, re.compile(
        rf'(?<![a-z0-9_가-힣])(?:{_variants})\s*\(\s*(?:{_variants})\s*\)', re.I)))
MAX_REQUIREMENT_CHARS = 65_536


class RequirementTextTooLong(ValueError):
    pass


class MissingCoreRequirements(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = tuple(missing)
        super().__init__('Crash 핵심 기준에 필수 기술이 빠졌어요: ' + ', '.join(missing)
                         + '. 후속 학습이나 비교만으로 미루지 않고 핵심 구현에 포함해 다시 생성해 주세요. 기존 계획은 유지됩니다.')


def _raw_texts(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _raw_texts(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _raw_texts(item)


def _texts(value: object, *, limit: int | None = None):
    for raw in _raw_texts(value):
        if limit is not None:
            limit -= len(raw)
            if limit < 0:
                raise RequirementTextTooLong(f'Crash 목표와 수정 요청의 요구사항을 합계 {MAX_REQUIREMENT_CHARS:,}자 이내로 줄여 주세요.')
        text = unicodedata.normalize('NFKC', raw).replace('`', '')
        # Django(장고)처럼 동일 기술의 별칭을 괄호로 쓴 경우만 합친다. 선택/제외 설명은 보존한다.
        for name, pattern in _alias_pairs:
            text = pattern.sub(name, text)
        yield text


def _technology_name(raw: str) -> str:
    name = raw.casefold()
    return 'python' if _python_version.fullmatch(name) else _alias_names.get(name, name)


def _is_technology(raw: str) -> bool:
    return raw.casefold() not in _stop and not _non_core.fullmatch(raw)


def _read_list(clause: str, first: re.Match) -> tuple[list[frozenset[str]], int]:
    """기술과 구분자를 한 방향으로 소비한다. 뒤에 '필수'가 없어도 목록을 다시 탐색하지 않는다."""
    groups = [{_technology_name(first['name'])}]
    match = first
    while True:
        end = match.end()
        sep = _join.match(clause, end)
        match = _joined_term.match(clause, sep.end()) if sep else None
        if match is None or not _is_technology(match['name']):
            return [frozenset(group) for group in groups], end
        name = _technology_name(match['name'])
        if sep['alternative']:
            groups[-1].add(name)
        else:
            groups.append({name})


def _lists(clause: str):
    pos = 0
    while first := _term.search(clause, pos):
        if not _is_technology(first['name']):
            pos = first.end()
            continue
        groups, pos = _read_list(clause, first)
        yield first.start(), pos, groups


def _prefixed(clause: str, markers: list[int], previous_end: int, start: int) -> bool:
    """접두 표현과 기술 사이에 일반 낱말만 있으면 그 기술에 걸린다. '반드시 REST API를 Django로'."""
    index = bisect_right(markers, start) - 1
    if index < 0 or markers[index] < previous_end:
        return False
    between = _term.sub('', clause[markers[index]:start])
    return _stop_only.fullmatch(between) is not None


def _marked_lists(clause: str):
    lists = list(_lists(clause))
    markers = [marker.end() for marker in _prefix.finditer(clause)]
    previous_end = 0
    for index, (start, end, groups) in enumerate(lists):
        marker = _suffix.match(clause, end)
        if marker is None and all(name in ALIASES for name in groups[-1]):
            marker = _known_suffix.match(clause, end)
        prefixed = marker is None and _prefixed(clause, markers, previous_end, start)
        previous_end = end
        if marker is None and not prefixed:
            continue
        # 다음 기술의 선택·제외는 앞 기술을 취소하지 않는다. 각 꼬리는 한 번만 읽는다.
        scope_end = lists[index + 1][0] if index + 1 < len(lists) else len(clause)
        tail = clause[marker.end() if marker else end:scope_end]
        if (_not_required.match(tail) or _negated_action.match(tail) or _deferred_next.match(tail)
                or _denied.search(tail.split(',', 1)[0])):
            continue
        # 뒤에 붙으면 이미 말한 의무다. "Django 사용 필수, 오류 없이 처리"의 뒤 조건은 의무를 취소하지 않는다.
        if marker is not None or not (_excluded_next.match(tail) or _cancelled_scope.search(
                _excluded_before.sub('', tail.split(',', 1)[0]))):
            yield from groups


def _requirement_groups(handoff: dict, request: object = None) -> set[frozenset[str]]:
    """사용자 목표·현재 프로젝트 범위·직접 수정 요청만 읽는다. 프로필/모델의 추천은 요구가 아니다."""
    details = handoff.get('details')
    if 'userNotes' in handoff and isinstance(details, dict):
        details = {key: value for key, value in details.items() if key != 'etc'}
    sources = [handoff.get(key) for key in ('goal', 'projectSummary', 'desiredCompetencies', 'userNotes')]
    sources.append(details)
    # 수정 요청의 사용자 자유문만 읽는다. removeActs 등의 기술명을 요구로 부활시키지 않는다.
    sources.append({key: request.get(key) for key in ('wish', 'quick')} if isinstance(request, dict) else request)
    found = set()
    for text in _texts(sources, limit=MAX_REQUIREMENT_CHARS):
        for clause in _clauses.split(text):
            found.update(_marked_lists(clause))
    return found


def required_technologies(handoff: dict, request: object = None) -> set[str]:
    """기존 집합 API는 대안의 후보까지 반환한다. 의무 그룹은 안내·검증에서 보존한다."""
    return {name for group in _requirement_groups(handoff, request) for name in group}


def _group_label(group: frozenset[str]) -> str:
    names = sorted(group)
    return names[0] if len(names) == 1 else '(' + ' 또는 '.join(names) + ' 중 하나)'


def validate_core_requirements(rows: list[dict], handoff: dict, request: object = None, *,
                               previous_handoff: dict | None = None) -> None:
    """새 의무 그룹마다 긍정적 핵심 기술이 필요하다. 이전 그룹은 직접 재요구한 경우에만 검사한다."""
    groups = _requirement_groups(handoff, request)
    if previous_handoff is not None:
        # 저장된 의무의 기존 불일치는 유지하되 직접 수정 요청의 명시적 재요구는 검사한다.
        groups = (groups - _requirement_groups(previous_handoff)) | _requirement_groups({}, request)
    if not groups:
        return
    names = {name for group in groups for name in group}
    patterns = {name: technology_pattern(name, ALIASES.get(name, ())) for name in names}
    texts = (text for row in rows for key in ('coreOutcome', 'coreCriteria') for text in _raw_texts(row.get(key)))
    covered = applied_technologies(texts, patterns)
    missing = sorted(_group_label(group) for group in groups if not group & covered)
    if missing:
        raise MissingCoreRequirements(missing)


def prompt_requirements(handoff: dict, request: object = None) -> str:
    try:
        groups = _requirement_groups(handoff, request)
    except RequirementTextTooLong as error:
        from app.errors import ApiError
        raise ApiError(422, 'CRASH_REQUIREMENTS_TOO_LONG', str(error)) from error
    if not groups:
        return ''
    return ('\n[사용자가 명시한 필수 기술]\n' + ', '.join(sorted(_group_label(group) for group in groups))
            + '\n각 항목은 모두 충족한다. 괄호의 대안은 그중 하나 이상을 충족하면 된다. '
            '단독 기술과 대안 그룹에서 선택한 기술은 관련 스킬의 coreOutcome 또는 coreCriteria에 실제 사용하는 핵심으로 남긴다. '
            'application·followUpScope나 비교만으로 대신하지 않는다. 선택적 비교·후속 확장은 별도로 유지한다.\n')

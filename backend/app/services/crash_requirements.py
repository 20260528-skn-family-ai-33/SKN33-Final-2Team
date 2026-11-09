"""명시적 필수 기술을 Crash 핵심에서 누락하지 않게 한다. 자유 문장 전체의 의미 판정은 아니다."""
from __future__ import annotations

import re
import unicodedata
from app.english_patterns import english_token

# 한글 표기와 영문 표기를 같은 요구로 읽는다. 모르는 영문 기술명도 명시적 의무 구문에서 받는다.
ALIASES = {
    'django': ('장고',), 'fastapi': ('패스트API', '패스트 API'),
    'python': ('파이썬',), 'java': ('자바',), 'javascript': ('자바스크립트',),
    'typescript': ('타입스크립트',), 'docker': ('도커',),
    'kubernetes': ('쿠버네티스', 'k8s'), 'postgresql': ('포스트그레스큐엘', 'postgres'),
    'react': ('리액트',), 'spring': ('스프링',), 'flask': ('플라스크',),
    'redis': ('레디스',), 'linux': ('리눅스',),
    'spring boot': ('스프링 부트', 'springboot'),
    'sql server': ('microsoft sql server', 'mssql', 'SQL 서버'),
    'github actions': ('깃허브 액션',),
}
_alias_names = {alias.casefold(): name for name, aliases in ALIASES.items() for alias in (name, *aliases)}
_known = '|'.join(english_token(re.escape(alias)) if alias.isascii() else re.escape(alias)
                  for alias in sorted(_alias_names, key=len, reverse=True))
_name = rf'(?:(?:{_known})(?![.-][a-z0-9_+#])|CI/CD|[a-z][a-z0-9_+#]*(?:[.-][a-z0-9_+#]+)*)'
_particle = r'(?:으로|로|을|를|은|는|이|가|만|도)?'
_version = r'(?:[ \t]++v?[0-9]++(?:\.[0-9]++)*+(?![a-z0-9_]))?'
_term = re.compile(rf'(?<![a-z0-9_])(?P<name>{_name}){_version}', re.I)
_join = re.compile(r'\s*+(?:,|/|·|및|와|과|\band\b|&)\s*+', re.I)
_suffix = re.compile(
    rf'\s*+{_particle}\s*+'
    r'(?:(?:사용|활용|도입|적용|구현|개발|학습)\s*+(?:은|는|이|가)?\s*+)?'
    r'(?:필수|반드시|꼭|해야|must\s+be\s+used|(?:is\s+)?required|(?:is\s+)?mandatory)', re.I)
_prefix = re.compile(
    r'(?:반드시|꼭|필수\s*+(?:기술|스택|도구)?\s*+[:：]|must\s+(?:use|include)|required\s+(?:stack|technologies)\s*:)\s*+', re.I)
_not_required = re.compile(r'\s*+(?:(?:기술|도구|스택|요구사항)\s*+)?(?:(?:은|는|이|가)\s*+)?(?:아니|아님|아닙|없|않|not\b)', re.I)
_negated_action = re.compile(r'\s*+(?:(?:사용|활용|구현)\s*+)?(?:하지\s*않|쓰지|안\s*)')
_non_core = re.compile(r'후속|나중|추후|선택\s*(?:사항|적)|제외|미사용|없이|대신|사용하지|필요\s*없|쓰지|안\s*(?:함|하|해|쓰|사용)|않|아니|아닌|아닙|아님|\b(?:later|optional|without|instead|not|exclude\w*)\b', re.I)
_prefix_boundary = re.compile(rf',|{_non_core.pattern}', re.I)
_compare = re.compile(r'비교|검토|\bcompar\w*\b', re.I)
_practice = re.compile(r'구현|구축|개발|사용|활용|적용|실행|연동|배포|\b(?:implement\w*|build\w*|us(?:e|ing)|deploy\w*)\b', re.I)
_clauses = re.compile(r'[\n;!?]|\.(?:\s|$)|(?:한\s*뒤|한\s*후|구현\s*후|그리고|하지만)|(?<=하고)\s+|(?<=하며)\s+|(?<=아니고)\s+|(?<=아니라)\s+')
_stop = {'a', 'an', 'the', 'must', 'use', 'include', 'required', 'mandatory', 'is', 'not', 'and', 'or'}
_excluded_after = re.compile(rf'{_particle}\s*+(?:대신(?:에)?|없이|말고|제외하고|아닌)')
_excluded_before = re.compile(r'\b(?:instead\s+of|without)\s++(?:using\s++)?', re.I)
MAX_REQUIREMENT_CHARS = 65_536


class RequirementTextTooLong(ValueError):
    pass


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
        for name, aliases in ALIASES.items():
            for alias in aliases:
                text = re.sub(re.escape(name) + r'\s*\(\s*' + re.escape(alias) + r'\s*\)', name, text, flags=re.I)
        yield text


def _read_list(clause: str, first: re.Match) -> tuple[list[str], int]:
    """기술과 구분자를 한 방향으로 소비한다. 뒤에 '필수'가 없어도 목록을 다시 탐색하지 않는다."""
    terms = []
    match = first
    while True:
        terms.append(match['name'].casefold())
        end = match.end()
        sep = _join.match(clause, end)
        match = _term.match(clause, sep.end()) if sep else None
        if match is None or match['name'].casefold() in _stop or _non_core.fullmatch(match['name']):
            return terms, end


def _lists(clause: str):
    pos = 0
    while first := _term.search(clause, pos):
        terms, pos = _read_list(clause, first)
        yield first.start(), pos, terms


def _marked_lists(clause: str):
    for _, end, terms in _lists(clause):
        if marker := _suffix.match(clause, end):
            yield terms, marker.end()
    # 여러 접두 표현이 한 절에 있어도 같은 꼬리를 매번 끝까지 검색하지 않는다.
    boundary_at, excluded = -1, False
    for marker in _prefix.finditer(clause):
        if first := _term.match(clause, marker.end()):
            terms, end = _read_list(clause, first)
            if end > boundary_at:
                boundary = _prefix_boundary.search(clause, end)
                boundary_at = boundary.start() if boundary else len(clause)
                excluded = bool(boundary and boundary[0] != ',')
            if not excluded:
                yield terms, end


def required_technologies(handoff: dict, request: object = None) -> set[str]:
    """사용자 목표·현재 프로젝트 범위·직접 수정 요청만 읽는다. 프로필/모델의 추천은 요구가 아니다."""
    sources = [handoff.get(key) for key in ('goal', 'projectSummary', 'desiredCompetencies', 'details', 'userNotes')]
    # 수정 요청의 사용자 자유문만 읽는다. removeActs 등의 기술명을 요구로 부활시키지 않는다.
    sources.append({key: request.get(key) for key in ('wish', 'quick')} if isinstance(request, dict) else request)
    found = set()
    for text in _texts(sources, limit=MAX_REQUIREMENT_CHARS):
        for clause in _clauses.split(text):
            for terms, end in _marked_lists(clause):
                if _not_required.match(clause, end) or _negated_action.match(clause, end):
                    continue
                found.update(_alias_names.get(term, term) for term in terms if term not in _stop)
    return found


def _pattern(name: str) -> re.Pattern:
    variants = [name, *ALIASES.get(name, ())]
    return re.compile('|'.join(english_token(re.escape(v)) if v.isascii() else re.escape(v) + r'(?=$|[^가-힣]|(?:으로|로|을|를|은|는|이|가|와|과)(?=$|[^가-힣]))' for v in variants), re.I)


def _asserted_clauses(clause: str):
    # “A 대신 B”에서는 쉼표로 이어진 A 목록까지 지운다. “B instead of A”에서는 앞부분이 남는다.
    # “나중에 A 대신 B”와 같은 문장의 나머지 한정어는 그대로 검사한다.
    parts = []
    pos = 0
    for start, end, _ in _lists(clause):
        if marker := _excluded_after.match(clause, end):
            parts.append(clause[pos:start])
            pos = marker.end()
    clause = ' '.join([*parts, clause[pos:]])
    parts, pos = [], 0
    for marker in _excluded_before.finditer(clause):
        if marker.start() >= pos and (first := _term.match(clause, marker.end())):
            parts.append(clause[pos:marker.start()])
            _, pos = _read_list(clause, first)
    yield from ' '.join([*parts, clause[pos:]]).split(',')


def _positive_mention(pattern: re.Pattern, clause: str) -> bool:
    if _non_core.search(clause):
        return False
    for match in pattern.finditer(clause):
        tail = clause[match.end():]
        # 비교 대상 뒤에 다른 기술의 구현이 있어도 해당 기술을 구현한 것으로 보지 않는다.
        compare, practice = _compare.search(tail), _practice.search(tail)
        if compare and (not practice or compare.start() < practice.start()):
            continue
        return True
    return False


def validate_core_requirements(rows: list[dict], handoff: dict, request: object = None) -> None:
    """필수 기술은 적어도 한 스킬의 긍정적인 핵심 기준에 있어야 한다. 입력/결과를 고쳐 통과시키지 않는다."""
    missing = []
    required = required_technologies(handoff, request)
    if not required:
        return
    core_clauses = [clause for row in rows for key in ('coreOutcome', 'coreCriteria')
                    for text in _texts(row.get(key)) for part in _clauses.split(text) for clause in _asserted_clauses(part)]
    for name in sorted(required):
        pattern = _pattern(name)
        covered = any(_positive_mention(pattern, clause) for clause in core_clauses)
        if not covered:
            missing.append(name)
    if missing:
        raise ValueError('Crash 핵심 기준에 필수 기술이 빠졌어요: ' + ', '.join(missing)
                         + '. 후속 학습이나 비교만으로 미루지 않고 핵심 구현에 포함해 다시 생성해 주세요. 기존 계획은 유지됩니다.')


def prompt_requirements(handoff: dict, request: object = None) -> str:
    try:
        names = sorted(required_technologies(handoff, request))
    except RequirementTextTooLong as error:
        from app.errors import ApiError
        raise ApiError(422, 'CRASH_REQUIREMENTS_TOO_LONG', str(error)) from error
    if not names:
        return ''
    return ('\n[사용자가 명시한 필수 기술]\n' + ', '.join(names)
            + '\n각 기술은 관련 스킬의 coreOutcome 또는 coreCriteria에 실제 사용하는 핵심으로 남긴다. '
            'application·followUpScope나 비교만으로 대신하지 않는다. 선택적 비교·후속 확장은 별도로 유지한다.\n')

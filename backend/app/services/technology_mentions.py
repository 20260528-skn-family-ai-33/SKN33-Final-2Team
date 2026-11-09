"""기술별 실제 적용 근거를 읽는다. 필수 요구 추출과 별칭 관리는 호출자의 책임이다.

각 결과·기준은 독립적으로 판정한다. 기술 목록은 근거를 공유하지만 비교·참고·제외
대상은 다른 기술의 구현 근거를 빌리지 않는다. 자유 문장 전체의 의미 평가는 아니다.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from heapq import merge
import re
import unicodedata


__all__ = ['technology_pattern', 'applied_technologies']

# 조사는 기술명에 포함하지 않는다. 한글과 영문 모두 같은 양쪽 경계를 적용한다.
_PARTICLES = (
    r'(?:으로만|으로도|으로는|으로서|으로써|만으로|로만|로도|로는|에서는|에서도|'
    r'으로|에서|에게|부터|까지|을|를|은|는|이|가|와|과|의|에|로|만|도)'
)
_VERSION = r'[ \t]+v?[0-9]+(?:\.[0-9]+)*(?:\.x)?(?!\w)'
_SUBJECT = re.compile(rf'(?:{_VERSION})?[ \t]*(?:{_PARTICLES})?[ \t]*', re.I)
_JOIN = re.compile(
    rf'(?:{_VERSION})?[ \t]*(?:(?:으로|로|을|를|은|는|이|가|만|도)[ \t]*)?'
    r'(?:,|/|·|및|와|과|&|\+|\band\b)[ \t]*', re.I,
)
_BRACKETS = re.compile(r'[()\[\]{}]')
_CLAUSES = re.compile(
    r'[\n;!?。]+|\.(?=\s|$)|(?<=하고)\s+|(?<=하며)\s+|(?<=않고)\s+|'
    r'(?<=아니고)\s+|(?<=아니라)\s+|(?<=말고)\s+|'
    r'(?<=\s)(?:후|뒤)\s+|(?<=구현)후(?=\s|$)|'
    r'(?<!\w)(?:그리고|하지만|반면에?|and\s+then|but|then)(?!\w)', re.I,
)
_DEFERRED = re.compile(
    r'후속|나중|추후|선택\s*사항|(?<!\w)(?:later|optional)(?!\w)', re.I,
)
_OPTIONAL_PREDICATE = re.compile(r'\b(?:is|are)\s+optional\s*[.!]?$', re.I)
_EXCLUDED_BEFORE = re.compile(
    r'\b(?:instead\s+of|without)\s+(?:using\s+)?$|'
    r'\b(?:exclude|excluding|except|compare|comparing|reference)\s+(?:with\s+)?$|'
    r'\b(?:do\s+not|never|not)\s+(?:use|implement|build|deploy)\s+$', re.I,
)
_EXCLUDED_AFTER = re.compile(
    r'(?:대신(?:에)?|없이|말고|제외|미사용|미구현|미적용|아닌|후속|나중|추후|'
    r'선택\s*사항|선택만|(?:필수|필요)[^,;.!?]*?(?:아니|아님|아닙|없)|'
    r'(?:(?:is|are)\s+)?(?:not|never)\b)', re.I,
)
_PREFIX_ACTION = re.compile(
    r'\b(?:implement\w*|build\w*|develop\w*|us(?:e|ing)|deploy\w*|'
    r'integrat\w*|run|running|configur\w*|test\w*|validat\w*)'
    r'\s+(?:(?:a|an|the)\s+)?$', re.I,
)
_KOREAN_ACTION = (
    r'(?:구현|구축|개발|사용(?!자)|활용|적용|실행|연동|배포|실습|구성|설정|'
    r'작성|완성|생성|저장|조회|처리|만들)'
)
_NEGATED_ACTION = (
    rf'(?<![가-힣])(?:{_KOREAN_ACTION}\s*(?:하지\s*않|되지\s*않|안\s*함|'
    r'안\s*하|할\s*필요(?:가|는)?\s*없)|쓰지\s*않|'
    rf'안\s+{_KOREAN_ACTION}|미(?:사용|구현|적용))|'
    r'\b(?:not|never)\s+(?:us\w*|implement\w*|build\w*|deploy\w*)'
)
# 고정된 어휘를 한 번 순회한다. 남은 문장 전체에 .*를 적용하는 패턴을 두지 않는다.
_CUES = re.compile(
    rf'(?P<negative>{_NEGATED_ACTION})|'
    r'(?P<deferred>후속|나중|추후|선택\s*사항|\b(?:later|optional)\b)|'
    r'(?P<reference>소개|개요|이론|문서|영상|시청|참고|검토|'
    r'(?<![가-힣])선택(?!적)|\b(?:overview|introduct\w*|theory|docs?|'
    r'documentation|reference\w*|watch\w*|select\w*|choos\w*)\b)|'
    r'(?P<compare>비교|\b(?:compar\w*|versus|vs)\b)|'
    r'(?P<verification_object>응답|결과|출력|상태\s*코드|기대값|'
    r'\b(?:responses?|results?|outputs?|status\s+codes?|expected)\b)|'
    r'(?P<verify>검증|테스트|확인|점검|측정|'
    r'\b(?:test\w*|validat\w*|verif\w*|check\w*|assert\w*)\b)|'
    rf'(?P<action>(?<![가-힣]){_KOREAN_ACTION}|'
    r'\b(?:implement\w*|build\w*|develop\w*|us(?:e|ing|ed)|deploy\w*|'
    r'integrat\w*|run|running|configur\w*|creat\w*)\b)|'
    r'(?P<artifact>앱|애플리케이션|어플리케이션|서비스|서버|웹사이트|파이프라인|'
    r'데이터베이스|컨테이너|캐시|쿼리|프로젝트|'
    r'\b(?:rest(?:ful)?\s+api|api|apps?|applications?|services?|servers?|'
    r'websites?|pipelines?|databases?|containers?|queries|projects?)\b)', re.I,
)


def technology_pattern(name: str, aliases: tuple[str, ...] = ()) -> re.Pattern[str]:
    """호출자가 제공한 이름·별칭을 리터럴로 읽는 대소문자 무관 패턴을 만든다.

    반환 패턴은 기술명만 소비하고 조사는 보존한다. 예를 들어 장고는 냉장고에,
    Java는 JavaScript에 일치하지 않는다. 빈 이름·별칭만 있으면 ValueError다.
    """
    variants = {unicodedata.normalize('NFKC', value).strip() for value in (name, *aliases)}
    variants.discard('')
    if not variants:
        raise ValueError('기술 이름이나 별칭이 필요합니다.')
    body = '|'.join(re.escape(value) for value in sorted(variants, key=lambda v: (-len(v), v)))
    return re.compile(
        rf'(?<!\w)(?:{body})(?![.\-+#][a-z0-9_])(?=$|[^\w]|{_PARTICLES}(?!\w))', re.I,
    )


def _scopes(text: str) -> Iterator[str]:
    """괄호 안은 독립 판정하고 바깥 문장은 이어 둔다. 중첩도 한 방향으로 소비한다."""
    frames: list[list[str]] = [[]]
    pos = 0
    for match in _BRACKETS.finditer(text):
        frames[-1].append(text[pos:match.start()])
        if match[0] in '([{':
            frames[-1].append(' ')
            frames.append([])
        elif len(frames) > 1:
            yield ''.join(frames.pop())
            frames[-1].append(' ')
        else:
            frames[-1].append(' ')
        pos = match.end()
    frames[-1].append(text[pos:])
    while frames:
        yield ''.join(frames.pop())


@dataclass
class _TechnologyGroup:
    start: int
    end: int
    names: set[str]


def _matches(name: str, pattern: re.Pattern[str], text: str) -> Iterator[tuple[int, int, str]]:
    for match in pattern.finditer(text):
        if match.end() > match.start():
            yield match.start(), match.end(), name


def _groups(text: str, patterns: dict[str, re.Pattern[str]]) -> list[_TechnologyGroup]:
    # 각 패턴의 정렬된 결과를 병합한다. N=문자 수, K=패턴 수일 때 O(KN + M log K).
    mentions = merge(*(_matches(name, pattern, text) for name, pattern in patterns.items()),
                     key=lambda item: (item[0], -item[1]))
    groups: list[_TechnologyGroup] = []
    for start, end, name in mentions:
        if groups and (start <= groups[-1].end or _JOIN.fullmatch(text[groups[-1].end:start])):
            groups[-1].end = max(groups[-1].end, end)
            groups[-1].names.add(name)
        else:
            groups.append(_TechnologyGroup(start, end, {name}))
    return groups


def _has_evidence(tail: str, *, prefix_action: bool) -> bool:
    action, artifact, verification_object = prefix_action, False, False
    blocked, comparison = False, False
    for cue in _CUES.finditer(tail):
        kind = cue.lastgroup
        if kind in ('negative', 'deferred'):
            return False
        if kind == 'reference':
            action = artifact = verification_object = False
            blocked = True
        elif kind == 'compare':
            action = artifact = False
            blocked = comparison = True
        elif kind == 'verification_object':
            verification_object = True
        elif kind == 'verify':
            # 권한 경계·JWT 등의 검증은 응답/결과라는 명사가 없어도 실제 근거다.
            # 기술 비교나 문서 확인은 검증으로 승격하지 않는다.
            if not blocked or (comparison and verification_object):
                action, blocked, comparison = True, False, False
        elif kind == 'action':
            if not comparison:
                action, blocked = True, False
        elif kind == 'artifact' and not blocked:
            artifact = True
    return (action or artifact) and not blocked


def _applied_in_clause(clause: str, patterns: dict[str, re.Pattern[str]]) -> set[str]:
    groups = _groups(clause, patterns)
    if not groups:
        return set()
    if _DEFERRED.search(clause[:groups[0].start].rsplit(',', 1)[-1]):
        return set()
    # 문장 전체를 optional로 한정하는 영어 술어는 제외 대상만 수식하지 않는다.
    if ',' not in clause and _OPTIONAL_PREDICATE.search(clause):
        return set()
    found: set[str] = set()
    for index, group in enumerate(groups):
        previous_end = groups[index - 1].end if index else 0
        next_start = groups[index + 1].start if index + 1 < len(groups) else len(clause)
        before, after = clause[previous_end:group.start], clause[group.end:next_start]
        # 호출자가 Django 패턴만 넘겨도 "Django 구현, Redis는 후속 학습"은
        # 서로 다른 서술이다. 기술 목록의 쉼표는 _groups에서 이미 소비했다.
        before, after = before.rsplit(',', 1)[-1], after.split(',', 1)[0]
        if _EXCLUDED_BEFORE.search(before):
            continue
        subject = _SUBJECT.match(after)
        tail = after[subject.end():]
        if _EXCLUDED_AFTER.match(tail):
            continue
        # "Use B instead of A"의 instead of는 A만 제외한다.
        if exclusion := _EXCLUDED_BEFORE.search(tail):
            tail = tail[:exclusion.start()]
        if _has_evidence(tail, prefix_action=bool(_PREFIX_ACTION.search(before))):
            found.update(group.names)
    return found


def applied_technologies(texts: Iterable[str], patterns: dict[str, re.Pattern[str]]) -> set[str]:
    """독립적인 결과·criteria 문자열에서 실제 적용된 기술의 패턴 키를 반환한다.

    구현·실행·검증 근거 또는 실제 산출물 명사구가 필요하다. 기술명만 있는 문자열과
    별도 문자열의 '구현'을 합치지 않는다. 입력과 패턴을 변경하지 않는다. 기술별
    언급 사이의 구간은 상수 횟수만 읽고, 글자 수를 이유로 정상 출력을 거절하지 않는다.
    """
    found: set[str] = set()
    if not patterns:
        return found
    if isinstance(texts, str):
        texts = [texts]
    for raw in texts:
        text = unicodedata.normalize('NFKC', raw).replace('`', '')
        for scope in _scopes(text):
            for clause in _CLAUSES.split(scope):
                found.update(_applied_in_clause(clause, patterns))
    return found

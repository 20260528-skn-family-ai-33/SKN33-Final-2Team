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
    r'(?:이라는|이라고|라는|라고|으로만|으로도|으로는|으로서|으로써|만으로|로만|로도|로는|에서는|에서도|'
    r'으로|에서|에게|부터|까지|을|를|은|는|이|가|와|과|의|에|로|만|도)'
)
_VERSION = r'[ \t]+v?[0-9]+(?:\.[0-9]+)*(?:\.x)?(?!\w)'
# 조사 뒤에 글자가 이어지면 조사가 아니다. "Django 도입"의 도, "Docker 이미지"의 이.
_SUBJECT = re.compile(rf'(?:{_VERSION})?[ \t]*(?:{_PARTICLES}(?!\w))?[ \t]*', re.I)
_JOIN = re.compile(
    rf'(?:{_VERSION})?[ \t]*(?:(?:으로|로|을|를|은|는|이|가|만|도)[ \t]*)?'
    rf'(?:,|/|·|및|와|과|&|\+|\band\b)[ \t]*|(?:{_VERSION})?[ \t]+', re.I,
)
_BRACKETS = re.compile(r'[()\[\]{}]')
_CLAUSES = re.compile(
    r'[\n;!?。]+|\.(?=\s|$)|(?<=하고)\s+|(?<=하며)\s+|(?<=하되)\s+|(?<=않고)\s+|'
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
    r'\b(?:migrat\w*|mov\w*|switch\w*)\s+(?:away\s+)?from\s+$|'
    r'\b(?:do\s+not|never|not)\s+(?:use|implement|build|deploy|adopt|include)\s+$', re.I,
)
# 기술 바로 뒤 서술어는 그 기술을 말한다. "Django는 도입하지 않음"과 달리
# "Django는 권한 없는 요청을 허용하지 않음"의 부정은 요청을 말하므로 첫 낱말만 본다.
_EXCLUDED_AFTER = re.compile(
    r'(?:대신(?:에)?|(?:(?:구현|개발|사용|활용|적용)[ \t]*)?없이|말고|빼고|뺀|제거|대체|제외|'
    r'미사용|미구현|미적용|미도입|미채택|미포함|금지|불가|불필요|아닌|후속|나중|추후|'
    r'[가-힣]+지[ \t]*않(?!는|은|도록|게)|(?:안|못)[ \t]|없(?:음|다|습니다|어요)|'
    r'범위\s*(?:밖|외)|선택\s*사항|선택만|(?:필수|필요)[^,;.!?]*?(?:아니|아님|아닙|없)|'
    r'(?:(?:is|are)\s+)?(?:not|never)\b)', re.I,
)
# "Django에서 FastAPI로 전환"의 Django는 벗어나는 대상이다. 호출자가 뒤 기술의 패턴을 넘기지 않아도 같다.
_MIGRATED_FROM = re.compile(
    r'[ \t]*(?:에서|로부터)[ \t]+[^,]*?(?:으로|로)[ \t]*(?:전환|마이그레이션|이관|이전|교체|대체)', re.I,
)
_KOREAN_ACTION = (
    r'(?:구현|구축|개발|사용(?!자)|활용|적용|실행|연동|배포|실습|구성|설정|'
    r'작성|완성|생성|저장|조회|처리|만들)'
)
# 적용 동사는 어미와 무관하게 부정이다. "Django를 도입하지 않는 FastAPI 구현".
# 세부 동작은 끝맺을 때만 본다. "Django로 저장하지 않는 조회 API 구현"은 Django를 쓴다.
_APPLY_ACTION = r'(?:구현|구축|개발|사용(?!자)|활용|적용|실습|도입|채택)'
_NEGATED_ACTION = (
    rf'(?<![가-힣])(?:{_APPLY_ACTION}\s*(?:하지\s*않|되지\s*않|안\s*함|'
    rf'안\s*하|할\s*필요(?:가|는)?\s*없)|'
    rf'{_KOREAN_ACTION}\s*(?:(?:하지|되지)\s*않(?:음|습|는다|아|다)|안\s*함)|쓰지\s*않|'
    rf'안\s+{_KOREAN_ACTION}|안\s*(?:씀|쓴|쓰|씁)|'
    r'미(?:사용|구현|적용|도입|채택|포함)(?=\s*(?:$|[,.;])))|'
    r'\b(?:not|never)\s+(?:be\s+)?(?:us\w*|implement\w*|build\w*|built|deploy\w*|adopt\w*|includ\w*)'
)
# "Django 구현은 제외"처럼 기술의 적용 자체를 범위에서 빼는 술어만 본다.
# "저장은 제외하고 조회 API 구현", "권한 없는 사용자는 제외한 API"는 구현 범위 설명이므로 막지 않는다.
_SCOPED_OUT = (
    r'(?<![가-힣])(?:구현|구축|개발|사용(?!자)|활용|적용|실습|서버|서비스|프로젝트|앱|API)(?:은|는|을|를)[ \t]*'
    r'(?:제외(?!한)|다음\s*단계|미룸|미룬|미루|연기|보류|하지\s*않|안\s*함|안\s*하|못\s*함|못\s*하)|'
    rf'(?<![가-힣]){_APPLY_ACTION}\s*(?:금지|불가|불필요|계획\s*(?:이|은)?\s*없)|'
    r'필요\s*(?:는|가)?\s*없(?:음|다|습니다|어요)|다루지\s*않|범위\s*(?:밖|외)|'
    r'\b(?:out\s+of\s+scope|deferred|postponed|excluded)\b'
)
_WEAK_REFERENCE = (
    r'소개|개요|이론|문서|영상|자료|검토|'
    r'\b(?:overview|introduct\w*+|theory|docs?|documentation)\b'
)
_VERIFY = r'검증|테스트|확인|점검|측정'
# 고정된 어휘를 한 번 순회한다. 남은 문장 전체에 .*를 적용하는 패턴을 두지 않는다.
_CUES = re.compile(
    rf'(?P<negative>{_NEGATED_ACTION}|{_SCOPED_OUT})|'
    r'(?P<deferred>후속|나중|추후|선택\s*사항|\b(?:later|optional)\b)|'
    r'(?P<reference>시청|참고|수강|열람|언급|(?<![가-힣])선택(?!적)|'
    r'후보\s*(?:기술|스택|도구|목록|군)|후보로|(?:기술|스택|도구)\s*(?:후보|대안)|대안\s*(?:기술|스택|도구)|(?:후보|대안)\s*$|'
    r'\b(?:reference\w*|mention\w*|watch\w*|select\w*|choos\w*)\b)|'
    rf'(?P<weak>{_WEAK_REFERENCE})|'
    r'(?P<compare>비교|\b(?:compar\w*|versus|vs)\b)|'
    r'(?P<coordination>(?<![가-힣])및(?![가-힣])|\band\b)|'
    r'(?P<verification_object>응답|결과|출력|상태\s*코드|기대값|'
    r'\b(?:responses?|results?|outputs?|status\s+codes?|expected)\b)|'
    rf'(?P<verify>{_VERIFY}|'
    r'\b(?:test\w*|validat\w*|verif\w*|check\w*|assert\w*)\b)|'
    rf'(?P<finished>(?<![가-힣])(?:{_KOREAN_ACTION}(?:한|된|과|와)|만든)(?=\s))|'
    rf'(?P<action>(?<![가-힣]){_KOREAN_ACTION}|'
    r'\b(?:implement\w*|build\w*|develop\w*|us(?:e|ing|ed)|deploy\w*|'
    r'integrat\w*|run|running|configur\w*|creat\w*)\b)|'
    r'(?P<artifact>앱|애플리케이션|어플리케이션|서비스|서버|웹사이트|파이프라인|'
    r'데이터베이스|컨테이너|캐시|쿼리|프로젝트|'
    r'\b(?:rest(?:ful)?\s+api|api|apps?|applications?|services?|servers?|'
    r'websites?|pipelines?|databases?|containers?|queries|projects?)\b)', re.I,
)
# 문장 끝이 이 어휘뿐이면 약한 참고어가 핵심 명사다. "Django 소개 영상 확인"은 구현이 아니다.
_REFERENCE_TAIL = re.compile(
    rf'[^\w]*+(?:{_WEAK_REFERENCE}|{_VERIFY}|\b(?:test\w*+|check\w*+|verif\w*+)\b)++(?:{_PARTICLES}|하기|함)?[^\w]*+', re.I,
)
# "Use Django instead of FastAPI and Flask", "Flask, FastAPI를 제외하고"는 목록의 다른 기술까지 제외한다.
_EXCLUDED_LIST = re.compile(r'제외|대신|없이|말고|빼고|아닌|\b(?:instead\s+of|without|except|excluding)\b', re.I)
# 기술 이름을 부연할 뿐 무엇을 한다는 내용이 없는 낱말이다.
_FILLER = re.compile(
    rf'(?:프레임워크|라이브러리|기술|스택|도구|언어|버전|기반|필수|'
    rf'frameworks?|librar(?:y|ies)|technolog(?:y|ies)|stacks?|tools?|languages?|versions?|required)'
    rf'(?:{_PARTICLES})?', re.I,
)
_WORD = re.compile(r'[^\W\d_]{2,}[\w.+#-]*')
_HANGUL = re.compile(r'[가-힣]')
_LATIN_WORD = re.compile(r'[A-Za-z][\w.+#-]*')
_GENERIC_WORDS = {'rest', 'restful', 'api', 'apis', 'crud', 'http', 'https', 'jwt', 'oauth', 'web', 'json', 'ui', 'db'}


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


def _scopes(text: str) -> Iterator[tuple[str, str]]:
    """(범위 글, 괄호 바로 앞 글)을 낸다. 괄호 안은 독립 판정하고 바깥 문장은 이어 둔다.

    중첩도 한 방향으로 소비한다.
    """
    frames: list[list[str]] = [[]]
    leads = ['']
    pos = 0
    for match in _BRACKETS.finditer(text):
        fragment = text[pos:match.start()]
        frames[-1].append(fragment)
        if match[0] in '([{':
            frames[-1].append(' ')
            frames.append([])
            leads.append(fragment)
        elif len(frames) > 1:
            yield ''.join(frames.pop()), leads.pop()
            frames[-1].append(' ')
        else:
            frames[-1].append(' ')
        pos = match.end()
    frames[-1].append(text[pos:])
    while frames:
        yield ''.join(frames.pop()), leads.pop()


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


def _content_start(tail: str) -> int | None:
    """부연어를 뺀 첫 내용어의 위치다. 낱말을 한 번만 읽는다."""
    for word in _WORD.finditer(tail):
        if not _FILLER.fullmatch(word[0]):
            return word.start()
    return None


def _reference_tail_start(tail: str) -> int:
    """문장 끝에 이어진 약한 참고어·확인어의 시작 위치다. 뒤에서부터 낱말을 한 번만 읽는다."""
    start = len(tail)
    for word in reversed(list(re.finditer(r'\S+', tail))):
        if not _REFERENCE_TAIL.fullmatch(word[0]):
            break
        start = word.start()
    return start


def _has_evidence(tail: str, *, context: bool) -> bool:
    """제외·후속·참고·비교로만 쓰인 언급을 거른다. 내용이 있는 나머지 표현은 적용으로 본다.

    동사 목록으로 적용을 확인하지 않는다. 저장을 막는 검사라서 빌드·분석·학습처럼 목록 밖의
    정상 구현을 거부하는 쪽이 애매한 문장을 통과시키는 쪽보다 비용이 크다.
    """
    content = _content_start(tail)
    reference_tail = _reference_tail_start(tail)
    action, artifact, verification_object = context, False, False
    blocked, comparison, finished = False, False, False
    for cue in _CUES.finditer(tail):
        kind = cue.lastgroup
        if kind in ('negative', 'deferred'):
            return False
        if kind == 'coordination':
            # "Django API 구현 및 Swagger 문서"는 뒤 항목이 앞 구현을 지우지 않는다.
            if not blocked and (action or artifact or (content is not None and content < cue.start())):
                return True
        elif kind == 'reference':
            action = artifact = verification_object = False
            blocked = True
        elif kind == 'weak':
            # "Django 영상 업로드 서버"의 영상은 구현 대상이고 "Django 구현 개요"의 개요는 결과가 구현이 아니다.
            if cue.start() >= reference_tail and not finished:
                action = artifact = False
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
        elif kind in ('action', 'finished'):
            if not comparison:
                action, blocked = True, False
                finished = finished or kind == 'finished'
        elif kind == 'artifact' and not blocked:
            artifact = True
    return not blocked and (action or artifact or content is not None)


def _before_evidence(before: str) -> bool:
    """기술 앞의 구현 표현을 읽는다. "REST API를 구현하는 Django", "구현 기술: Django"."""
    if _EXCLUDED_LIST.search(before):
        return False
    found = False
    for cue in _CUES.finditer(before):
        kind = cue.lastgroup
        if kind in ('negative', 'deferred', 'reference', 'compare'):
            return False
        found = found or kind in ('action', 'finished', 'artifact', 'verify')
    return found


def _lead_applies(lead: str) -> bool:
    """괄호는 바로 앞 절의 구현을 이어받는다. "REST API 구현 (Django)".

    문장이 끝났거나("구현. 후보 기술 목록 (Django)") 앞 절이 다른 도구를 말하면
    ("FastAPI로 구현 (Django)") 이어받지 않는다.
    """
    clause = _CLAUSES.split(lead)[-1].rsplit(',', 1)[-1]
    if _HANGUL.search(clause) and any(
            word.casefold() not in _GENERIC_WORDS for word in _LATIN_WORD.findall(clause)):
        return False
    return _before_evidence(clause)


def _applied_in_clause(clause: str, patterns: dict[str, re.Pattern[str]], *, context: bool = False) -> set[str]:
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
        before = before.rsplit(',', 1)[-1]
        after, _, listed = after.partition(',')
        if _EXCLUDED_BEFORE.search(before) or _MIGRATED_FROM.match(after):
            continue
        subject = _SUBJECT.match(after)
        tail = after[subject.end():]
        if _EXCLUDED_AFTER.match(tail):
            continue
        if listed and not tail.strip():
            # "Django, Celery로 구현"은 패턴에 없는 기술과의 나열이다. 다음 항목의 서술을 함께 읽는다.
            tail = listed.split(',', 1)[0]
            if _EXCLUDED_LIST.search(tail):
                continue
        # "Use B instead of A"의 instead of는 A만 제외한다.
        if exclusion := _EXCLUDED_BEFORE.search(tail):
            tail = tail[:exclusion.start()]
        if _has_evidence(tail, context=context or _before_evidence(before)):
            found.update(group.names)
    return found


def applied_technologies(texts: Iterable[str], patterns: dict[str, re.Pattern[str]]) -> set[str]:
    """독립적인 결과·criteria 문자열에서 실제 적용된 기술의 패턴 키를 반환한다.

    제외·후속·참고·비교로만 쓰인 언급과 기술명만 있는 문자열은 적용으로 보지 않는다.
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
        for scope, lead in _scopes(text):
            context = bool(lead) and _lead_applies(lead)
            for clause in _CLAUSES.split(scope):
                found.update(_applied_in_clause(clause, patterns, context=context))
    return found

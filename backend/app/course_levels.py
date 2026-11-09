"""강좌 원본 난이도를 우선하고, 미기재 과정은 실제 제목·단원으로 분류한다."""
import re
import unicodedata

LOW, MID, UPPER_MID, HIGH = 'BEGINNER', 'INTERMEDIATE', 'UPPER_INTERMEDIATE', 'ADVANCED'
_intro = re.compile(r'입문|초급|초보|기초|처음|개론|beginner|introduct|fundamental|basics?', re.I)
_advanced = re.compile(r'고급|심화|advanced', re.I)
_middle = re.compile(r'중급|intermediate', re.I)
_depth = re.compile(r'트러블슈팅|성능\s*(?:튜닝|최적화|분석)|장애\s*(?:분석|복구)|부하\s*테스트|분산\s*(?:트랜잭션|합의)|benchmark|troubleshoot|performance tuning', re.I)


def classify(raw: str | None, title: str | None, curriculum: dict | None) -> tuple[str, str]:
    if raw in (HIGH, UPPER_MID, MID, LOW):
        return raw, '원본'
    title = unicodedata.normalize('NFKC', title or '')
    intro, advanced = bool(_intro.search(title)), bool(_advanced.search(title))
    if (intro and advanced) or _middle.search(title):
        return MID, '제목의 중급·혼합 수준'
    if advanced:
        return HIGH, '제목의 고급·심화 표기'
    if intro:
        return LOW, '제목의 입문·기초 표기'
    units = {unicodedata.normalize('NFKC', unit.get('title') or '').strip().casefold()
             for unit in (curriculum or {}).get('items') or [] if isinstance(unit, dict) and not unit.get('suspended')}
    if sum(bool(_depth.search(unit)) for unit in units) >= 2:
        return HIGH, '심화 작업을 다루는 단원 2개 이상'
    if units and sum(bool(_intro.search(unit)) for unit in units) >= max(2, len(units)/2):
        return LOW, '입문·기초 단원 중심'
    return MID, '명시적 수준 근거 부족, 계획용 중간값'


def short_course(record: dict) -> bool:
    hours = record.get('hours')
    return isinstance(hours, (int, float)) and not isinstance(hours, bool) and 0 < hours <= 2 and record.get('timeStatus') != 'unknown'


def challenge_band(record: dict) -> int:
    level = record.get('difficulty') or record.get('_courseLevel')
    if level == HIGH:
        return 0
    if level == UPPER_MID:
        return 1
    return 2


def eligible(record: dict, track: str | None) -> bool:
    """관련성 검사와 별개인 코스별 가격·난이도 조건. 난이도는 강좌 단위로 적용한다."""
    if track == 'A1':
        return record.get('cost') == 0 and not isinstance(record.get('cost'), bool)
    if track == 'A2':
        return challenge_band(record) == 2
    if track == 'A3':
        return challenge_band(record) < 2
    return True


def preference(record: dict, track: str) -> int:
    band = challenge_band(record)
    if track == 'A3':
        return band + int(band == 2 and (record.get('difficulty') or record.get('_courseLevel')) == LOW)
    if track == 'A2':
        return int(band < 2)
    return 0

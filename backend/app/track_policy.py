"""DB 프롬프트는 유지하고 Fast 후보 선정·전달 입력에 적용하는 추가 기준."""
from __future__ import annotations

VERSION = '20261111-skill-cap-3-v8'
# 선정 스킬 상한(모든 코스). 이전에 4~5개로 저장된 목록은 사용자 순서의 앞 3개만 쓴다.
MAX_SKILLS = 3
# 이전 상한. 이미 저장된 점검의 남은 퀴즈를 이어 만들 때만 허용한다(기존 문항·응답 보존).
LEGACY_MAX_SKILLS = 5
FAST_SKILLS = 3
FAST_MIN_OUTLINE_UNITS = 6
FAST_MIN_FOCUS = 1 / 3

# 활성 DB 프롬프트의 관점을 후보 선정 조건으로 설명한다. 시스템 프롬프트를 대체하지 않는다.
CANDIDATE_PREFERENCE = {
    'A2': '목표에 필요한 핵심 학습 내용에 집중된 커리큘럼과 최소 기능 구현을 우선 검토한다. 확보된 단원이 6개 이상일 때 목표 관련 단원이 1/3 미만인 일반 강좌는 후보에서 제외한다. 품질·보안 검증은 생략하지 않는다.',
    'A3': '목표 관련 설계·성능 측정·문제 해결이 있는 중급·고급 과정을 우선 검토한다. Beginner도 심화 근거가 있거나 기초 보강에 필요하면 사용할 수 있다. 단순 구현·배포 따라하기는 후순위다. 높은 난이도·긴 시간만으로 선택하지 말고 known·gaps·deepCheck의 학습자 수준과 시간·예산 안에서 최종 편성한다.',
}



CHALLENGE_DEPTH_VERSION = 'challenge-depth/20261101-v1'
CHALLENGE_DEPTH = """
[Challenge 심화 기준]
동일 스킬의 기초 이해·단순 따라하기보다 높은 도달 수준을 목표로 한다.
목표 범위와 학습자 수준 안에서 설계 대안 비교, 성능·품질 측정, 실패 원인 분석, 개선 전후 검증 중 관련 있는 것을 구체화한다.
자료 개수·과제 개수·학습시간·기간만 늘려 도전성을 꾸미지 않는다. 새 스킬이나 프로젝트 밖의 배포·모델 학습을 억지로 추가하지 않는다.
기초 보강이 필요하면 포함하되 최종 산출물은 실행 성공을 넘어 선택 이유와 검증 근거가 남아야 한다.
존재하지 않는 DB 목차나 성능 수치를 지어내지 않고, 적절한 기준선과 측정 방법으로 검증한다.
"""
CHALLENGE_STAGES = {
 'plan': 'learningSkills의 application은 심화 도달 수준이 드러나는 명사형으로 쓴다. 각 항목에 targetOutcome(구체적인 산출물)과 completionCriteria(확인 가능한 완료 기준 2~4개)를 추가한다. 예: SQL은 조인 결과 작성에서 끝내지 않고 쿼리 대안 비교·결과 정합성·실행 계획 검증까지 목표에 맞춰 확장한다. title·tagline·reason에도 실제 심화 범위를 반영하고 근거 없이 고급·전문가라고 꾸미지 않는다.',
 'resources': 'skills와 course.learningSkills의 targetOutcome·completionCriteria를 뒷받침하는 자료를 우선한다. 제목의 고급·실무 단어나 난이도 표지만으로 판단하지 않고 제공된 설명·목차에서 설계·비교·측정·검증의 학습 근거를 확인한다. 입문 자료도 선수 학습에 필요하면 사용할 수 있지만 단순 따라하기 자료만으로 심화 수준을 충족했다고 하지 않는다. 입력 후보 밖의 자료나 비용을 만들어 채우지 않는다.',
 'tasks': 'skillTargets의 targetOutcome·completionCriteria를 이어받는다. 스킬마다 과제 하나 안에 관련 설계 대안 또는 기준선과의 비교, 측정 가능한 결과, 실패·한계 분석 및 개선 근거를 담는다. how의 만들 것·필수 항목·제출물·평가 기준에 수행 내용과 확인할 증거를 구체적으로 쓴다. 단순 수강·요약·코드 실행만으로 완료시키지 않는다. 다시 제안해도 같은 도달 수준과 검증 기준을 유지한다. 선택 자료로 뒷받침할 수 없는 전문성을 보장하지 않는다.',
 'summary': '선택 자료가 실제 뒷받침하는 분석·설계·비교·검증 역량을 명사형으로 요약한다. 계획의 목표 역량을 DB 근거 없이 이미 획득할 수 있는 역량으로 단정하지 않는다.',
}


def challenge_guidance(course,stage):
    course_id=course.get('id') if isinstance(course,dict) else course
    return CHALLENGE_DEPTH+'\n'+CHALLENGE_STAGES[stage] if course_id=='A3' else ''


# Crash는 선정 스킬을 유지하고 학습 범위를 최소 기능판의 핵심 완료 기준으로 좁힌다.
# 계획이 정한 coreOutcome·coreCriteria를 자료 판정·과제 평가 기준·역량 요약이 그대로 공유한다.
CRASH_CORE_VERSION = 'crash-core/20261105-v1'
CRASH_CORE_MARKER = '[Crash 핵심 완료 기준]'
CRASH_CORE = CRASH_CORE_MARKER + """
선정 스킬은 모두 유지하되 각 스킬은 최소 기능판 결과물에 필요한 부분만 다룬다.
coreOutcome은 이 스킬로 최소 기능판에서 만들 결과, coreCriteria는 그 결과의 완료를 확인하는 핵심 기준 1~3개다.
목표 문장에 직접 나온 일과 품질·보안 확인은 핵심 기준에 남긴다. 그 밖의 전체 목표 범위는 followUpScope(후속 학습 0~3개)로 옮긴다.
계획과 과제 완료 판단에 같은 coreOutcome·coreCriteria를 적용한다. 후속 학습 범위는 다음 과제로 남긴다.
"""
CRASH_STAGES = {
 'plan': 'learningSkills 각 항목에 coreOutcome(최소 기능판에서 이 스킬로 만들 결과 문자열), coreCriteria(서로 다른 핵심 완료 기준 문자열 1~3개), followUpScope(이번 Crash에서 빼고 후속 학습으로 넘기는 전체 목표 범위 문자열 0~3개)를 추가한다. 필드 생략·본문 대체 금지. 활동은 핵심 기준 충족에 필요한 자료·실습만 편성하고 scope에는 핵심 결과물과 후속 학습을 한 줄로 쓴다.',
 'resources': '직원 목표와 선정 스킬에 맞는 강좌를 제목과 학습 단원에서 확인한다. 제공된 후보 중 같은 강좌의 시간을 한 번만 합산해 짧은 조합을 우선한다.',
 'tasks': 'skillTargets의 coreOutcome·coreCriteria를 이어받는다. 스킬별 과제의 만들 것은 coreOutcome의 최소 기능판, 평가 기준은 coreCriteria와 대응하는 관찰 가능한 통과 기준으로 쓴다. followUpScope는 필수 항목·평가 기준에 넣지 않는다.',
 'summary': '선택 자료가 뒷받침하는 coreCriteria 범위의 수행 능력으로 요약한다. followUpScope 범위를 획득한 역량으로 쓰지 않는다.',
}


def crash_guidance(course,stage):
    course_id=course.get('id') if isinstance(course,dict) else course
    if course_id != 'A2':
        return ''
    prefix = '' if stage == 'resources' else CRASH_CORE
    return '\n' + prefix + CRASH_STAGES[stage]


def course_guidance(course,stage):
    return challenge_guidance(course,stage)+crash_guidance(course,stage)

PERIOD_GUIDANCE = """
[현재 확정 기간 정책 · 앞의 상충하는 기간 상한 지시보다 우선]
Free·Crash·Challenge 모두 기간 상한을 적용하지 않는다. deadlineWeeks는 참고 값이다.
입력 기간을 넘었다는 이유만으로 자료·스킬을 빼거나, 실제 강좌 시간을 축소하거나, 계획을 실패시키지 않는다.
실제 자료 시간과 주당 시간으로 예상 기간을 계산하고 주당 시간·가격·무료 강좌 조건·프로젝트 포함 범위는 유지한다.
"""

"""DB 프롬프트는 유지하고 Fast 후보 선정·전달 입력에 적용하는 추가 기준."""
from __future__ import annotations

VERSION = '20261103-course-preparation-crash-v6'
FAST_WEEKS = 6
FAST_SKILLS = 3
FAST_MIN_OUTLINE_UNITS = 6
FAST_MIN_FOCUS = 1 / 3

# 활성 DB 프롬프트의 관점을 후보 선정 조건으로 설명한다. 시스템 프롬프트를 대체하지 않는다.
CANDIDATE_PREFERENCE = {
    'A2': '목표에 필요한 핵심 학습 내용에 집중된 커리큘럼과 최소 기능 구현을 우선 검토한다. 확보된 단원이 6개 이상일 때 목표 관련 단원이 1/3 미만인 일반 강좌는 후보에서 제외한다. 품질·보안 검증은 생략하지 않는다.',
    'A3': '목표 관련 설계·성능 측정·문제 해결이 있는 중급·고급 과정을 우선 검토한다. Beginner도 심화 근거가 있거나 기초 보강에 필요하면 사용할 수 있다. 단순 구현·배포 따라하기는 후순위다. 높은 난이도·긴 시간만으로 선택하지 말고 known·gaps·deepCheck의 학습자 수준과 시간·예산 안에서 최종 편성한다.',
}


def fast_weeks(prefs: dict) -> int:
    value = prefs.get('deadlineWeeks')
    return min(FAST_WEEKS, max(1, int(value))) if value is not None else FAST_WEEKS


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

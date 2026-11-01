"""DB 프롬프트는 유지하고 Fast 후보 선정·전달 입력에 적용하는 추가 기준."""
from __future__ import annotations

VERSION = '20261030-db-active-fast-task-tags-v4'
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

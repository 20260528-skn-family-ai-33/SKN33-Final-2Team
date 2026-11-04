"""AI 설명과 선택 자료의 계산값이 서로 다른 총기간·금액을 제시하지 않게 한다."""

MARKER = '[기간·비용 표시 계약 roadmap-display/v1]'
GUIDANCE = MARKER + '''
이 표시 계약은 다른 문구의 '예상 기간 계산' 지시보다 우선한다.
최종 선택 자료가 바뀔 수 있으므로 displayTitle·tagline·reason·pros·cons·scope·summary·notes에
총기간(주/일/개월), 전체 학습시간, 총금액을 직접 계산하거나 확정값처럼 적지 않는다.
해당 설명은 편성 이유·변경 내용·범위·장단점을 정성적으로 적는다. 총기간·대표 금액은 시스템이 선택 자료로 계산해 별도 표시한다.
사용자가 입력한 희망 기간·주당 시간·예산은 입력 조건으로 보존한다. 활동별 hours·catalog 원값·실제 자료명·수행 내용의 숫자를 바꾸지 않는다.
자료 학습 예상 기간은 고유 강좌 ID별 시간을 한 번 합산하고 고유 도서 ID별 1주를 더한 뒤 주당 시간으로 전체 올림한다.
도서 카탈로그 시간은 참고값이며 계획에는 현재 주당 학습시간만큼 1주를 배정한다. 실제 독서시간이 확인되었다고 말하지 않는다.
산출물 과제 시간은 자료 학습 예상 기간에서 제외하며 별도로 표시한다. 희망 기간 상한은 새로 적용하지 않는다.
'''


def with_display_contract(prompt: str) -> str:
    """기존 DB 버전도 동일 계약 사용. JSON 예제는 문서 끝에 유지한다."""
    if MARKER in prompt:
        return prompt
    example = 'JSON 형식 예: '
    if example in prompt:
        before, after = prompt.split(example, 1)
        return before.rstrip() + '\n\n' + GUIDANCE + '\n' + example + after
    return prompt.rstrip() + '\n\n' + GUIDANCE.strip()

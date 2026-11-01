"""월간 프롬프트 개선 실행 시각 계약. 예약 등록·DB 쓰기·모델 호출은 하지 않는다."""
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
MODEL = 'growpath-27b'


def monthly_run_at(year: int, month: int) -> datetime:
    """해당 월 첫 월요일 한국시간 06:00."""
    first = datetime(year, month, 1, 6, tzinfo=KST)
    return first + timedelta(days=(-first.weekday()) % 7)


def next_run_after(value: datetime) -> datetime:
    """주어진 시각보다 뒤의 정기 실행 시각. 장애 후 보충 실행 정책과는 분리한다."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('시간대가 있는 시각이 필요합니다.')
    local = value.astimezone(KST)
    candidate = monthly_run_at(local.year, local.month)
    if candidate > local:
        return candidate
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    return monthly_run_at(year, month)


def run_key(value: datetime) -> str:
    """같은 달의 중복 실행 방지에 사용할 키. 실제 잠금/저장은 실행 담당에서 처리한다."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('시간대가 있는 시각이 필요합니다.')
    return 'prompt-improvement/' + value.astimezone(KST).strftime('%Y-%m')

"""첫 월요일 06시 실행. 같은 업로드 볼륨의 배타 파일과 DB 버전 검사로 중복 적용을 막는다."""
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from uuid import uuid4

from app.services.prompt_improvement_schedule import KST, monthly_run_at, next_run_after, run_key
from app.services.prompt_improvement_runner import run_cycle
from app.services.prompt_evaluation_replay import evaluate_change, load_cases

logger = logging.getLogger(__name__)


def execute_month(scheduled_at: datetime, state_dir: Path, evaluate, *, apply=True, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    if scheduled_at.tzinfo is None or now.tzinfo is None:
        raise ValueError('시간대가 필요합니다.')
    local = scheduled_at.astimezone(KST)
    if local != monthly_run_at(local.year, local.month) or now < scheduled_at:
        raise ValueError('정해진 월간 실행 시각 이후에만 실행합니다.')
    key = run_key(scheduled_at)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / (key.replace('/', '-') + '.json')
    try:
        with path.open('x', encoding='utf-8') as stream:
            json.dump({'period': key, 'status': 'started', 'scheduledAt': scheduled_at.isoformat()}, stream)
    except FileExistsError:
        return {'status': 'already_claimed', 'period': key}
    try:
        result = run_cycle(key, evaluate, apply=apply)
    except Exception as error:
        result = {'status': 'failed', 'errorType': type(error).__name__}
        logger.error('월간 프롬프트 개선 실패: %s (%s)', key, type(error).__name__)
    final = dict(result, period=key, finishedAt=datetime.now(timezone.utc).isoformat())
    temporary = path.with_name(path.name + '.' + str(uuid4()) + '.tmp')
    temporary.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    return final


async def serve(cases_path: str, state_dir: Path, *, apply=True):
    cases = load_cases(cases_path)
    def evaluate(ctx, course, before, after):
        return evaluate_change(ctx, course, before, after, cases)
    target = next_run_after(datetime.now(timezone.utc))
    while True:
        delay = (target - datetime.now(timezone.utc)).total_seconds()
        if delay > 0:
            await asyncio.sleep(min(delay, 60))
            continue
        result = await asyncio.to_thread(execute_month, target, state_dir, evaluate, apply=apply)
        logger.info('월간 프롬프트 개선: %s (%s)', result['status'], result['period'])
        target = next_run_after(datetime.now(timezone.utc))

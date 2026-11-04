"""GrowPath 5차 목업 서버 진입점.

  python -m uvicorn app.main:app --port 8785      (목업_실행.cmd 가 실행)
화면(web/)과 API(/api/v1)를 한 서버에서 낸다. 배포(AWS) 때도 이 앱을 컨테이너로 그대로 띄우고 설정은 환경변수로 넣는다.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from contextlib import suppress
import asyncio
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import catalog, jobs
from .config import ROOT
from .errors import ApiError, api_error_handler
from .routers import account, notifications, team, work, preassessment

WEB = ROOT / 'web'
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    n = jobs.mark_lost()
    if n:
        print(f'  서버가 다시 시작돼 끊긴 작업 {n}개를 실패로 남겼어요(다시 시도는 사용자가 누를 때만)')
    started = time.perf_counter()
    try:
        await run_in_threadpool(catalog.warmup_roadmap)
    except Exception:
        # 사전 준비 실패로 다른 기능까지 막지 않는다. 로드맵 요청은 기존 검사로 다시 확인한다.
        logger.exception('로드맵 사전 로딩 실패: 로드맵 요청 시 다시 확인합니다.')
    else:
        logger.info('로드맵 사전 로딩 완료: %.0fms', (time.perf_counter() - started) * 1000)
    prompt_task = None
    if os.environ.get('PROMPT_IMPROVEMENT_ENABLED', '0') == '1':
        from .services.prompt_evaluation_replay import load_cases
        from .services.prompt_improvement_worker import serve
        cases_path = os.environ.get('PROMPT_IMPROVEMENT_CASES', '')
        load_cases(cases_path)  # 설정이 없거나 잘못됐으면 활성화에 성공한 것처럼 시작하지 않는다.
        state_dir = Path(os.environ.get('PROMPT_IMPROVEMENT_STATE_DIR', str(ROOT / 'var' / 'prompt_improvement')))
        prompt_task = asyncio.create_task(serve(cases_path, state_dir, apply=os.environ.get('PROMPT_IMPROVEMENT_AUTO_APPLY', '1') == '1'))
    try:
        yield
    finally:
        if prompt_task:
            prompt_task.cancel()
            with suppress(asyncio.CancelledError):
                await prompt_task


app = FastAPI(title='GrowPath 5차 목업 API', version='5.0', lifespan=lifespan, docs_url='/api/docs', openapi_url='/api/openapi.json')
app.add_exception_handler(ApiError, api_error_handler)
app.include_router(account.r)
app.include_router(work.r)
app.include_router(team.r)
app.include_router(preassessment.r)
app.include_router(notifications.r)
for error_type in (preassessment.StoreError, preassessment.SelectionError, preassessment.SurveyError, preassessment.RecommendationError):
    app.add_exception_handler(error_type, preassessment.validation_error)
try:
    from .routers import admin
    app.include_router(admin.r)
except ImportError as e:  # 관리자 화면 코드가 없을 때도 나머지는 뜨게
    print(f'  관리자 API 없음: {e}')


@app.exception_handler(Exception)
async def unexpected(_: Request, exc: Exception):
    # 예상 못 한 오류도 성공으로 바꾸지 않고 알린다. 원문은 운영자용으로만
    return JSONResponse({'error': {'code': 'SERVER_ERROR', 'message': '서버에서 문제가 생겼어요', 'hint': '잠시 뒤 다시 시도해 주세요', 'retryable': True,
                                   'kind': 'other', 'cause': '서버 오류', 'raw': f'{type(exc).__name__}: {exc}'[:500]}}, status_code=500)


@app.get('/')
def index():
    return FileResponse(WEB / 'index.html', headers={'Cache-Control': 'no-cache'})


class Assets(StaticFiles):
    """화면 파일은 매번 바뀐 게 있는지 묻게 한다(no-cache + ETag). 고친 화면 코드가 브라우저 캐시 때문에 안 보이는 일을 막는다"""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers['Cache-Control'] = 'no-cache'
        return resp


app.mount('/assets', Assets(directory=WEB / 'assets'), name='assets')

"""GrowPath 5차 목업 서버 진입점.

  python -m uvicorn app.main:app --port 8785      (목업_실행.cmd 가 실행)
화면(web/)과 API(/api/v1)를 한 서버에서 낸다. 배포(AWS) 때도 이 앱을 컨테이너로 그대로 띄우고 설정은 환경변수로 넣는다.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import jobs
from .config import ROOT
from .errors import ApiError, api_error_handler
from .routers import account, team, work

WEB = ROOT / 'web'


@asynccontextmanager
async def lifespan(_: FastAPI):
    n = jobs.mark_lost()
    if n:
        print(f'  서버가 다시 시작돼 끊긴 작업 {n}개를 실패로 남겼어요(다시 시도는 사용자가 누를 때만)')
    yield


app = FastAPI(title='GrowPath 5차 목업 API', version='5.0', lifespan=lifespan, docs_url='/api/docs', openapi_url='/api/openapi.json')
app.add_exception_handler(ApiError, api_error_handler)
app.include_router(account.r)
app.include_router(work.r)
app.include_router(team.r)
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

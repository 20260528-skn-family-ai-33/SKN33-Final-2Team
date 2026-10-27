"""API 라우터 (/api/v1 · 설계서 v1.7 6.1)."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from .. import jobs
from ..errors import ApiError


def wants_async(request: Request) -> bool:
    return 'respond-async' in (request.headers.get('prefer') or '').lower()


def job_response(request: Request, job_id: str | None, employee_id: int, done: dict | None = None, timeout: float = 600):
    """오래 걸리는 작업: 'Prefer: respond-async' 면 202 {jobId}, 아니면 끝날 때까지 기다렸다가 결과(설계서 6.2)"""
    if not job_id:
        return done or {'ok': True}
    if wants_async(request):
        return JSONResponse({'jobId': job_id, 'status': 'running'}, status_code=202)
    v = jobs.wait_result(job_id, employee_id, timeout)
    if v['status'] == 'failed':
        e = v['error'] or {}
        raise ApiError(502, e.get('code', 'AI_ERROR'), e.get('user', '처리하지 못했어요'), e.get('hint', ''), bool(e.get('retryable')), kind=e.get('kind'), cause=e.get('text'), raw=e.get('raw'))
    return v['result'] or {'ok': True}

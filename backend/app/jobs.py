"""오래 걸리는 에이전트 호출을 작업으로 돌린다 (설계서 v1.7 6.2 '오래 걸리는 작업').

- 작업은 app_ext.jobs 에 남는다. 화면을 떠나거나 새로 고쳐도 서버가 이어서 처리하고, 화면은 작업 ID로 결과를 받아 간다.
- 실행은 이 서버 프로세스 안의 스레드 풀(5차 목업 범위). 서버가 다시 켜지면 돌던 작업은 '끊김'으로 실패 처리한다(자동 재시도 없음).
- 결과를 업무 표(작성 중 로드맵 등)에 쓰는 일은 작업 함수 안에서 한다. 작업 표에는 화면에 돌려줄 값만 남긴다.
  나중에 LangGraph 로 옮길 때는 작업 함수 하나가 그래프 하나(또는 노드)에 대응한다.
"""
from __future__ import annotations

import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import db
from .errors import AgentError, ApiError, cause

POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix='gp5-job')
WAIT_MAX_S = 15


class JobCtx:
    def __init__(self, job_id: str):
        self.job_id = job_id

    def progress(self, data: dict) -> None:
        with db.tx() as t:
            t.run("UPDATE app_ext.jobs SET progress = progress || :p, updated_at = now() WHERE job_id = :j AND status = 'running'", p=db.J(data), j=self.job_id)

    def cancelled(self) -> bool:
        return db.val('SELECT status FROM app_ext.jobs WHERE job_id = :j', j=self.job_id) == 'cancelled'


def start(kind: str, employee_id: int | None, ref: str, fn: Callable[[JobCtx], Any], progress: dict | None = None) -> str:
    with db.tx() as t:
        jid = str(t.val("INSERT INTO app_ext.jobs(employee_id, kind, ref, status, progress) VALUES(:e, :k, :r, 'running', :p) RETURNING job_id",
                        e=employee_id, k=kind, r=ref, p=db.J(progress or {})))

    def work() -> None:
        ctx = JobCtx(jid)
        status, result, error = 'done', None, None
        try:
            result = fn(ctx)
        except AgentError as e:
            status, error = 'failed', dict(e.info, stopped=e.stopped)
        except ApiError as e:
            status, error = 'failed', {'kind': 'other', 'code': e.code, 'user': e.message, 'text': e.message, 'hint': e.hint, 'raw': '', 'retryable': e.retryable}
        except Exception as e:  # noqa: BLE001 - 작업 스레드의 예상 못 한 오류도 실패로 남긴다(조용히 삼키지 않음)
            traceback.print_exc()
            status, error = 'failed', cause(f'서버 오류: {e}')
        with db.tx() as t:
            t.run("UPDATE app_ext.jobs SET status = :s, result = :r, error = :e, updated_at = now() WHERE job_id = :j AND status = 'running'",
                  s=status, r=db.J(result), e=db.J(error), j=jid)

    POOL.submit(work)
    return jid


def view(job_id: str, employee_id: int | None, wait: float = 0) -> dict:
    """작업 상태. wait 초 동안 끝나기를 기다린다(최대 15초). 다른 사람의 작업은 보이지 않는다"""
    deadline = time.time() + max(0.0, min(wait, WAIT_MAX_S))
    while True:
        j = db.one('SELECT job_id, employee_id, kind, ref, status, progress, result, error FROM app_ext.jobs WHERE job_id = CAST(:j AS uuid)', j=job_id)
        if not j or (employee_id is not None and j['employee_id'] not in (None, employee_id)):
            raise ApiError(404, 'JOB_NOT_FOUND', '작업을 찾을 수 없어요')
        if j['status'] != 'running' or time.time() >= deadline:
            return {'jobId': str(j['job_id']), 'kind': j['kind'], 'status': j['status'], 'progress': j['progress'],
                    'result': j['result'], 'error': j['error']}
        time.sleep(0.25)


def cancel(job_id: str, employee_id: int | None) -> str:
    with db.tx() as t:
        j = t.one('SELECT employee_id, status FROM app_ext.jobs WHERE job_id = CAST(:j AS uuid) FOR UPDATE', j=job_id)
        if not j or (employee_id is not None and j['employee_id'] not in (None, employee_id)):
            raise ApiError(404, 'JOB_NOT_FOUND', '작업을 찾을 수 없어요')
        if j['status'] == 'running':
            t.run("UPDATE app_ext.jobs SET status = 'cancelled', updated_at = now() WHERE job_id = CAST(:j AS uuid)", j=job_id)
            return 'cancelled'
        return j['status']


def mark_lost() -> int:
    """서버를 다시 켜면 돌던 작업은 끊긴 것으로 남긴다. 다시 시도는 사용자가 누를 때만"""
    err = cause('서버가 다시 시작돼 진행 중이던 작업이 끊겼어요')
    with db.tx() as t:
        return t.run("UPDATE app_ext.jobs SET status = 'failed', error = :e, updated_at = now() WHERE status = 'running'", e=db.J(err))


def lost_cause() -> dict:
    """끊긴 작업(서버를 다시 켜서 작업 표에서 running 이 아님)을 화면에 보여 줄 원인"""
    return cause('서버가 다시 시작돼 진행 중이던 작업이 끊겼어요')


def alive(job_ids: list, t: db.Tx | None = None) -> set[str]:
    """그중 아직 돌고 있는 작업 ID. 업무 표에 '작성 중'으로 남았는데 작업이 끝났으면(서버 재시작) 끊긴 것으로 본다"""
    ids = [str(x) for x in job_ids if x]
    if not ids:
        return set()
    sql = "SELECT job_id FROM app_ext.jobs WHERE job_id = ANY(CAST(:ids AS uuid[])) AND status = 'running'"
    rows = t.all(sql, ids=ids) if t else db.all_(sql, ids=ids)
    return {str(r['job_id']) for r in rows}


def wait_result(job_id: str, employee_id: int | None, timeout: float = 600) -> dict:
    """서버 안에서 작업 결과를 기다린다(동기 응답이 필요한 요청용)"""
    end = time.time() + timeout
    while True:
        v = view(job_id, employee_id, wait=min(WAIT_MAX_S, max(0.0, end - time.time())))
        if v['status'] != 'running' or time.time() >= end:
            return v

"""기존 동기 계약을 유지하면서 UI의 생성 요청은 작업 ID로 즉시 반환한다."""
from functools import wraps
from inspect import signature, Parameter
from fastapi import Request
from fastapi.responses import JSONResponse
from app import jobs
from app.errors import ApiError


def start_shared(employee,reference,work):
    from app import db
    from app.services.generation_lock import generation_guard
    with generation_guard('generation-start',f'{employee}:{reference}'):
        old=db.one("SELECT job_id FROM app_ext.jobs WHERE employee_id=:e AND kind='learning_generation' AND ref=:r AND status='running' ORDER BY updated_at DESC LIMIT 1",e=employee,r=reference)
        if old:return str(old['job_id'])
        return jobs.start('learning_generation',employee,reference,work)


def queued_generation(function=None, *, reference_prefix=''):
    if function is None:return lambda fn:queued_generation(fn,reference_prefix=reference_prefix)
    original = signature(function, eval_str=True)

    @wraps(function)
    def endpoint(*args, **kwargs):
        request = kwargs.pop('generation_request', None)
        if request is None or 'respond-async' not in (request.headers.get('prefer') or '').lower():
            return function(*args, **kwargs)
        values = original.bind(*args, **kwargs).arguments
        account = values['a']
        reference = reference_prefix+str(values.get('project_id', values.get('plan_id', '')))
        def work(_):
            try:
                return function(*args, **kwargs)
            except ValueError as error:
                raise ApiError(422, 'GENERATION_INVALID', str(error)) from error
        from fastapi.encoders import jsonable_encoder
        work._resume = {'operation':'route','module':function.__module__,'function':function.__name__,'kwargs':jsonable_encoder(dict(values))}
        jid = start_shared(account.id,reference,work) if reference_prefix else jobs.start('learning_generation', account.id, reference, work)
        return JSONResponse({'jobId': jid, 'status': 'running'}, status_code=202)

    endpoint.__signature__ = original.replace(parameters=[*original.parameters.values(),
        Parameter('generation_request', Parameter.KEYWORD_ONLY, default=None, annotation=Request)])
    return endpoint

"""기존 동기 계약을 유지하면서 UI의 생성 요청은 작업 ID로 즉시 반환한다."""
from functools import wraps
from inspect import signature, Parameter
from fastapi import Request
from fastapi.responses import JSONResponse
from app import jobs
from app.errors import ApiError


def queued_generation(function):
    original = signature(function, eval_str=True)

    @wraps(function)
    def endpoint(*args, **kwargs):
        request = kwargs.pop('generation_request', None)
        if request is None or 'respond-async' not in (request.headers.get('prefer') or '').lower():
            return function(*args, **kwargs)
        values = original.bind(*args, **kwargs).arguments
        account = values['a']
        reference = str(values.get('project_id', values.get('plan_id', '')))
        def work(_):
            try:
                return function(*args, **kwargs)
            except ValueError as error:
                raise ApiError(422, 'GENERATION_INVALID', str(error)) from error
        jid = jobs.start('learning_generation', account.id, reference, work)
        return JSONResponse({'jobId': jid, 'status': 'running'}, status_code=202)

    endpoint.__signature__ = original.replace(parameters=[*original.parameters.values(),
        Parameter('generation_request', Parameter.KEYWORD_ONLY, default=None, annotation=Request)])
    return endpoint

"""기존 jobs JSON의 복구 설명으로 중단 작업을 재등록. 스키마 변경 없음."""
from app import db,jobs
from contextvars import ContextVar
parent_job=ContextVar("recovery_parent",default=None)
from app.errors import ApiError
from app.services.generation_lock import generation_guard


def invoke(spec,employee):
    from app.services import drafts,plans,goals,post_quiz
    op=spec.get('operation');kw=dict(spec.get('kwargs') or {})
    if op=='route':
        from app.routers import preassessment,work
        from app.auth import Account
        from inspect import signature
        from pydantic import BaseModel
        modules={'app.routers.preassessment':preassessment,'app.routers.work':work}
        module=modules.get(spec.get('module'))
        fn=getattr(module,spec.get('function',''),None) if module else None
        fn=getattr(fn,'__wrapped__',None)
        if fn is None:raise ApiError(409,'RECOVERY_UNAVAILABLE','다시 준비할 요청을 확인하지 못했어요.')
        account=kw.get('a') or {}
        if account.get('id')!=employee:raise ApiError(403,'FORBIDDEN','본인의 작업만 다시 준비할 수 있어요.')
        kw['a']=Account(**account)
        for name,p in signature(fn,eval_str=True).parameters.items():
            if name in kw and isinstance(p.annotation,type) and issubclass(p.annotation,BaseModel):kw[name]=p.annotation.model_validate(kw[name])
        def run(_):return fn(**kw)
        run._resume=spec
        return jobs.start('learning_generation',employee,'recovery:'+spec['function'],run)
    if kw.get('employee_id')!=employee:raise ApiError(403,'FORBIDDEN','본인의 작업만 다시 준비할 수 있어요.')
    if op=='post-quiz':
        row=plans._owned(employee,kw['plan_id'])
        return post_quiz.prepare(employee,kw['plan_id'],row['content'])
    if op=='materials':
        from app.routers import preassessment
        from app.auth import Account
        from app.services.course_recommendations import option_cache_key
        with db.tx() as t:
            w=drafts._row(t,employee,kw['draft_id'],lock=False)['draft_choices']
            option=(((w.get('draft') or {}).get('gen') or {}).get('options') or {}).get(kw['course'])
            if option_cache_key(option)!=spec.get('optionKey'):return None
        def run(_):return preassessment.generate_recommendations(kw['draft_id'],Account('employee',employee,''),course=kw['course'])
        run._resume=spec
        return jobs.start('learning_generation',employee,kw['draft_id']+':'+kw['course'],run)
    allowed={'drafts.doc_summary_start':drafts.doc_summary_start,'drafts.assessment_start':drafts.assessment_start,
        'drafts.diagnosis_start':drafts.diagnosis_start,'drafts.option_retry':drafts.option_retry,'drafts._maybe_support':drafts._maybe_support,
        'drafts.regenerate':drafts.regenerate,'plans.post_deep_start':plans.post_deep_start,'plans.revise_start':plans.revise_start,
        'plans.revision_support':plans.revision_support,'plans.report_start':plans.report_start,'goals.request':goals.request}
    if op not in allowed:raise ApiError(409,'RECOVERY_UNAVAILABLE','다시 준비할 요청을 확인하지 못했어요.')
    if op.startswith('drafts.'):
        with db.tx() as t:
            w=drafts._wrap(drafts._row(t,employee,kw['draft_id'],lock=False)['draft_choices'])
            key=((w.get('draft') or {}).get('genRun') or {}).get('key')
            if spec.get('inputKey') and key!=spec['inputKey']:return None
        drafts._mutate(employee,kw['draft_id'],drafts._heal)
    return allowed[op](**kw)


def resume(job_id,employee):
    jobs.view(job_id,employee)
    with generation_guard('job-recovery',str(job_id)):
        row=db.one('SELECT status,error,progress FROM app_ext.jobs WHERE job_id=CAST(:j AS uuid) AND employee_id=:e',j=str(job_id),e=employee)
        if not row:raise ApiError(404,'NOT_FOUND','작업을 찾을 수 없어요.')
        progress=row.get('progress') or {}
        if progress.get('redirectJobId'):return str(progress['redirectJobId'])
        if row['status']!='failed' or (row.get('error') or {}).get('code')!='JOB_INTERRUPTED' or not progress.get('_resume'):
            raise ApiError(409,'RECOVERY_UNAVAILABLE','자동으로 다시 준비할 작업이 아니에요.')
        token=parent_job.set(str(job_id))
        try:result=invoke(progress['_resume'],employee)
        finally:parent_job.reset(token)
        jid=result if isinstance(result,str) else (result or {}).get('jobId') if isinstance(result,dict) else None
        if not jid and isinstance(result,dict):jid=next(iter((result.get('jobs') or {}).values()),None)
        if jid:
            with db.tx() as t:t.run("UPDATE app_ext.jobs SET progress=coalesce(progress,'{}'::jsonb)||jsonb_build_object('redirectJobId',CAST(:n AS text)) WHERE job_id=CAST(:j AS uuid)",n=str(jid),j=str(job_id))
            return str(jid)
        with db.tx() as t:t.run("UPDATE app_ext.jobs SET status='done',result=:r,updated_at=now() WHERE job_id=CAST(:j AS uuid)",r=db.J(result if isinstance(result,dict) else {}),j=str(job_id))
        return str(job_id)


def resume_pending():
    rows=db.all_("SELECT job_id,employee_id FROM app_ext.jobs WHERE status='failed' AND error->>'code'='JOB_INTERRUPTED' AND progress ? '_resume' AND NOT (progress ? 'redirectJobId') ORDER BY created_at LIMIT 32")
    for row in rows:
        try:resume(str(row['job_id']),row['employee_id'])
        except Exception:
            import logging
            logging.getLogger(__name__).exception('중단 작업 자동 복구 보류')

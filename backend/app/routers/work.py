"""새 로드맵 작성·내 로드맵·점검·보고서·학습 자료·사내 생활 도우미·작업 (API-09, 14~54)."""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from .. import catalog, db, jobs, regstore, skillmap
from ..agents import regulation as REG
from ..agents import runtime as rt
from ..auth import Account, require_account, require_employee
from ..config import S
from ..errors import ApiError, not_found
from ..services import drafts as DR
from ..services import plans as PL
from . import job_response

r = APIRouter(prefix='/api/v1')
MAX_DOC = 15_000_000


# ── 작업 ──
@r.get('/jobs/{job_id}')
def api_job(job_id: str, wait: float = 0, a: Account = Depends(require_account)):
    return jobs.view(job_id, a.id if a.type == 'employee' else None, wait)


@r.post('/jobs/{job_id}/cancel')
def api_job_cancel(job_id: str, a: Account = Depends(require_account)):
    return {'jobId': job_id, 'status': jobs.cancel(job_id, a.id if a.type == 'employee' else None)}


# ── 한 번에 불러오기 (목업 편의 · 로그인 직후·새로 고침) ──
@r.get('/me/workspace')
def api_workspace(a: Account = Depends(require_employee)):
    w = PL.workspace(a.id)
    d = DR.current(a.id)
    w['res'].update(d.pop('res'))
    w['reg']['articles'].update(d['reg']['articles'])
    w['reg']['regs'].update(d['reg']['regs'])
    d.pop('reg')
    return dict(w, draft=d)


# ── 새 로드맵 작성 (API-14~35) ──
@r.get('/drafts/current')
def api_draft_current(a: Account = Depends(require_employee)):
    return DR.current(a.id)


@r.post('/drafts')
def api_draft_create(body: dict, a: Account = Depends(require_employee)):
    return DR.create(a.id, body)


@r.patch('/drafts/{draft_id}')
def api_draft_patch(draft_id: str, body: dict, a: Account = Depends(require_employee)):
    return DR.patch(a.id, draft_id, body)


@r.delete('/drafts/{draft_id}', status_code=204)
def api_draft_delete(draft_id: str, a: Account = Depends(require_employee)):
    DR.discard(a.id, draft_id)


@r.post('/drafts/{draft_id}/changes/apply')
def api_changes_apply(draft_id: str, body: dict, a: Account = Depends(require_employee)):
    return DR.changes_apply(a.id, draft_id, body.get('kind') or 'gen')


@r.post('/drafts/{draft_id}/changes/revert')
def api_changes_revert(draft_id: str, body: dict, a: Account = Depends(require_employee)):
    return DR.changes_revert(a.id, draft_id, body.get('kind') or 'gen')


@r.post('/drafts/{draft_id}/project-file')
async def api_project_file(draft_id: str, request: Request, file: UploadFile = File(...), a: Account = Depends(require_employee)):
    raw = await file.read(MAX_DOC + 1)
    if len(raw) > MAX_DOC:
        raise ApiError(413, 'DOC_TOO_BIG', '파일이 너무 커요(15MB까지)', '15MB 이하로 줄이거나 필요한 부분만 따로 저장해 주세요', kind='docbig', cause='요청이 너무 커요 (기획서 파일은 15MB까지)')
    from starlette.concurrency import run_in_threadpool
    out = await run_in_threadpool(DR.doc_read, a.id, draft_id, file.filename or 'file', raw)
    jid = await run_in_threadpool(DR.doc_summary_start, a.id, draft_id, False)
    return dict(out, jobId=jid)


@r.delete('/drafts/{draft_id}/project-file')
def api_project_clear(draft_id: str, a: Account = Depends(require_employee)):
    return DR.clear_project(a.id, draft_id)


@r.post('/drafts/{draft_id}/project-file/summary')
def api_project_summary(draft_id: str, request: Request, body: dict | None = None, a: Account = Depends(require_employee)):
    jid = DR.doc_summary_start(a.id, draft_id, bool((body or {}).get('skipImages')))
    return job_response(request, jid, a.id)


@r.post('/drafts/{draft_id}/assessment')
def api_assessment(draft_id: str, request: Request, a: Account = Depends(require_employee)):
    jid = DR.assessment_start(a.id, draft_id)
    return job_response(request, jid, a.id, DR.get(a.id, draft_id))


@r.put('/drafts/{draft_id}/assessment/answers')
def api_answers(draft_id: str, body: dict, a: Account = Depends(require_employee)):
    return DR.patch(a.id, draft_id, {'answers': body.get('answers') or {}})


@r.post('/drafts/{draft_id}/diagnosis')
def api_diagnosis(draft_id: str, request: Request, a: Account = Depends(require_employee)):
    jid = DR.diagnosis_start(a.id, draft_id)
    return job_response(request, jid, a.id, DR.get(a.id, draft_id))


@r.put('/drafts/{draft_id}/diagnosis/overrides')
def api_overrides(draft_id: str, body: dict, a: Account = Depends(require_employee)):
    return DR.overrides(a.id, draft_id, body)


@r.post('/drafts/{draft_id}/options')
def api_options_start(draft_id: str, a: Account = Depends(require_employee)):
    out = DR.options_start(a.id, draft_id)
    return JSONResponse(out, status_code=202 if out.get('jobs') else 200)


@r.get('/drafts/{draft_id}/options')
def api_options(draft_id: str, a: Account = Depends(require_employee)):
    return DR.get(a.id, draft_id)


@r.get('/drafts/{draft_id}/options/events')
def api_options_events(draft_id: str, a: Account = Depends(require_employee)):
    """3안 작성·지원 조건 확인 진행 알림(API-28 · SSE). 바뀔 때마다 안별 상태를 보낸다"""
    def state():
        d = DR.get(a.id, draft_id)['draft']
        rows = ((d.get('genRun') or {}).get('rows') or {})
        g = d.get('gen') or {}
        out = {pid: {'status': {'run': 'running', 'ok': 'done', 'fail': 'failed'}.get((rows.get(pid) or {}).get('st'), 'waiting')} for pid in ('A1', 'A2', 'A3')}
        opts = g.get('options') or {}
        sup = 'waiting' if not opts else 'failed' if any(o.get('supportFail') for o in opts.values()) else 'done' if all(o.get('support') for o in opts.values()) else 'running'
        out['regulation'] = {'status': sup}
        return out

    def stream():
        last, end = None, time.time() + 600
        while time.time() < end:
            try:
                s = state()
            except ApiError:
                break
            if s != last:
                yield f"data: {json.dumps(s, ensure_ascii=False)}\n\n"
                last = s
            if all(v['status'] not in ('running',) for k, v in s.items() if k != 'regulation') and s['regulation']['status'] != 'running':
                break
            time.sleep(0.5)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store'})


@r.post('/drafts/{draft_id}/options/accept-partial')
def api_accept_partial(draft_id: str, a: Account = Depends(require_employee)):
    return DR.accept_partial(a.id, draft_id)


@r.post('/drafts/{draft_id}/options/support/retry')
def api_support_retry(draft_id: str, body: dict | None = None, a: Account = Depends(require_employee)):
    return DR.support_retry(a.id, draft_id, (body or {}).get('perspective'))


@r.post('/drafts/{draft_id}/options/{pid}/retry')
def api_option_retry(draft_id: str, pid: str, a: Account = Depends(require_employee)):
    return DR.option_retry(a.id, draft_id, pid)


@r.post('/drafts/{draft_id}/options/{pid}/regenerate')
def api_regenerate(draft_id: str, pid: str, body: dict | None = None, a: Account = Depends(require_employee)):
    return DR.regenerate(a.id, draft_id, pid, (body or {}).get('request'))


@r.post('/drafts/{draft_id}/selection')
def api_selection(draft_id: str, body: dict, a: Account = Depends(require_employee)):
    return DR.select(a.id, draft_id, body.get('perspective'))


@r.post('/drafts/{draft_id}/confirm')
def api_confirm(draft_id: str, a: Account = Depends(require_employee)):
    return DR.confirm(a.id, draft_id)


# ── 내 로드맵 (API-36~47) ──
@r.get('/plans')
def api_plans(status: str = '', detail: int = 0, a: Account = Depends(require_employee)):
    recs = PL.records(a.id, statuses=(status,) if status else None)
    if detail:
        return {'plans': recs, 'res': PL.resources_of(recs), 'reg': PL.reg_of(recs)}
    return [{'planId': k, 'goal': v['plan']['goal'], 'perspective': v['plan']['opt'], 'version': v['plan']['version'], 'status': v['status'],
             'done': sum(1 for x in v['plan']['acts'] if (v['progress'].get(x['id']) or {}).get('status') == 'done'), 'total': len(v['plan']['acts']),
             'newComments': sum(1 for c in v['comments'] if c['status'] == 'new'), 'weeks': v['plan']['weeks'], 'weeklyHours': v['plan']['hours'],
             'doneAt': v['doneAt'], 'archivedAt': v['archivedAt']} for k, v in recs.items()]


def _plan_out(rec: dict) -> dict:
    one = {rec['id']: rec}
    return {'plan': rec, 'res': PL.resources_of(one), 'reg': PL.reg_of(one)}


@r.get('/plans/{plan_id}')
def api_plan(plan_id: str, a: Account = Depends(require_employee)):
    return _plan_out(PL.record(PL._owned(a.id, plan_id)))


@r.put('/plans/{plan_id}/activities/{act_id}/progress')
def api_progress(plan_id: str, act_id: str, body: dict, a: Account = Depends(require_employee)):
    return _plan_out(PL.save_progress(a.id, plan_id, act_id, body))


@r.post('/plans/{plan_id}/activities/{act_id}/attachments')
async def api_attach(plan_id: str, act_id: str, file: UploadFile = File(...), a: Account = Depends(require_employee)):
    """결과물·수료증 첨부(API-39). 5차는 서버 폴더(var/uploads)에 둔다 — 배포 때는 같은 자리를 S3 같은 저장소로 바꾼다.
    활동 기록·사후 점검 저장과 같은 규칙으로 대상을 먼저 확인한다: 본인의 진행 중 로드맵, 그 로드맵의 활동(사후 점검 첨부는 'post')"""
    row = PL._owned(a.id, plan_id)
    if PL.STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵에만 파일을 붙일 수 있어요')
    if act_id != 'post' and not any(x['id'] == act_id for x in row['content']['acts']):
        raise not_found('활동')
    raw = await file.read(MAX_DOC + 1)
    if len(raw) > MAX_DOC:
        raise ApiError(413, 'FILE_TOO_BIG', '파일이 너무 커요(15MB까지)')
    fid = uuid.uuid4().hex
    folder = S.var_dir / 'uploads'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / fid).write_bytes(raw)
    return {'fileId': fid, 'name': file.filename, 'size': len(raw)}


@r.get('/plans/{plan_id}/versions')
def api_versions(plan_id: str, a: Account = Depends(require_employee)):
    rec = PL.record(PL._owned(a.id, plan_id))
    return [{'version': v['version'], 'reason': v.get('why'), 'confirmedAt': v.get('confirmedAt'), 'weeks': v['weeks'], 'weeklyHours': v['hours'], 'cost': v['cost']} for v in rec['versions']]


@r.post('/plans/{plan_id}/archive')
def api_archive(plan_id: str, a: Account = Depends(require_employee)):
    return _plan_out(PL.archive(a.id, plan_id))


@r.post('/plans/{plan_id}/resume')
def api_resume(plan_id: str, a: Account = Depends(require_employee)):
    return _plan_out(PL.resume(a.id, plan_id))


@r.post('/plans/{plan_id}/revisions')
def api_revise(plan_id: str, request: Request, body: dict, a: Account = Depends(require_employee)):
    out = PL.revise_start(a.id, plan_id, body)
    return job_response(request, out['jobId'], a.id, out)


@r.post('/plans/{plan_id}/revisions/support/retry')
def api_rev_support(plan_id: str, request: Request, a: Account = Depends(require_employee)):
    jid = PL.revision_support_retry(a.id, plan_id)
    return job_response(request, jid, a.id)


def _rev_owner(a: Account, revision_id: str) -> str:
    rid = db.val('SELECT roadmap_id FROM app_ext.roadmap_revisions WHERE revision_id = CAST(:i AS uuid)', i=revision_id)
    if not rid:
        raise not_found('수정안')
    PL._owned(a.id, str(rid))
    return str(rid)


@r.post('/revisions/{revision_id}/accept')
def api_rev_accept(revision_id: str, a: Account = Depends(require_employee)):
    rid = _rev_owner(a, revision_id)
    rec = PL.accept_revision(a.id, rid, revision_id)
    return dict(_plan_out(rec), planId=rid, version=rec['plan']['version'])


@r.delete('/revisions/{revision_id}', status_code=204)
def api_rev_drop(revision_id: str, a: Account = Depends(require_employee)):
    rid = _rev_owner(a, revision_id)
    PL.discard_revision(a.id, rid, revision_id)


@r.get('/plans/{plan_id}/comments')
def api_comments(plan_id: str, a: Account = Depends(require_employee)):
    return PL.record(PL._owned(a.id, plan_id))['comments']


@r.post('/plans/{plan_id}/comments/{comment_id}/read')
def api_comment_read(plan_id: str, comment_id: str, a: Account = Depends(require_employee)):
    return _plan_out(PL.read_comment(a.id, plan_id, comment_id))


# ── 점검·보고서 (API-48~52) ──
@r.get('/plans/{plan_id}/assessment')
def api_pre(plan_id: str, a: Account = Depends(require_employee)):
    A = PL.record(PL._owned(a.id, plan_id))['plan']['assess']
    return {'questions': A['questions'], 'answers': A['answers']}


@r.put('/plans/{plan_id}/post-assessment')
def api_post(plan_id: str, body: dict, a: Account = Depends(require_employee)):
    return _plan_out(PL.save_post(a.id, plan_id, body))


# 사후 심화 질문 만들기(설계서 v1.7 밖 추가 · 10/23): 사전에 심화 질문을 고른 로드맵만. 끝나면 로드맵을 다시 읽어 post.deep 을 본다
@r.post('/plans/{plan_id}/post-assessment/deep')
def api_post_deep(plan_id: str, request: Request, a: Account = Depends(require_employee)):
    jid = PL.post_deep_start(a.id, plan_id)
    return job_response(request, jid, a.id)


@r.post('/plans/{plan_id}/reports')
def api_report(plan_id: str, request: Request, a: Account = Depends(require_employee)):
    jid = PL.report_start(a.id, plan_id)
    return job_response(request, jid, a.id)


@r.get('/reports')
def api_reports(planId: str = '', a: Account = Depends(require_employee)):
    return [x for x in PL.reports(a.id) if not planId or x['planId'] == planId]


@r.get('/reports/{report_id}')
def api_report_one(report_id: str, a: Account = Depends(require_employee)):
    x = next((x for x in PL.reports(a.id) if x['id'] == report_id), None)
    if not x:
        raise not_found('결과 보고서')
    return x


@r.post('/reports/{report_id}/confirm')
def api_report_confirm(report_id: str, a: Account = Depends(require_employee)):
    return PL.confirm_report(a.id, report_id)


# ── 학습 자료·자격증 (API-22, 53, 54) ──
@r.get('/certifications')
def api_certs(a: Account = Depends(require_account)):
    return catalog.cert_groups()


@r.get('/resources')
def api_resources(kind: str = '', q: str = '', stage: int = 0, exclude: str = '', limit: int = 30, offset: int = 0, certs: int = 1, a: Account = Depends(require_account)):
    return catalog.search(kind, q, stage, [x for x in exclude.split(',') if x], max(1, min(100, limit)), max(0, offset), bool(certs))


@r.post('/resources/lookup')
def api_resources_lookup(body: dict, a: Account = Depends(require_account)):
    return catalog.resources_for(body.get('ids') or [])


@r.get('/resources/{resource_id}')
def api_resource(resource_id: str, a: Account = Depends(require_account)):
    x = catalog.resources_for([resource_id], detail=True).get(resource_id)
    if not x:
        raise not_found('학습 자료')
    return x


# ── 스킬 지도 (검토·확정 화면 · 설계서 밖 추가 10/23) ──
@r.get('/skills/map')
def api_skill_map(a: Account = Depends(require_account)):
    return skillmap.skill_map()


# ── 사내 생활 도우미 (API-09) ──
@r.post('/assistant/ask')
def api_ask(request: Request, body: dict, a: Account = Depends(require_employee)):
    q = str(body.get('question') or '').strip()
    if not q:
        raise ApiError(400, 'EMPTY_QUESTION', '질문을 적어 주세요')
    hist = body.get('history') or []

    def work(job: jobs.JobCtx):
        ctx = rt.context(a.id)
        brief = [{'goal': x['plan']['goal'], 'name': x['plan']['name'], 'weeklyHours': x['plan']['hours'], 'costWon': x['plan']['cost']}
                 for x in PL.records(a.id, statuses=('active',)).values()]
        dp = DR.current(a.id).get('draftPlan')
        context = REG.reg_context(ctx.me, brief, {'name': dp['name'], 'weeklyHours': dp['hours'], 'costWon': dp['cost']} if dp else None)
        ans = REG.answer(ctx, q, hist, context, sim=rt.sim_once(ctx, 'reg', q))
        ids = list(ans.get('basis') or []) + list(ans.get('ref') or [])
        return {'answer': ans, 'reg': regstore.bundle(ids), 'meta': ctx.meta}
    jid = jobs.start('assistant', a.id, q[:120], work)
    return job_response(request, jid, a.id)


@r.post('/regulations/lookup')
def api_reg_lookup(body: dict, a: Account = Depends(require_account)):
    return regstore.bundle(body.get('ids') or [])


@r.get('/regulations/sets')
def api_reg_sets(a: Account = Depends(require_account)):
    return {g: {'group': s['group'], 'label': s['label'], 'org': s['org'], 'regs': s['regs']} for g, s in regstore.data()['sets'].items()}

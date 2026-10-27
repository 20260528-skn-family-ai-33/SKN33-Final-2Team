"""확정한 로드맵 (설계서 v1.7 API-36~52 · 부서장 API-55~59).

저장: 팀 DB public.roadmaps(지금 버전 content · 처음 버전 baseline_content) + roadmap_steps(활동 · 완료 여부) + roadmap_step_resources(강좌·도서·자격 연결)
      + 보조 스키마 roadmap_meta(버전·상태 시각)·roadmap_versions(버전 이력)·activity_progress(진행·메모·첨부)·roadmap_revisions(수정안)
      + 사후 점검: assessment_questions/responses POST + post_checks · 보고서: growth_reports(+report_meta 확인 여부) · 코멘트: roadmap_comments(+comment_meta)
상태는 projects.status(IN_PROGRESS 진행 중 · COMPLETED 마침 · ARCHIVED 보관). 로드맵마다 기록이 따로이고 개수 제한은 없다.
팀 DB 트리거 규칙: 보고서는 넣은 뒤 고칠 수 없다(다시 만들면 지우고 새로 넣음) · 코멘트는 작성자(부서장) 정보가 있어야 쓰거나 바뀐다
→ 수정안 확정으로 로드맵 내용이 바뀌면 코멘트가 '수정 완료'로 바뀌므로 그 코멘트 작성자 정보를 붙여 저장한다.
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import date

from .. import catalog, db, jobs, regstore
from ..agents import deepcheck as DC
from ..agents import diag as DG
from ..agents import regulation as REG
from ..agents import roadmap as RM
from ..agents import runtime as rt
from ..agents.demo import D
from ..errors import AgentError, ApiError, forbidden, not_found
from . import profile

STATUS = {'IN_PROGRESS': 'active', 'COMPLETED': 'done', 'ARCHIVED': 'archived'}
STATUS_DB = {v: k for k, v in STATUS.items()}


def today() -> str:
    return date.today().isoformat()


def _d(v) -> str | None:
    return v.strftime('%Y-%m-%d') if v else None


# ── 확정 (drafts.confirm 이 부름) ──
def _write_steps(t: db.Tx, roadmap_id: str, plan: dict) -> None:
    items = catalog.items()
    done = {r['activity_id'] for r in t.all("SELECT activity_id FROM app_ext.activity_progress WHERE roadmap_id = CAST(:r AS uuid) AND status = 'done'", r=roadmap_id)}
    t.run('DELETE FROM public.roadmap_steps WHERE roadmap_id = CAST(:r AS uuid)', r=roadmap_id)
    for i, a in enumerate(plan['acts'], 1):
        res = items.get(a.get('res') or '')
        sid = t.val("""INSERT INTO public.roadmap_steps(roadmap_id, step_order, title, activity, estimated_duration, estimated_cost, is_completed, details)
                       VALUES(CAST(:r AS uuid), :o, :t, :a, :du, :c, :done, :d) RETURNING step_id""",
                    r=roadmap_id, o=i, t=a['title'], a=a.get('how') or (res['title'] if res else None), du=f"{a['hours']:g}시간 · {a['wFrom']}~{a['wTo']}주차",
                    c=res['cost'] if res and res['cost'] is not None else None, done=a['id'] in done,
                    d=db.J({k: a.get(k) for k in ('id', 'stage', 'res', 'task', 'hours', 'wFrom', 'wTo', 'skills')}))  # skills: 과제가 다루는 스킬 이름(10/23)
        if res and res['type'] in ('course', 'book', 'cert'):
            col = {'course': 'course_id', 'book': 'isbn', 'cert': 'certification_id'}[res['type']]
            val = a['res'] if res['type'] == 'course' else a['res'].replace('book_', '', 1) if res['type'] == 'book' else int(a['res'].replace('cert_', '', 1))
            t.run(f'INSERT INTO public.roadmap_step_resources(step_id, {col}) VALUES(:s, :v) ON CONFLICT DO NOTHING', s=sid, v=val)


def insert_roadmap(t: db.Tx, project_id: str, round_id: str, plan: dict) -> str:
    rid = str(t.val("""INSERT INTO public.roadmaps(project_id, diagnostic_round_id, strategy_type, strategy_title, summary, content, baseline_content, selected_at)
                       VALUES(CAST(:p AS uuid), CAST(:r AS uuid), :st, :tt, :s, :c, :c, now()) RETURNING roadmap_id""",
                    p=project_id, r=round_id, st=plan['opt'], tt=plan['name'], s=plan['tagline'], c=db.J(plan)))
    _write_steps(t, rid, plan)
    t.run('INSERT INTO app_ext.roadmap_meta(roadmap_id, version) VALUES(CAST(:r AS uuid), 1)', r=rid)
    t.run("INSERT INTO app_ext.roadmap_versions(roadmap_id, version, plan, reason) VALUES(CAST(:r AS uuid), 1, :p, '최초 확정')", r=rid, p=db.J(plan))
    return rid


def shared_with(employee_id: int) -> dict:
    v = profile.view(employee_id) or {}
    return {'supervisor': v.get('mySupervisor')}


# ── 기록 조립 (화면 4차 모양: plans[id] · reports[]) ──
def _base_rows(employee_id: int, roadmap_id: str | None = None) -> list[dict]:
    if roadmap_id is not None:
        # 주소의 로드맵 id 모양이 틀리면 DB 형 변환 오류(500) 대신 '없음'(404)으로 다룬다(PR #23 리뷰 확인 중 발견)
        try:
            roadmap_id = str(uuid.UUID(str(roadmap_id)))
        except ValueError:
            return []
    return db.all_("""SELECT r.roadmap_id, r.project_id, r.content, r.created_at, r.diagnostic_round_id, p.status, p.employee_id,
                         m.version, m.done_at, m.archived_at, m.resumed_at
                      FROM public.roadmaps r JOIN public.projects p ON p.project_id = r.project_id
                      LEFT JOIN app_ext.roadmap_meta m ON m.roadmap_id = r.roadmap_id
                      WHERE p.employee_id = :e AND p.status IN ('IN_PROGRESS', 'COMPLETED', 'ARCHIVED') AND r.content ? 'acts' AND r.content ? 'opt'
                        AND (CAST(:r AS uuid) IS NULL OR r.roadmap_id = CAST(:r AS uuid))
                      ORDER BY r.created_at""", e=employee_id, r=roadmap_id)


def _comments(roadmap_id: str) -> list[dict]:
    rows = db.all_("""SELECT c.comment_id, c.created_at, c.updated_at, c.body, e.name, e.employee_number, m.fit, m.fit_text, m.level, m.level_text, m.free_text, m.status, m.read_at, m.applied_version
                      FROM public.roadmap_comments c JOIN public.employees e ON e.employee_id = c.author_employee_id
                      LEFT JOIN app_ext.comment_meta m ON m.comment_id = c.comment_id WHERE c.roadmap_id = CAST(:r AS uuid) ORDER BY c.created_at""", r=roadmap_id)
    # 수정 여부: 팀 DB 트리거(guard_roadmap_comment)가 작성·본문 수정 때만 updated_at 을 now() 로 쓴다(작성 때는 created_at 과 같음). 이전 내용은 남기지 않는다(10/23 사용자 결정)
    return [{'id': str(c['comment_id']), 'by': c['name'], 'byCode': c['employee_number'], 'fit': c['fit'] or 'none', 'fitText': c['fit_text'] or '',
             'level': c['level'] or 'none', 'levelText': c['level_text'] or '', 'free': c['free_text'] if c['fit'] else c['body'], 'at': _d(c['created_at']),
             'editedAt': _d(c['updated_at']) if c['updated_at'] > c['created_at'] else None, 'stamp': c['updated_at'].isoformat(),
             'status': c['status'] or 'new', 'readAt': _d(c['read_at']), 'appliedVersion': c['applied_version']} for c in rows]


def _post(row: dict, plan: dict) -> dict:
    qs = (plan.get('assess') or {}).get('questions') or []
    ans = {}
    for r in db.all_("""SELECT q.sequence_no, a.score FROM public.assessment_responses a JOIN public.assessment_questions q ON q.question_id = a.question_id
                        WHERE q.diagnostic_round_id = :d AND q.assessment_type = 'POST'""", d=row['diagnostic_round_id']):
        if 0 < r['sequence_no'] <= len(qs):
            ans[qs[r['sequence_no'] - 1]['id']] = str(r['score'])
    # 보고서를 쓰던 작업이 끊겼으면(서버 재시작) 실패로 바꾼다. 작업이 결과를 쓴 뒤 끝났으면 running 이 이미 false 라 바뀌지 않는다
    lost_sql = """UPDATE app_ext.post_checks pc SET running = false, fail = :f WHERE pc.roadmap_id = :r AND pc.running AND pc.job_id IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM app_ext.jobs j WHERE j.job_id = pc.job_id AND j.status = 'running')"""
    # 사후 심화 질문을 만들던 작업이 끊겼어도 같은 방식으로 실패로 바꾼다(다시 시도는 사용자가 누를 때만)
    lost_deep = """UPDATE app_ext.post_checks pc SET deep = jsonb_build_object('status', 'fail', 'fail', CAST(:f AS jsonb)) WHERE pc.roadmap_id = :r
                     AND pc.deep->>'status' = 'run' AND pc.deep->>'jobId' IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM app_ext.jobs j WHERE j.job_id::text = pc.deep->>'jobId' AND j.status = 'running')"""
    with db.tx() as t:
        t.run(lost_sql, f=db.J({'cause': jobs.lost_cause()}), r=row['roadmap_id'])
        t.run(lost_deep, f=json.dumps({'cause': jobs.lost_cause()}, ensure_ascii=False), r=row['roadmap_id'])
    pc = db.one('SELECT goal_self, attachment, running, fail, job_id, deep FROM app_ext.post_checks WHERE roadmap_id = :r', r=row['roadmap_id']) or {}
    return {'answers': ans, 'goalSelf': str(pc['goal_self']) if pc.get('goal_self') else '', 'file': pc.get('attachment'), 'running': bool(pc.get('running')),
            'fail': pc.get('fail'), 'jobId': str(pc['job_id']) if pc.get('job_id') and pc.get('running') else None, 'deep': _post_deep(plan, pc.get('deep'))}


def _post_deep(plan: dict, dp: dict | None) -> dict | None:
    """사후 심화 질문(10/23): 사전에 심화를 고른 로드맵만. 정답·해설·모범 답안은 보고서를 만든 뒤(judge 가 생긴 뒤)에만 보낸다"""
    if not ((plan.get('assess') or {}).get('deep') or {}).get('on'):
        return None
    dp = dp or {}
    reveal = bool(dp.get('judge'))
    return {'status': dp.get('status') or 'none', 'quiz': DC.public(dp.get('quiz'), reveal), 'mcq': dp.get('mcq') or {}, 'essay': dp.get('essay') or {},
            'notes': dp.get('notes') or [], 'fail': dp.get('fail'), 'jobId': dp.get('jobId') if dp.get('status') == 'run' else None,
            'judge': dp.get('judge') if reveal else None, 'grade': DC.grade(dp['quiz'], dp.get('mcq')) if reveal and dp.get('quiz') else None}


def post_deep_start(employee_id: int, roadmap_id: str) -> str | None:
    """사후 심화 질문 만들기(같은 개념, 새 문제 · 10/23). 이미 있으면 그대로, 만드는 중이면 그 작업. 실패는 가데이터로 대신하지 않는다"""
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵만 사후 점검할 수 있어요')
    pl = row['content']
    A = pl.get('assess') or {}
    if not (A.get('deep') or {}).get('on'):
        raise ApiError(409, 'NO_DEEP', '사전 점검에서 심화 질문을 고르지 않아 사후 심화 질문이 없어요')
    dp = (db.one('SELECT deep FROM app_ext.post_checks WHERE roadmap_id = :r', r=row['roadmap_id']) or {}).get('deep') or {}
    if dp.get('status') == 'ready':
        return None
    if dp.get('status') == 'run' and dp.get('jobId') and db.val('SELECT status FROM app_ext.jobs WHERE job_id = CAST(:j AS uuid)', j=dp['jobId']) == 'running':
        return dp['jobId']
    inp = {'goal': pl['goal'], 'acts': [a['title'] for a in pl['acts']], 'questions': A['questions'], 'pre': A['deep']['quiz']}
    with db.tx() as t:
        t.run("""INSERT INTO app_ext.post_checks(roadmap_id, deep) VALUES(:r, :d)
                 ON CONFLICT (roadmap_id) DO UPDATE SET deep = EXCLUDED.deep, updated_at = now()""", r=row['roadmap_id'], d=db.J({'status': 'run', 'jobId': None}))

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        try:
            out = DG.post_deep(ctx, inp)
            if not out.get('deep'):
                raise AgentError('사후 심화 질문이 비어 있어요', ctx.provider)
        except AgentError as e:
            with db.tx() as t:
                t.run('UPDATE app_ext.post_checks SET deep = :d, updated_at = now() WHERE roadmap_id = :r', d=db.J({'status': 'fail', 'fail': {'cause': e.info}}), r=row['roadmap_id'])
            raise
        with db.tx() as t:
            t.run('UPDATE app_ext.post_checks SET deep = :d, updated_at = now() WHERE roadmap_id = :r',
                  d=db.J({'status': 'ready', 'quiz': out['deep'], 'notes': out.get('notes') or [], 'mcq': {}, 'essay': {}}), r=row['roadmap_id'])
        return {'ok': True}
    jid = jobs.start('post-deep', employee_id, roadmap_id, work)
    with db.tx() as t:
        t.run("""UPDATE app_ext.post_checks SET deep = jsonb_set(deep, '{jobId}', to_jsonb(CAST(:j AS text)))
                 WHERE roadmap_id = :r AND deep->>'status' = 'run'""", j=jid, r=row['roadmap_id'])
    return jid


def _revision(roadmap_id: str) -> dict | None:
    # 수정안을 쓰던 작업이 끊겼으면 실패로 바꾼다(작업이 'ready' 를 쓴 뒤 끝났으면 status 가 이미 running 이 아니라 바뀌지 않는다)
    with db.tx() as t:
        t.run("""UPDATE app_ext.roadmap_revisions v SET status = 'failed', error = :e, updated_at = now() WHERE v.roadmap_id = CAST(:r AS uuid) AND v.status = 'running'
                 AND v.job_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM app_ext.jobs j WHERE j.job_id = v.job_id AND j.status = 'running')""",
              e=db.J({'cause': jobs.lost_cause()}), r=roadmap_id)
    return db.one("""SELECT revision_id, request, result, status, error, job_id FROM app_ext.roadmap_revisions
                     WHERE roadmap_id = CAST(:r AS uuid) AND status IN ('running', 'ready', 'failed') ORDER BY created_at DESC LIMIT 1""", r=roadmap_id)


def record(row: dict, for_mgr: bool = False) -> dict:
    rid = str(row['roadmap_id'])
    plan = dict(row['content'], rid=rid)
    versions = [dict(v['plan'], rid=rid) for v in db.all_('SELECT plan FROM app_ext.roadmap_versions WHERE roadmap_id = :r ORDER BY version', r=row['roadmap_id'])] or [plan]
    prog = {}
    for p in db.all_('SELECT activity_id, status, memo, attachment, updated_at FROM app_ext.activity_progress WHERE roadmap_id = :r', r=row['roadmap_id']):
        prog[p['activity_id']] = {'status': p['status'], 'at': _d(p['updated_at'])} if for_mgr else {'status': p['status'], 'memo': p['memo'] or '', 'file': p['attachment'], 'at': _d(p['updated_at'])}
    rec = {'id': rid, 'status': STATUS.get(row['status'], 'active'), 'createdAt': _d(row['created_at']), 'doneAt': _d(row['done_at']), 'archivedAt': _d(row['archived_at']),
           'resumedAt': _d(row['resumed_at']), 'plan': plan, 'versions': versions, 'progress': prog, 'comments': _comments(rid), 'pending': None, 'revision': None}
    if for_mgr:
        # 부서장 공개 범위(설계서 v1.7 1.1): 점검 응답 원본·진단 내용·메모·첨부·수정안은 빼고 보낸다
        for v in [rec['plan']] + rec['versions']:
            v.pop('handoff', None)
            if v.get('assess'):
                v['assess'] = {'questions': [], 'answers': {}, 'domain': v['assess'].get('domain')}
        rec['post'] = {'answers': {}, 'goalSelf': '', 'file': None}
        return rec
    rec['post'] = _post(row, plan)
    rv = _revision(rid)
    if rv:
        rec['revision'] = {'id': str(rv['revision_id']), 'status': rv['status'], 'error': rv['error'], 'jobId': str(rv['job_id']) if rv['job_id'] else None,
                           'request': rv['request']}
        if rv['status'] == 'ready':
            rec['pending'] = rv['result']
    return rec


def records(employee_id: int, statuses: tuple | None = None, for_mgr: bool = False) -> dict[str, dict]:
    out = {}
    for row in _base_rows(employee_id):
        r = record(row, for_mgr)
        if not statuses or r['status'] in statuses:
            out[r['id']] = r
    return out


def _owned(employee_id: int, roadmap_id: str) -> dict:
    rows = _base_rows(employee_id, roadmap_id)
    if not rows:
        raise not_found('로드맵')
    return rows[0]


MGR_HIDDEN = ('deep', 'goalSelf', 'file')


def reports(employee_id: int, for_mgr: bool = False) -> list[dict]:
    rows = db.all_("""SELECT g.report_id, g.roadmap_id, g.report_content, g.created_at, coalesce(m.confirmed, false) AS confirmed
                      FROM public.growth_reports g JOIN public.projects p ON p.project_id = g.project_id LEFT JOIN app_ext.report_meta m ON m.report_id = g.report_id
                      WHERE p.employee_id = :e AND g.report_content ? 'gained' ORDER BY g.created_at DESC""", e=employee_id)
    out = []
    for r in rows:
        # 수준값은 화면에 보내지 않는다. 부서장 화면에는 심화 질문 결과(10/23)와 사후 점검 원본 응답·첨부(목표 달성 답·결과물 파일 · PR #23 리뷰)를 빼고 보낸다
        c = {k: v for k, v in r['report_content'].items() if k != 'hidden' and not (for_mgr and k in MGR_HIDDEN)}
        c.update(id=str(r['report_id']), planId=str(r['roadmap_id']), confirmed=bool(r['confirmed']), createdAt=_d(r['created_at']))
        out.append(c)
    return out


def resources_of(recs: dict, reps: list | None = None) -> dict:
    keys = []
    for r in recs.values():
        for v in [r['plan']] + r['versions'] + ([r['pending']['to'], r['pending']['from']] if r.get('pending') else []):
            keys += [a.get('res') for a in v.get('acts', [])]
    return catalog.resources_for(keys)


def reg_of(recs: dict) -> dict:
    ids = []
    for r in recs.values():
        for v in [r['plan']] + r['versions'] + ([r['pending']['to']] if r.get('pending') else []):
            ids += list(((v.get('def') or {}).get('support') or {}).get('basis') or [])
    return regstore.bundle(ids)


def workspace(employee_id: int) -> dict:
    recs = records(employee_id)
    reps = reports(employee_id)
    return {'plans': recs, 'reports': reps, 'res': resources_of(recs), 'reg': reg_of(recs)}


# ── 진행 기록 (API-38) ──
def save_progress(employee_id: int, roadmap_id: str, act_id: str, body: dict) -> dict:
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵만 기록할 수 있어요')
    if not any(a['id'] == act_id for a in row['content']['acts']):
        raise not_found('활동')
    st = body.get('status') if body.get('status') in ('doing', 'done') else 'doing'
    with db.tx() as t:
        old = t.one('SELECT memo, attachment FROM app_ext.activity_progress WHERE roadmap_id = CAST(:r AS uuid) AND activity_id = :a', r=roadmap_id, a=act_id) or {}
        memo = body['memo'] if 'memo' in body and body['memo'] is not None else old.get('memo')
        att = body['file'] if 'file' in body else old.get('attachment')
        t.run("""INSERT INTO app_ext.activity_progress(roadmap_id, activity_id, status, memo, attachment) VALUES(CAST(:r AS uuid), :a, :s, :m, :f)
                 ON CONFLICT (roadmap_id, activity_id) DO UPDATE SET status = EXCLUDED.status, memo = EXCLUDED.memo, attachment = EXCLUDED.attachment, updated_at = now()""",
              r=roadmap_id, a=act_id, s=st, m=memo or '', f=db.J(att) if att else None)
        # 완료 여부만 ERD 단계 행에 맞춘다(완료 여부만 바뀌면 팀 DB 트리거가 코멘트를 건드리지 않음)
        t.run("UPDATE public.roadmap_steps SET is_completed = :d WHERE roadmap_id = CAST(:r AS uuid) AND details->>'id' = :a", d=st == 'done', r=roadmap_id, a=act_id)
    return record(_owned(employee_id, roadmap_id))


# ── 보관·다시 진행 (API-41·42) ──
def archive(employee_id: int, roadmap_id: str) -> dict:
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵만 보관할 수 있어요')
    with db.tx() as t:
        t.run("UPDATE public.projects SET status = 'ARCHIVED', updated_at = now() WHERE project_id = :p", p=row['project_id'])
        t.run('UPDATE app_ext.roadmap_meta SET archived_at = now() WHERE roadmap_id = :r', r=row['roadmap_id'])
        t.run("UPDATE app_ext.roadmap_revisions SET status = 'discarded', updated_at = now() WHERE roadmap_id = :r AND status IN ('running', 'ready', 'failed')", r=row['roadmap_id'])
    return record(_owned(employee_id, roadmap_id))


def resume(employee_id: int, roadmap_id: str) -> dict:
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'archived':
        raise ApiError(409, 'NOT_ARCHIVED', '보관한 로드맵만 다시 진행할 수 있어요')
    with db.tx() as t:
        t.run("UPDATE public.projects SET status = 'IN_PROGRESS', updated_at = now() WHERE project_id = :p", p=row['project_id'])
        t.run('UPDATE app_ext.roadmap_meta SET archived_at = NULL, resumed_at = now() WHERE roadmap_id = :r', r=row['roadmap_id'])
    return record(_owned(employee_id, roadmap_id))


# ── 수정안 (API-43~45) ──
REV_FIELDS = {'hours': '주당 학습 시간', 'weeks': '정해진 기간', 'budget': '교육 예산', 'format': '학습 방식', 'cert': '자격증 계획', 'etc': '일정·환경 제약',
              'start': '시작 단계', 'pid': '관점', 'remove': '활동 빼기', 'replace': '활동 바꾸기', 'add': '활동 추가'}


def _rev_changes(r: dict, pl: dict) -> dict:
    """수정 요청 화면에서 고른 항목만 사람이 읽는 값으로 (4차 revChanges)"""
    from .drafts import pref_text, cert_res
    v, on, c = r['v'], r.get('on') or {}, {}
    blank = lambda x: x in ('', None)  # noqa: E731
    act_ref = lambda i: next(({'key': a['id'], 'title': a['title']} for a in pl['acts'] if a['id'] == i), None)  # noqa: E731
    raw = dict(pl.get('prefs') or {})
    for k in ('hours', 'weeks', 'budget', 'format', 'cert', 'etc'):
        if on.get(k):
            raw[k] = v.get(k)
    if on.get('hours'):
        c['weeklyHours'] = '알아서' if blank(v.get('hours')) else float(v['hours'])
    if on.get('weeks'):
        c['deadlineWeeks'] = '없음' if blank(v.get('weeks')) else int(float(v['weeks']))
    if on.get('budget'):
        c['budgetWon'] = '알아서' if blank(v.get('budget')) else int(float(v['budget']))
    if on.get('format'):
        c['format'] = pref_text('format', raw)
    if on.get('cert'):
        cc = catalog.cert_by_code(raw.get('cert'))
        c['certification'] = cc['title'] if cc else '계획 없음'
    if on.get('etc'):
        c['constraints'] = str(v.get('etc') or '').strip() or '없음'
    if on.get('start'):
        c['startStage'] = int(v['start'])
    if on.get('pid') and v.get('pid') != pl['opt']:
        c['perspective'] = f"{v['pid']} {D['perspectives'][v['pid']]['name']}"
    if on.get('remove'):
        c['removeActs'] = [x for x in (act_ref(i) for i in v.get('remove') or []) if x]
    if on.get('replace'):
        c['replaceActs'] = [x for x in (act_ref(i) for i in v.get('replace') or [] if not (on.get('remove') and i in (v.get('remove') or []))) if x]
        if str(v.get('replaceHow') or '').strip():
            c['replaceHint'] = v['replaceHow'].strip()
    if on.get('add'):
        if v.get('addRes'):
            c['addResources'] = list(v['addRes'])
        tasks = [x.strip() for x in str(v.get('addTask') or '').split('\n') if x.strip()][:5]
        if tasks:
            c['addTasks'] = tasks
    return {'c': c, 'raw': raw, 'pid': v['pid'] if on.get('pid') and v.get('pid') != pl['opt'] else pl['opt'], 'start': int(v['start']) if on.get('start') else pl['start'],
            'certRes': cert_res(raw)}


def revise_start(employee_id: int, roadmap_id: str, body: dict) -> dict:
    """수정안 작성(API-43). 확정하기 전까지 기존 로드맵은 그대로. 실패하면 가데이터로 대신하지 않는다"""
    from .drafts import handoff_prefs
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵만 고칠 수 있어요')
    base = row['content']
    rev = body.get('rev') or {}
    ch = _rev_changes(rev, base)
    prefs_h = handoff_prefs(ch['raw'])
    handoff = dict(base.get('handoff') or {}, prefs=prefs_h, startStage=ch['start'], userNotes=[ch['raw']['etc'].strip()] if str(ch['raw'].get('etc') or '').strip() else [])
    req = str(rev.get('note') or '').strip()
    done = {p['activity_id'] for p in db.all_("SELECT activity_id FROM app_ext.activity_progress WHERE roadmap_id = :r AND status = 'done'", r=row['roadmap_id'])}
    inp = {'pid': ch['pid'], 'handoff': handoff, 'changes': ch['c'], 'request': req or None, 'fromComment': rev.get('fromComment') or False,
           'plan': {k: base.get(k) for k in ('opt', 'name', 'tagline', 'def', 'hours', 'start')} | {'acts': [dict(a, done=a['id'] in done) for a in base['acts']]}}
    with db.tx() as t:
        t.run("UPDATE app_ext.roadmap_revisions SET status = 'discarded', updated_at = now() WHERE roadmap_id = :r AND status IN ('running', 'ready', 'failed')", r=row['roadmap_id'])
        rev_id = str(t.val("INSERT INTO app_ext.roadmap_revisions(roadmap_id, request, status) VALUES(:r, :q, 'running') RETURNING revision_id",
                           r=row['roadmap_id'], q=db.J(dict(rev, key=body.get('key')))))

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        try:
            out = RM.revise(ctx, inp, sim=rt.sim_once(ctx, 'rev', str(body.get('key') or rev_id)))
        except AgentError as e:
            with db.tx() as t:
                t.run("UPDATE app_ext.roadmap_revisions SET status = 'failed', error = :e, updated_at = now() WHERE revision_id = CAST(:i AS uuid) AND status = 'running'",
                      e=db.J({'cause': e.info}), i=rev_id)
            raise
        d = RM.keep_ids(out, base, base['version'] + 1)
        to = RM.build_plan(d, {'start': ch['start'], 'hours': prefs_h['weeklyHours'] or d.get('weeklyHours') or base['hours'] or D['autoHours'], 'format': prefs_h['formatKey'], 'patch': {}}, base['goal'])
        summary = str(out.get('summary') or '').strip()
        pd = {'from': base, 'to': to, 'key': body.get('key'), 'request': req, 'fromComment': rev.get('fromComment') or False, 'summary': summary, 'notes': out.get('notes') or [],
              'source': d.get('source'), 'prefsFrom': base.get('prefs'), 'prefsTo': ch['raw'], 'handoff': handoff,
              'label': f"{'부서장 코멘트 반영' if rev.get('fromComment') else '수정 요청 반영'}{' · ' + summary if summary else ''}"[:70]}
        # 지원 조건: 자료·자격·기간·비용이 그대로면 이전 버전의 확인 결과, 바뀌었으면 규정 에이전트가 이 버전을 다시 확인(설계서 v1.7 SCR-RM-06)
        sup = (base.get('def') or {}).get('support')
        if sup and RM.sup_sig(to) == RM.sup_sig(base):
            to['def']['support'] = copy.deepcopy(sup)
            pd['supSame'] = True
        with db.tx() as t:
            t.run("UPDATE app_ext.roadmap_revisions SET status = 'ready', result = :p, updated_at = now() WHERE revision_id = CAST(:i AS uuid) AND status = 'running'",
                  p=db.J(pd), i=rev_id)
        if not to['def'].get('support'):
            revision_support(employee_id, roadmap_id, rev_id)
        return {'revisionId': rev_id}
    jid = jobs.start('revision', employee_id, roadmap_id, work)
    with db.tx() as t:
        t.run('UPDATE app_ext.roadmap_revisions SET job_id = CAST(:j AS uuid) WHERE revision_id = CAST(:i AS uuid)', j=jid, i=rev_id)
    return {'revisionId': rev_id, 'jobId': jid}


def revision_support(employee_id: int, roadmap_id: str, rev_id: str) -> str | None:
    """수정안의 지원 조건 확인(바뀐 경우만). 실패하면 '확인 필요'로 두고 다시 확인은 사용자가 누를 때만"""
    rv = db.one('SELECT result, status FROM app_ext.roadmap_revisions WHERE revision_id = CAST(:i AS uuid)', i=rev_id)
    if not rv or rv['status'] != 'ready':
        return None
    pd = rv['result']
    from .drafts import _sup_input, _plans_brief

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        err, out = None, None
        try:
            out = REG.support(ctx, [_sup_input(pd['to']['opt'], pd['to']['name'], pd['to'])], REG.reg_context(ctx.me, _plans_brief(employee_id), None),
                              sim=rt.sim_once(ctx, 'sup', 'rev|' + str(pd.get('key'))))
        except AgentError as e:
            err = e.info
        with db.tx() as t:
            cur = t.one('SELECT result, status FROM app_ext.roadmap_revisions WHERE revision_id = CAST(:i AS uuid) FOR UPDATE', i=rev_id)
            if not cur:
                # 확인하는 동안 수정안이 지워졌으면(시연 초기화 등으로 로드맵과 함께 지워짐) 결과를 쓸 곳이 없다.
                # 성공으로 바꾸지 않고 이유를 적어 작업을 실패로 남긴다(작업 표 error · 서버 오류 추적은 남기지 않음)
                raise ApiError(409, 'REVISION_GONE', '확인하는 동안 수정안이 지워져 지원 조건 확인 결과를 저장하지 않았어요')
            res = cur['result']
            if err:
                res['supFail'] = {'cause': err}
            else:
                res['to']['def']['support'] = (out or {}).get(res['to']['opt']) or {'level': 'missing', 'summary': '이 버전은 확인 결과를 받지 못했어요. 담당 부서에 확인해 주세요.', 'basis': [], 'missing': []}
                res.pop('supFail', None)
            if cur['status'] == 'ready':
                t.run('UPDATE app_ext.roadmap_revisions SET result = :r, updated_at = now() WHERE revision_id = CAST(:i AS uuid)', r=db.J(res), i=rev_id)
            elif cur['status'] == 'accepted' and not err:
                # 확인 중에 확정했으면 확정한 버전에 남긴다
                _patch_current_support(roadmap_id, res['to']['def']['support'])
        if err:
            raise AgentError(err['raw'] or err['text'])
        return {'ok': True}
    return jobs.start('revision-support', employee_id, roadmap_id, work)


def _patch_current_support(roadmap_id: str, support: dict) -> None:
    with db.tx() as t:
        row = t.one('SELECT content FROM public.roadmaps WHERE roadmap_id = CAST(:r AS uuid) FOR UPDATE', r=roadmap_id)
        content = row['content']
        content.setdefault('def', {})['support'] = support
        _actor_for_comments(t, roadmap_id)
        t.run('UPDATE public.roadmaps SET content = :c, updated_at = now() WHERE roadmap_id = CAST(:r AS uuid)', c=db.J(content), r=roadmap_id)
        t.run("UPDATE app_ext.roadmap_versions SET plan = :c WHERE roadmap_id = CAST(:r AS uuid) AND version = :v", c=db.J(content), r=roadmap_id, v=content.get('version'))


def revision_support_retry(employee_id: int, roadmap_id: str) -> str | None:
    _owned(employee_id, roadmap_id)
    rv = _revision(roadmap_id)
    if not rv or rv['status'] != 'ready':
        raise ApiError(409, 'NO_REVISION', '다시 확인할 수정안이 없어요')
    res = rv['result']
    res.pop('supFail', None)
    with db.tx() as t:
        t.run('UPDATE app_ext.roadmap_revisions SET result = :r WHERE revision_id = :i', r=db.J(res), i=rv['revision_id'])
    return revision_support(employee_id, roadmap_id, str(rv['revision_id']))


def _actor_for_comments(t: db.Tx, roadmap_id: str) -> None:
    """로드맵 내용이 바뀌면 팀 DB 트리거가 코멘트를 '수정 완료'로 바꾼다. 그 갱신은 코멘트 작성자 정보가 있어야 통과한다.
    한 로드맵의 코멘트는 보통 내 계획을 보는 부서장 한 명이 쓴다. 작성자가 둘 이상이면 저장이 막혀 오류로 알린다(팀원 요청 목록)"""
    authors = [r['author_employee_id'] for r in t.all('SELECT DISTINCT author_employee_id FROM public.roadmap_comments WHERE roadmap_id = CAST(:r AS uuid)', r=roadmap_id)]
    if len(authors) == 1:
        t.actor(authors[0])
    elif len(authors) > 1:
        raise ApiError(409, 'COMMENT_TRIGGER', '이 로드맵에 코멘트를 남긴 부서장이 여러 명이라 지금은 새 버전을 저장할 수 없어요. 담당자에게 알려 주세요',
                       '팀 DB 트리거(mark_roadmap_comments_modified → guard_roadmap_comment)가 코멘트 작성자 한 명의 정보만 받을 수 있어요. 팀원 요청 목록 참고')


def accept_revision(employee_id: int, roadmap_id: str, revision_id: str) -> dict:
    row = _owned(employee_id, roadmap_id)
    with db.tx() as t:
        rv = t.one("SELECT result, status FROM app_ext.roadmap_revisions WHERE revision_id = CAST(:i AS uuid) AND roadmap_id = :r FOR UPDATE", i=revision_id, r=row['roadmap_id'])
        if not rv or rv['status'] != 'ready':
            raise ApiError(409, 'NO_REVISION', '확정할 수정안이 없어요')
        pd, cur = rv['result'], row['content']
        changed = pd['to']['opt'] != cur['opt']
        from .drafts import selection_of
        plan = dict(pd['to'], version=cur['version'] + 1, confirmedAt=today(), why=pd['label'], assess=cur.get('assess'), prefs=pd['prefsTo'], handoff=pd['handoff'],
                    selection=selection_of(pd['to']['def']) if changed else cur.get('selection'))
        _actor_for_comments(t, roadmap_id)
        t.run('UPDATE public.roadmaps SET content = :c, strategy_type = :st, strategy_title = :tt, summary = :s, updated_at = now() WHERE roadmap_id = :r',
              c=db.J(plan), st=plan['opt'], tt=plan['name'], s=plan['tagline'], r=row['roadmap_id'])
        _write_steps(t, roadmap_id, plan)
        t.run('UPDATE app_ext.roadmap_meta SET version = :v WHERE roadmap_id = :r', v=plan['version'], r=row['roadmap_id'])
        t.run('INSERT INTO app_ext.roadmap_versions(roadmap_id, version, plan, reason) VALUES(:r, :v, :p, :w)', r=row['roadmap_id'], v=plan['version'], p=db.J(plan), w=pd['label'])
        t.run("UPDATE app_ext.roadmap_revisions SET status = 'accepted', updated_at = now() WHERE revision_id = CAST(:i AS uuid)", i=revision_id)
        if pd.get('fromComment'):
            t.run("""INSERT INTO app_ext.comment_meta(comment_id, status, applied_version) VALUES(CAST(:c AS uuid), 'applied', :v)
                     ON CONFLICT (comment_id) DO UPDATE SET status = 'applied', applied_version = :v""", c=pd['fromComment'], v=plan['version'])
    return record(_owned(employee_id, roadmap_id))


def discard_revision(employee_id: int, roadmap_id: str, revision_id: str) -> None:
    row = _owned(employee_id, roadmap_id)
    with db.tx() as t:
        t.run("UPDATE app_ext.roadmap_revisions SET status = 'discarded', updated_at = now() WHERE revision_id = CAST(:i AS uuid) AND roadmap_id = :r", i=revision_id, r=row['roadmap_id'])


# ── 코멘트 (API-46·47 · 부서장 API-58 · 부서장 코멘트 수정은 설계서 밖 추가 10/23) ──
def read_comment(employee_id: int, roadmap_id: str, comment_id: str) -> dict:
    row = _owned(employee_id, roadmap_id)
    with db.tx() as t:
        if not t.one('SELECT 1 FROM public.roadmap_comments WHERE comment_id = CAST(:c AS uuid) AND roadmap_id = :r', c=comment_id, r=row['roadmap_id']):
            raise not_found('코멘트')
        t.run("""INSERT INTO app_ext.comment_meta(comment_id, status, read_at) VALUES(CAST(:c AS uuid), 'read', now())
                 ON CONFLICT (comment_id) DO UPDATE SET status = CASE WHEN app_ext.comment_meta.status = 'new' THEN 'read' ELSE app_ext.comment_meta.status END,
                 read_at = coalesce(app_ext.comment_meta.read_at, now())""", c=comment_id)
    return record(_owned(employee_id, roadmap_id))


def _comment_body(fit: str, fit_text: str, level: str, level_text: str, free: str) -> str:
    lb = lambda lst, v: next((l for x, l in lst if x == v), '의견 없음')  # noqa: E731
    lines = [f"업무 적합성: {lb(D['commentFit'], fit)}{' — ' + fit_text if fit_text else ''}", f"수준·기간·분량: {lb(D['commentLevel'], level)}{' — ' + level_text if level_text else ''}"]
    if free:
        lines.append(f'자유 의견: {free}')
    return '\n'.join(lines)


def _comment_target(head_id: int, member_id: int, roadmap_id: str, verb: str) -> dict:
    if member_id not in profile.member_ids(head_id):
        raise forbidden('소속 직원이 아니에요')
    row = _owned(member_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', f'진행 중인 로드맵에만 코멘트를 {verb} 수 있어요')
    return row


def _comment_fields(body: dict) -> dict:
    f = {'fit': body.get('fit'), 'fitText': (body.get('fitText') or '').strip(), 'level': body.get('level'), 'levelText': (body.get('levelText') or '').strip(),
         'free': (body.get('free') or '').strip()}
    if f['fit'] not in {x for x, _ in D['commentFit']} or f['level'] not in {x for x, _ in D['commentLevel']}:
        raise ApiError(422, 'COMMENT_FIELDS', '업무 적합성과 수준·기간·분량을 골라 주세요')
    return f


def send_comment(head_id: int, member_id: int, roadmap_id: str, body: dict) -> str:
    row = _comment_target(head_id, member_id, roadmap_id, '보낼')
    f = _comment_fields(body)
    with db.tx() as t:
        t.actor(head_id)
        cid = str(t.val('INSERT INTO public.roadmap_comments(roadmap_id, author_employee_id, body) VALUES(:r, :a, :b) RETURNING comment_id', r=row['roadmap_id'], a=head_id,
                        b=_comment_body(f['fit'], f['fitText'], f['level'], f['levelText'], f['free'])))
        t.run("""INSERT INTO app_ext.comment_meta(comment_id, fit, fit_text, level, level_text, free_text, status) VALUES(CAST(:c AS uuid), :f, :ft, :l, :lt, :fr, 'new')""",
              c=cid, f=f['fit'], ft=f['fitText'], l=f['level'], lt=f['levelText'], fr=f['free'])
    return cid


def edit_comment(head_id: int, member_id: int, roadmap_id: str, comment_id: str, body: dict) -> bool:
    """보낸 코멘트 고치기(10/23 사용자 요청 · 삭제는 직원에게 혼선을 줘서 두지 않음).
    직원이 수정안으로 반영하기 전(새·확인함)까지만 고칠 수 있고, 고치면 직원에게 다시 '새 코멘트'로 보인다. 이전 내용은 남기지 않는다(덮어쓰기).
    바뀐 값이 없으면 저장하지 않고 False"""
    row = _comment_target(head_id, member_id, roadmap_id, '고칠')
    f = _comment_fields(body)
    with db.tx() as t:
        c = t.one('SELECT author_employee_id FROM public.roadmap_comments WHERE comment_id = CAST(:c AS uuid) AND roadmap_id = :r FOR UPDATE', c=comment_id, r=row['roadmap_id'])
        if not c:
            raise not_found('코멘트')
        if c['author_employee_id'] != head_id:
            raise forbidden('내가 보낸 코멘트만 고칠 수 있어요')
        # 직원의 수정안 확정(accept_revision)이 같은 행을 'applied' 로 바꾸므로 잠근 뒤 상태를 본다
        m = t.one('SELECT fit, fit_text, level, level_text, free_text, status FROM app_ext.comment_meta WHERE comment_id = CAST(:c AS uuid) FOR UPDATE', c=comment_id) or {}
        if m.get('status') == 'applied':
            raise ApiError(409, 'COMMENT_APPLIED', '직원이 이미 로드맵에 반영한 코멘트라 고칠 수 없어요', '새 의견은 새 코멘트로 보내 주세요')
        if m and [m['fit'], m['fit_text'] or '', m['level'], m['level_text'] or '', m['free_text'] or ''] == [f['fit'], f['fitText'], f['level'], f['levelText'], f['free']]:
            return False
        t.actor(head_id)
        t.run('UPDATE public.roadmap_comments SET body = :b WHERE comment_id = CAST(:c AS uuid)', c=comment_id,
              b=_comment_body(f['fit'], f['fitText'], f['level'], f['levelText'], f['free']))
        t.run("""INSERT INTO app_ext.comment_meta(comment_id, fit, fit_text, level, level_text, free_text, status) VALUES(CAST(:c AS uuid), :f, :ft, :l, :lt, :fr, 'new')
                 ON CONFLICT (comment_id) DO UPDATE SET fit = :f, fit_text = :ft, level = :l, level_text = :lt, free_text = :fr, status = 'new', read_at = NULL""",
              c=comment_id, f=f['fit'], ft=f['fitText'], l=f['level'], lt=f['levelText'], fr=f['free'])
    return True


# ── 사후 점검·결과 보고서 (API-48~52) ──
def save_post(employee_id: int, roadmap_id: str, body: dict) -> dict:
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵만 사후 점검할 수 있어요')
    qs = row['content']['assess']['questions']
    labels = dict(D['answerOpts'])
    with db.tx() as t:
        pre = t.all("SELECT question_id, skill, question, options, sequence_no FROM public.assessment_questions WHERE diagnostic_round_id = :d AND assessment_type = 'PRE' ORDER BY sequence_no",
                    d=row['diagnostic_round_id'])
        post = {r['sequence_no']: r['question_id'] for r in t.all("SELECT question_id, sequence_no FROM public.assessment_questions WHERE diagnostic_round_id = :d AND assessment_type = 'POST'",
                                                                   d=row['diagnostic_round_id'])}
        if not post:
            for q in pre:
                post[q['sequence_no']] = t.val("""INSERT INTO public.assessment_questions(project_id, diagnostic_round_id, assessment_type, skill, question, options, sequence_no)
                                                  VALUES(:p, :d, 'POST', :s, :q, :o, :n) RETURNING question_id""",
                                               p=row['project_id'], d=row['diagnostic_round_id'], s=q['skill'], q=q['question'], o=db.J(q['options']), n=q['sequence_no'])
        for i, q in enumerate(qs, 1):
            v = (body.get('answers') or {}).get(q['id'])
            if i not in post:
                continue
            if v:
                t.run("""INSERT INTO public.assessment_responses(project_id, question_id, assessment_type, selected_option, score) VALUES(:p, :q, 'POST', :o, :s)
                         ON CONFLICT (project_id, question_id) DO UPDATE SET selected_option = EXCLUDED.selected_option, score = EXCLUDED.score, answered_at = now()""",
                      p=row['project_id'], q=post[i], o=labels.get(str(v), str(v)), s=int(v))
        gs = body.get('goalSelf')
        t.run("""INSERT INTO app_ext.post_checks(roadmap_id, goal_self, attachment) VALUES(:r, :g, :a)
                 ON CONFLICT (roadmap_id) DO UPDATE SET goal_self = EXCLUDED.goal_self, attachment = coalesce(EXCLUDED.attachment, app_ext.post_checks.attachment), updated_at = now()""",
              r=row['roadmap_id'], g=int(gs) if str(gs or '').isdigit() else None, a=db.J(body['file']) if body.get('file') else None)
        if 'clearFail' in body:
            t.run('UPDATE app_ext.post_checks SET fail = NULL WHERE roadmap_id = :r', r=row['roadmap_id'])
        if 'deepMcq' in body or 'deepEssay' in body:
            # 사후 심화 답: 문항이 준비된 뒤에만, 보고서를 만든 뒤(정답을 본 뒤)에는 바꾸지 않는다
            dp = (t.one('SELECT deep FROM app_ext.post_checks WHERE roadmap_id = :r FOR UPDATE', r=row['roadmap_id']) or {}).get('deep') or {}
            if dp.get('status') == 'ready' and not dp.get('judge'):
                if isinstance(body.get('deepMcq'), dict):
                    dp['mcq'] = {k: str(v) for k, v in body['deepMcq'].items() if k in dp['quiz']['mcq'] and v not in (None, '')}
                if isinstance(body.get('deepEssay'), dict):
                    ids = {e['id'] for e in dp['quiz']['essays']}
                    dp['essay'] = {k: str(v)[:2000] for k, v in body['deepEssay'].items() if k in ids}
                t.run('UPDATE app_ext.post_checks SET deep = :d, updated_at = now() WHERE roadmap_id = :r', d=db.J(dp), r=row['roadmap_id'])
    return record(_owned(employee_id, roadmap_id))


def _report_deep(row: dict, A: dict) -> dict | None:
    """결과 보고서용 심화 비교(10/23): 개념별 사전·사후 객관식 결과, 사후 서술형 답(핵심 요소·사전 판단과 함께). 심화를 안 골랐으면 None"""
    pre = A.get('deep') or {}
    if not pre.get('on'):
        return None
    dp = (db.one('SELECT deep FROM app_ext.post_checks WHERE roadmap_id = :r', r=row['roadmap_id']) or {}).get('deep') or {}
    if dp.get('status') != 'ready' or not DC.complete(dp['quiz'], dp.get('mcq')):
        raise ApiError(409, 'POST_DEEP_INCOMPLETE', '사후 심화 질문의 객관식에 모두 답해 주세요(‘잘 모르겠어요’도 돼요)')
    g = DC.grade(dp['quiz'], dp['mcq'])
    concepts = [{'concept': DG.skill_label(q.get('skill') or '') or q['text'], 'statement': q['text'],
                 'pre': (pre['grade'].get(q['id']) or {}).get('result') or '답 안 함', 'post': g[q['id']]['result']}
                for q in A['questions'] if q['id'] in dp['quiz']['mcq']]
    pre_lv = {e['area']: (pre['judge'].get(e['id']) or {}).get('level') for e in pre['quiz']['essays']}
    essays = [{'id': e['id'], 'area': e['area'], 'question': e['q'], 'points': e['points'], 'answer': str((dp.get('essay') or {}).get(e['id']) or '').strip(),
               'preLevel': pre_lv.get(e['area'])} for e in dp['quiz']['essays']]
    return {'concepts': concepts, 'essays': essays}


def report_start(employee_id: int, roadmap_id: str) -> str:
    row = _owned(employee_id, roadmap_id)
    rec = record(row)
    pl, post = rec['plan'], rec['post']
    A = pl['assess']
    if not all(post['answers'].get(q['id']) for q in A['questions']) or not post['goalSelf']:
        raise ApiError(409, 'POST_INCOMPLETE', '사후 점검 문항과 목표 달성에 모두 답해 주세요')
    items = [{'id': q['id'], 'area': q['area'], 'text': q['text'], 'skill': DG.skill_label(q.get('skill') or ''), 'pre': A['answers'].get(q['id']), 'post': post['answers'][q['id']]} for q in A['questions']]
    prog = rec['progress']
    done = [a for a in pl['acts'] if (prog.get(a['id']) or {}).get('status') == 'done']
    rest = [a for a in pl['acts'] if (prog.get(a['id']) or {}).get('status') != 'done']
    goal_self = D['goalSelf'][int(post['goalSelf']) - 1] if post['goalSelf'] else ''
    deep_inp = _report_deep(row, A)
    with db.tx() as t:
        if t.one('SELECT 1 FROM public.growth_reports g JOIN app_ext.report_meta m ON m.report_id = g.report_id WHERE g.roadmap_id = :r AND m.confirmed', r=row['roadmap_id']):
            raise ApiError(409, 'REPORT_CONFIRMED', '확인한 보고서가 있어 다시 만들 수 없어요')
        t.run('UPDATE app_ext.post_checks SET running = true, fail = NULL WHERE roadmap_id = :r', r=row['roadmap_id'])
    level_pre = (db.val('SELECT diagnostic_result FROM public.diagnostic_rounds WHERE diagnostic_round_id = :d', d=row['diagnostic_round_id']) or {}).get('level')

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        inp = {'goal': pl['goal'], 'planName': pl['name'], 'opt': pl['opt'], 'domain': A.get('domain'), 'items': items, 'doneTitles': [a['title'] for a in done],
               'restTitles': [a['title'] for a in rest], 'total': len(pl['acts']), 'goalSelf': goal_self}
        if deep_inp:
            inp['deep'] = deep_inp
        try:
            out = DG.report(ctx, inp, sim=rt.sim_once(ctx, 'report', json.dumps([roadmap_id, post['answers'], post['goalSelf']], sort_keys=True)))
        except AgentError as e:
            with db.tx() as t:
                t.run('UPDATE app_ext.post_checks SET running = false, fail = :f WHERE roadmap_id = :r', f=db.J({'cause': e.info}), r=row['roadmap_id'])
            raise
        r = {'planId': roadmap_id, 'version': pl['version'], 'goal': pl['goal'], 'opt': pl['name'],
             'gained': [{'skill': x['skill'], 'from': x['pre'], 'to': x['post']} for x in items if DG.rose(x['pre'], x['post'])],
             'still': [{'skill': x['skill'], 'from': x['pre'], 'to': x['post']} for x in items if not DG.rose(x['pre'], x['post'])],
             'doneTitles': inp['doneTitles'], 'restTitles': inp['restTitles'], 'goalSelf': goal_self, 'file': post.get('file'),
             'good': out['good'], 'improve': out['improve'], 'next': out['next'],
             'hidden': {'pre': level_pre, 'post': DG.level_of(A['questions'], post['answers'])}}
        if deep_inp:
            # 보고서에는 개념별 사전→사후 결과와 영역별 서술형 판단만(부서장 화면에는 보내지 않음 · reports(for_mgr))
            judge = out.get('judge') or {}
            r['deep'] = {'concepts': [{'concept': c['concept'], 'pre': c['pre'], 'post': c['post']} for c in deep_inp['concepts']],
                         'essays': [{'area': e['area'], 'pre': e['preLevel'], 'post': (judge.get(e['id']) or {}).get('level'), 'why': (judge.get(e['id']) or {}).get('why')}
                                    for e in deep_inp['essays']]}
        with db.tx() as t:
            if deep_inp:
                t.run("UPDATE app_ext.post_checks SET deep = deep || jsonb_build_object('judge', CAST(:j AS jsonb)) WHERE roadmap_id = :r",
                      j=json.dumps(out.get('judge') or {}, ensure_ascii=False), r=row['roadmap_id'])
            # 팀 DB 보고서는 넣은 뒤 고칠 수 없어(트리거) 확인 전 보고서는 지우고 새로 넣는다
            t.run('DELETE FROM public.growth_reports WHERE roadmap_id = :r', r=row['roadmap_id'])
            rep_id = str(t.val("INSERT INTO public.growth_reports(project_id, roadmap_id, report_type, report_content) VALUES(:p, :r, 'PRE_POST', :c) RETURNING report_id",
                               p=row['project_id'], r=row['roadmap_id'], c=db.J(r)))
            t.run('INSERT INTO app_ext.report_meta(report_id) VALUES(CAST(:i AS uuid))', i=rep_id)
            t.run('UPDATE public.diagnostic_rounds SET post_completed_at = now() WHERE diagnostic_round_id = :d', d=row['diagnostic_round_id'])
            t.run('UPDATE app_ext.post_checks SET running = false, fail = NULL WHERE roadmap_id = :r', r=row['roadmap_id'])
        return {'reportId': rep_id}
    jid = jobs.start('report', employee_id, roadmap_id, work)
    with db.tx() as t:
        t.run('UPDATE app_ext.post_checks SET job_id = CAST(:j AS uuid) WHERE roadmap_id = :r', j=jid, r=row['roadmap_id'])
    return jid


def confirm_report(employee_id: int, report_id: str) -> dict:
    with db.tx() as t:
        r = t.one("""SELECT g.report_id, g.roadmap_id, g.project_id FROM public.growth_reports g JOIN public.projects p ON p.project_id = g.project_id
                     WHERE g.report_id = CAST(:i AS uuid) AND p.employee_id = :e""", i=report_id, e=employee_id)
        if not r:
            raise not_found('결과 보고서')
        t.run('INSERT INTO app_ext.report_meta(report_id, confirmed, confirmed_at) VALUES(:i, true, now()) ON CONFLICT (report_id) DO UPDATE SET confirmed = true, confirmed_at = now()',
              i=r['report_id'])
        t.run("UPDATE public.projects SET status = 'COMPLETED', updated_at = now() WHERE project_id = :p AND status <> 'COMPLETED'", p=r['project_id'])
        t.run('UPDATE app_ext.roadmap_meta SET done_at = coalesce(done_at, now()) WHERE roadmap_id = :r', r=r['roadmap_id'])
        t.run("UPDATE app_ext.roadmap_revisions SET status = 'discarded', updated_at = now() WHERE roadmap_id = :r AND status IN ('running', 'ready', 'failed')", r=r['roadmap_id'])
    return {'planStatus': 'done', 'planId': str(r['roadmap_id'])}


# ── 부서장 (API-55~59) ──
def team_members(head_id: int) -> dict:
    me = profile.view(head_id)
    ids = profile.member_ids(head_id)
    rows = profile._rows()
    out = []
    for r in rows:
        if r['employee_id'] not in ids:
            continue
        v = profile.view(r['employee_id'], rows)
        recs = records(r['employee_id'], for_mgr=True)
        reps = reports(r['employee_id'])
        act = [x for x in recs.values() if x['status'] == 'active']
        out.append({'user': profile.team_view(v), 'activePlans': len(act), 'pastPlans': len(recs) - len(act), 'reports': len(reps),
                    'unreadComments': sum(1 for x in act for c in x['comments'] if c['status'] == 'new')})
    return {'group': me.get('supGroup'), 'members': out}


def member_state(head_id: int, member_id: int) -> dict:
    if member_id not in profile.member_ids(head_id):
        raise forbidden('소속 직원이 아니에요')
    recs = records(member_id, for_mgr=True)
    return {'user': profile.team_view(profile.view(member_id)), 'plans': recs, 'reports': reports(member_id, for_mgr=True), 'res': resources_of(recs), 'reg': reg_of(recs)}

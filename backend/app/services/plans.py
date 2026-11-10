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
from datetime import date, timedelta

from .. import catalog, course_time, db, jobs, regstore
from ..agents import deepcheck as DC
from ..agents import diag as DG
from ..agents import regulation as REG
from ..agents import roadmap as RM
from ..agents import runtime as rt
from ..agents.demo import D, course_id, course_name
from ..errors import AgentError, ApiError, forbidden, not_found
from ..free_track import validate_free_plan
from . import notifications as NT
from . import profile

STATUS = {'IN_PROGRESS': 'active', 'COMPLETED': 'done', 'ARCHIVED': 'archived'}
STATUS_DB = {v: k for k, v in STATUS.items()}
# 진행 중인 로드맵이 있을 때 새 로드맵을 확정하는 방식(API-35): 함께 진행 · 끝난 다음 주부터 · 보관하고 이번 주부터
START_MODES = ('together', 'after', 'archive')


def today() -> str:
    return date.today().isoformat()


def _is_book(resource: dict | None) -> bool:
    return bool(resource) and (resource.get('type') == 'book' or resource.get('kind') == '도서')


def tracked_acts(plan: dict) -> list[dict]:
    """완료 여부를 세는 활동. 도서는 진행 상태를 기록하지 않는 참고 자료라 뺀다."""
    acts = plan['acts']
    if not any(a.get('res') for a in acts):
        return acts  # 과제만 있으면 자료 목록을 읽지 않는다
    items = catalog.items()
    return [a for a in acts if not _is_book(items.get(a.get('res') or ''))]


def _d(v) -> str | None:
    return v.strftime('%Y-%m-%d') if v else None


# ── 확정 (drafts.confirm 이 부름) ──
def _write_steps(t: db.Tx, roadmap_id: str, plan: dict) -> None:
    items = catalog.items(refresh=plan.get('opt') == 'A1')
    done = {r['activity_id'] for r in t.all("SELECT activity_id FROM app_ext.activity_progress WHERE roadmap_id = CAST(:r AS uuid) AND status = 'done'", r=roadmap_id)}
    t.run('DELETE FROM public.roadmap_steps WHERE roadmap_id = CAST(:r AS uuid)', r=roadmap_id)
    for i, a in enumerate(plan['acts'], 1):
        res = items.get(a.get('res') or '')
        sid = t.val("""INSERT INTO public.roadmap_steps(roadmap_id, step_order, title, activity, estimated_duration, estimated_cost, is_completed, details)
                       VALUES(CAST(:r AS uuid), :o, :t, :a, :du, :c, :done, :d) RETURNING step_id""",
                    r=roadmap_id, o=i, t=a['title'], a=a.get('how') or (res['title'] if res else None), du=f"{course_time.display_hours(a['hours'])} · {a['wFrom']}~{a['wTo']}주차",
                    c=0 if plan.get('opt') == 'A1' and a.get('res') else res['cost'] if res and res['cost'] is not None else None, done=a['id'] in done,
                    d=db.J({k: a.get(k) for k in ('id', 'stage', 'res', 'task', 'hours', 'wFrom', 'wTo', 'skills', 'skill',
                                                'hoursEstimated', 'hoursBasis', 'timeStatus', 'hoursAllocation', 'catalogHours')}))
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
    return db.all_("""SELECT r.roadmap_id, r.project_id, r.content, r.created_at, r.diagnostic_round_id,
                         CASE WHEN report.created_at IS NOT NULL THEN 'COMPLETED' ELSE p.status::text END AS status,
                         p.employee_id, m.version, coalesce(m.done_at, report.created_at) AS done_at, m.archived_at, m.resumed_at
                      FROM public.roadmaps r JOIN public.projects p ON p.project_id = r.project_id
                      LEFT JOIN app_ext.roadmap_meta m ON m.roadmap_id = r.roadmap_id
                      LEFT JOIN LATERAL (
                        SELECT max(g.created_at) AS created_at FROM public.growth_reports g WHERE g.roadmap_id = r.roadmap_id AND g.report_type = 'PRE_POST'
                      ) report ON true
                      WHERE p.employee_id = :e AND p.status IN ('IN_PROGRESS', 'COMPLETED', 'ARCHIVED') AND r.content ? 'acts' AND r.content ? 'opt'
                        AND (CAST(:r AS uuid) IS NULL OR r.roadmap_id = CAST(:r AS uuid))
                      ORDER BY r.created_at""", e=employee_id, r=roadmap_id)


def active_rows(employee_id: int) -> list[dict]:
    return [row for row in _base_rows(employee_id) if STATUS.get(row['status']) == 'active']


def _start_day(row: dict) -> date:
    """1주차 첫날. 끝난 다음 주로 미룬 로드맵만 startDate 가 있고, 나머지는 확정한 날이다(화면 ganttCalc.planStart 와 같은 규칙)"""
    return date.fromisoformat(row['content'].get('startDate') or _d(row['created_at']))


def _plan_weeks(plan: dict) -> int:
    return max([1, plan.get('weeks') or 0, *[a.get('wTo') or 0 for a in plan['acts']]])


def next_start(rows: list[dict]) -> str | None:
    """로드맵들이 모두 끝난 다음 주의 첫날. 주차는 시작일부터 7일씩 세므로 마지막 주차 다음 날이고, 오늘 이전이면 미루지 않는다(None)"""
    if not rows:
        return None
    day = max(_start_day(row) + timedelta(weeks=_plan_weeks(row['content'])) for row in rows).isoformat()
    return day if day > today() else None


def _comments(roadmap_id: str) -> list[dict]:
    rows = db.all_("""SELECT c.comment_id, c.created_at, c.updated_at, c.body, e.name, e.employee_number, m.fit, m.fit_text, m.level, m.level_text, m.free_text, m.status, m.read_at, m.applied_version
                      FROM public.roadmap_comments c JOIN public.employees e ON e.employee_id = c.author_employee_id
                      LEFT JOIN app_ext.comment_meta m ON m.comment_id = c.comment_id WHERE c.roadmap_id = CAST(:r AS uuid) ORDER BY c.created_at""", r=roadmap_id)
    # 수정 여부: 팀 DB 트리거(guard_roadmap_comment)가 작성·본문 수정 때만 updated_at 을 now() 로 쓴다(작성 때는 created_at 과 같음). 이전 내용은 남기지 않는다(10/23 사용자 결정)
    return [{'id': str(c['comment_id']), 'by': c['name'], 'byCode': c['employee_number'], 'fit': c['fit'] or 'none', 'fitText': c['fit_text'] or '',
             'level': c['level'] or 'none', 'levelText': c['level_text'] or '', 'free': c['free_text'] if c['fit'] else c['body'], 'at': _d(c['created_at']),
             'editedAt': _d(c['updated_at']) if c['updated_at'] > c['created_at'] else None, 'stamp': c['updated_at'].isoformat(),
             'status': c['status'] or 'new', 'readAt': _d(c['read_at']), 'appliedVersion': c['applied_version'],
             **({'skill': skill} if (skill := _comment_skill(c['body'])) else {}),
             **({'deleted': True, 'fit': 'none', 'free': '', 'editedAt': None} if c['fit'] == '__deleted__' else {})} for c in rows]


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
    from .post_quiz import public_assessment
    post_survey=(pc.get('deep') or {}).get('v2Quiz')
    public_survey=public_assessment({'v2':{'survey':post_survey}})['v2']['survey'] if post_survey else None
    return {'quizSurvey': public_survey, 'quizAnswers': (pc.get('deep') or {}).get('v2Answers') or {}, 'answers': ans, 'goalSelf': str(pc['goal_self']) if pc.get('goal_self') else '', 'file': pc.get('attachment'), 'running': bool(pc.get('running')),
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
                 ON CONFLICT (roadmap_id) DO UPDATE SET deep = (coalesce(app_ext.post_checks.deep, '{}'::jsonb) - ARRAY['status','jobId','fail','quiz','notes','mcq','essay']) || EXCLUDED.deep, updated_at = now()""", r=row['roadmap_id'], d=db.J({'status': 'run', 'jobId': None}))

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        try:
            out = DG.post_deep(ctx, inp)
            if not out.get('deep'):
                raise AgentError('사후 심화 질문이 비어 있어요', ctx.provider)
        except AgentError as e:
            with db.tx() as t:
                t.run("UPDATE app_ext.post_checks SET deep = (coalesce(deep, '{}'::jsonb) - ARRAY['status','jobId','fail','quiz','notes','mcq','essay']) || :d, updated_at = now() WHERE roadmap_id = :r", d=db.J({'status': 'fail', 'fail': {'cause': e.info}}), r=row['roadmap_id'])
            raise
        with db.tx() as t:
            t.run("UPDATE app_ext.post_checks SET deep = (coalesce(deep, '{}'::jsonb) - ARRAY['status','jobId','fail','quiz','notes','mcq','essay']) || :d, updated_at = now() WHERE roadmap_id = :r",
                  d=db.J({'status': 'ready', 'quiz': out['deep'], 'notes': out.get('notes') or [], 'mcq': {}, 'essay': {}}), r=row['roadmap_id'])
        return {'ok': True}
    work._resume = {'operation':'plans.post_deep_start','kwargs':{'employee_id':employee_id,'roadmap_id':roadmap_id}}
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
    if STATUS.get(row['status']) == 'active' and (plan.get('def') or {}).get('materialSchedule'):
        from .duration_proposals import apply_plan_schedule
        plan = apply_plan_schedule(plan)
    versions = [dict(v['plan'], rid=rid) for v in db.all_('SELECT plan FROM app_ext.roadmap_versions WHERE roadmap_id = :r ORDER BY version', r=row['roadmap_id'])] or [plan]
    for snapshot in [plan, *versions]:
        definition = snapshot.get('def') or {}
        report = definition.get('learningReport') or {}
        recs = report.get('recommendations') or {}
        if recs.get('skills'):
            skills = [dict(skill, books=catalog.refresh_book_links(skill.get('books') or []),
                           courses=catalog.refresh_course_levels(skill.get('courses') or [])) for skill in recs['skills']]
            snapshot['def'] = dict(definition, learningReport=dict(report, recommendations=dict(recs, skills=skills)))
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
    from .post_quiz import public_assessment
    for version in [rec['plan']]+rec['versions']:
        if version.get('assess'):version['assess']=public_assessment(version['assess'])
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


MGR_HIDDEN = ('deep', 'goalSelf', 'file', 'executionSnapshot', 'postQuizDetails')


def reports(employee_id: int, for_mgr: bool = False) -> list[dict]:
    from .post_quiz import report_details

    details_sql = "" if for_mgr else ", CASE WHEN pc.updated_at <= g.created_at THEN pc.deep END AS saved_post_check"
    details_join = "" if for_mgr else "LEFT JOIN app_ext.post_checks pc ON pc.roadmap_id = g.roadmap_id"
    rows = db.all_(f"""SELECT g.report_id, g.roadmap_id, g.report_content, g.created_at, coalesce(m.confirmed, false) AS confirmed
                       {details_sql}
                      FROM public.growth_reports g JOIN public.projects p ON p.project_id = g.project_id LEFT JOIN app_ext.report_meta m ON m.report_id = g.report_id
                       {details_join}
                      WHERE p.employee_id = :e AND g.report_content ? 'gained' ORDER BY g.created_at DESC""", e=employee_id)
    out = []
    for r in rows:
        # 수준값은 화면에 보내지 않는다. 부서장 화면에는 심화 질문 결과(10/23)와 사후 점검 원본 응답·첨부(목표 달성 답·결과물 파일 · PR #23 리뷰)를 빼고 보낸다
        c = {k: v for k, v in r['report_content'].items() if k != 'hidden' and not (for_mgr and k in (*MGR_HIDDEN,'quizEvidence','surveyEvidence'))}
        # 이전 보고서는 opt 에 Track 이름이 저장돼 있어 코스 ID로 대응시킨다(#78)
        if not for_mgr and not c.get('postQuizDetails'):
            saved = r.get('saved_post_check') or {}
            details = report_details(saved.get('v2Quiz'), saved.get('v2Answers') or {})
            if details:
                c['postQuizDetails'] = details
        c.update(id=str(r['report_id']), planId=str(r['roadmap_id']), opt=course_id(c.get('opt')), confirmed=bool(r['confirmed']), createdAt=_d(r['created_at']))
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
    from .post_quiz import prepare as prepare_post_quiz
    for r in recs.values():
        if r.get('status') == 'active' and not (r.get('post') or {}).get('quizSurvey'):
            prepare_post_quiz(employee_id, r['id'], r['plan'])
    reps = reports(employee_id)
    return {'plans': recs, 'reports': reps, 'res': resources_of(recs), 'reg': reg_of(recs)}


# ── 진행 기록 (API-38) ──
def save_progress(employee_id: int, roadmap_id: str, act_id: str, body: dict) -> dict:
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵만 기록할 수 있어요')
    activity = next((a for a in row['content']['acts'] if a['id'] == act_id), None)
    if activity is None:
        raise not_found('활동')
    st = body.get('status') if body.get('status') in ('doing', 'done') else 'doing'
    completing_task = st == 'done' and activity.get('task') and activity.get('skill')
    resources = catalog.items() if activity.get('res') or completing_task else {}
    resource = resources.get(activity.get('res'))
    required_courses = {
        a['id'] for a in row['content']['acts']
        if not a.get('task') and a.get('skill') == activity['skill']
        and (resources.get(a.get('res'), {}).get('type') == 'course'
             or resources.get(a.get('res'), {}).get('kind') == '강좌')
    } if completing_task else set()
    shared = bool(resource and (resource.get('type') == 'course' or resource.get('kind') == '강좌') and not activity.get('task'))
    targets = [a['id'] for a in row['content']['acts'] if a['id'] == act_id or
               (shared and a.get('res') == activity.get('res') and not a.get('task'))]
    with db.tx() as t:
        if required_courses:
            done = {p['activity_id'] for p in t.all(
                "SELECT activity_id FROM app_ext.activity_progress WHERE roadmap_id = CAST(:r AS uuid) AND status = 'done'",
                r=roadmap_id)}
            if required_courses - done:
                raise ApiError(409, 'PREREQUISITE_COURSE_INCOMPLETE', '같은 스킬의 강좌를 먼저 완료해 주세요.')
        for target in targets:
            old = t.one('SELECT memo, attachment FROM app_ext.activity_progress WHERE roadmap_id = CAST(:r AS uuid) AND activity_id = :a', r=roadmap_id, a=target) or {}
            # Share status only; other skills keep their own notes and attachments.
            own = target == act_id
            memo = body['memo'] if own and 'memo' in body and body['memo'] is not None else old.get('memo')
            att = body['file'] if own and 'file' in body else old.get('attachment')
            t.run("""INSERT INTO app_ext.activity_progress(roadmap_id, activity_id, status, memo, attachment) VALUES(CAST(:r AS uuid), :a, :s, :m, :f)
                     ON CONFLICT (roadmap_id, activity_id) DO UPDATE SET status = EXCLUDED.status, memo = EXCLUDED.memo, attachment = EXCLUDED.attachment, updated_at = now()""",
                  r=roadmap_id, a=target, s=st, m=memo or '', f=db.J(att) if att else None)
            t.run("UPDATE public.roadmap_steps SET is_completed = :d WHERE roadmap_id = CAST(:r AS uuid) AND details->>'id' = :a", d=st == 'done', r=roadmap_id, a=target)
    return record(_owned(employee_id, roadmap_id))


# ── 보관·다시 진행 (API-41·42) ──
def archive_row(t: db.Tx, row: dict) -> bool:
    """진행 중일 때만 보관하고 보관했는지 돌려준다. row 를 읽은 뒤 다른 요청이 로드맵을 마쳤으면 완료 상태를 덮어쓰지 않도록 조건부로 갱신한다"""
    if not t.run("UPDATE public.projects SET status = 'ARCHIVED', updated_at = now() WHERE project_id = :p AND status = 'IN_PROGRESS'", p=row['project_id']):
        return False
    t.run('UPDATE app_ext.roadmap_meta SET archived_at = now() WHERE roadmap_id = :r', r=row['roadmap_id'])
    t.run("UPDATE app_ext.roadmap_revisions SET status = 'discarded', updated_at = now() WHERE roadmap_id = :r AND status IN ('running', 'ready', 'failed')", r=row['roadmap_id'])
    return True


def archive(employee_id: int, roadmap_id: str) -> dict:
    not_active = ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵만 보관할 수 있어요')
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise not_active
    with db.tx() as t:
        if not archive_row(t, row):
            raise not_active
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


def _skill_comment_option(out: dict, base: dict, targets: dict, skill: str, handoff: dict) -> dict:
    from app.llm import LlmError
    from .material_plan import rebuild_revision
    old_ids = {a.get('res') for a in base['acts'] if a.get('skill') == skill}
    old_tasks = {(a['title'], a.get('how') or '') for a in base['acts'] if a.get('skill') == skill and not a.get('res')}
    proposals = [a for a in out['acts'] if a.get('skill') == skill]
    courses = [a for a in proposals if a.get('res') and a['res'] not in old_ids
               and (RM._res(a['res']) or {}).get('type') == 'course']
    tasks = [a for a in proposals if not a.get('res') and (a['title'], a.get('how') or '') not in old_tasks]
    if len(courses) != 1 or len(tasks) != 1:
        raise ApiError(422, 'SKILL_REVISION_INVALID', '이 스킬의 새 강좌와 산출물을 하나씩 확인하지 못했어요. 다시 요청해 주세요.')
    replacement = {targets['course']['id']: courses[0], targets['task']['id']: tasks[0]}
    option = copy.deepcopy(base['def'])
    option.pop('support', None)
    option.pop('supportFail', None)
    option['acts'] = [
        dict(replacement[act['id']], key=None, skill=skill, stage=act['stage'])
        if act['id'] in replacement else dict(act, key=act['id'])
        for act in base['acts']
    ]
    option['summary'] = out.get('summary')
    option['notes'] = out.get('notes')
    try:
        return rebuild_revision(option, base, handoff)
    except LlmError as error:
        raise ApiError(422, 'SKILL_REVISION_INVALID', str(error)) from error


def revise_start(employee_id: int, roadmap_id: str, body: dict) -> dict:
    """수정안 작성(API-43). 확정하기 전까지 기존 로드맵은 그대로. 실패하면 가데이터로 대신하지 않는다"""
    from .drafts import handoff_prefs
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row['status']) != 'active':
        raise ApiError(409, 'NOT_ACTIVE', '진행 중인 로드맵만 고칠 수 있어요')
    base = row['content']
    retry_skill = body.get('retrySkill')
    retry = None
    if retry_skill is not None:
        if not isinstance(retry_skill, str) or retry_skill not in ((base.get('def') or {}).get('learningReport') or {}).get('skillOrder', []):
            raise ApiError(422, 'REVISION_SKILLS_INVALID', '다시 제안받을 스킬을 확인해 주세요.')
        retry = _revision(str(row['roadmap_id']))
        pending = (retry or {}).get('result') or {}
        if not retry or retry['status'] != 'ready' or str(retry['revision_id']) != body.get('revisionId') or pending.get('fromComment') or pending.get('from') != base:
            raise ApiError(409, 'REVISION_CHANGED', '현재 수정안을 다시 확인해 주세요.')
    rev = body.get('rev') or {}
    comment = next((c for c in _comments(roadmap_id) if c['id'] == rev['fromComment']), None) if rev.get('fromComment') else None
    if rev.get('fromComment') and not comment:
        raise not_found('코멘트')
    skill = (comment or {}).get('skill')
    if comment and (comment.get('deleted') or comment.get('status') == 'applied'):
        raise ApiError(409, 'COMMENT_UNAVAILABLE', '이미 반영했거나 삭제된 코멘트예요.')
    if skill:
        rev = dict(rev, on={})
    ch = _rev_changes(rev, base)
    prefs_h = handoff_prefs(ch['raw'])
    previous_handoff = dict(base.get('handoff') or {})
    if 'userNotes' not in previous_handoff and 'etc' not in (previous_handoff.get('details') or {}):
        legacy_note = str((base.get('prefs') or {}).get('etc') or '').strip()
        if legacy_note:
            previous_handoff['userNotes'] = [legacy_note]
    handoff = dict(previous_handoff, prefs=prefs_h, startStage=ch['start'])
    if 'constraints' in ch['c']:
        constraint = str(ch['raw'].get('etc') or '').strip()
        handoff.update(userNotes=[constraint] if constraint else [],
                       details={**(previous_handoff.get('details') or {}), 'etc': constraint})
    req = str(rev.get('note') or '').strip()
    done = {p['activity_id'] for p in db.all_("SELECT activity_id FROM app_ext.activity_progress WHERE roadmap_id = :r AND status = 'done'", r=row['roadmap_id'])}
    targets = {}
    if skill:
        for activity in base['acts']:
            if activity.get('skill') != skill or activity['id'] in done:
                continue
            resource = activity.get('res')
            if not resource:
                targets.setdefault('task', activity)
            elif (RM._res(resource) or {}).get('type') == 'course':
                targets.setdefault('course', activity)
        if len(targets) != 2:
            raise ApiError(422, 'SKILL_REVISION_TARGET', '이 스킬에 교체 가능한 미완료 강좌와 산출물이 각각 필요해요.')
        ch['c']['replaceActs'] = [{'key': a['id'], 'title': a['title']} for a in targets.values()]
        ch['c']['replaceHint'] = f'{skill}의 지정 강좌 1개와 산출물 1개 교체. 강좌는 실제 카탈로그의 다른 강좌. 그 외 활동 유지.'
        feedback = ' / '.join(comment.get(key) or '' for key in ('fit', 'fitText', 'level', 'levelText', 'free')).strip(' /')
        req = f'{skill} 담당 부서장 의견: {feedback}\n{req}'.strip()
    if (base.get('def') or {}).get('learningReport') and (skill or not rev.get('fromComment')):
        req = (req + '\n도서 유지. 새 산출물 설명 형식: 만들 것:, 필수 항목:, 제출물:, 평가 기준:. 각 항목 내용 필수.').strip()
    if retry:
        req = (req + f'\n재요청 대상 스킬: {retry_skill}. 이 스킬의 강좌와 산출물만 새로 제안. 다른 스킬과 도서, 완료 활동 유지.').strip()
    inp = {'pid': ch['pid'], 'handoff': handoff,
           'changes': ch['c'], 'request': req or None, 'fromComment': rev.get('fromComment') or False,
           'plan': {k: base.get(k) for k in ('opt', 'name', 'tagline', 'def', 'hours', 'start')} | {'acts': [dict(a, done=a['id'] in done) for a in base['acts']]}}
    if retry:
        rev_id = str(retry['revision_id'])
    else:
        with db.tx() as t:
            t.run("UPDATE app_ext.roadmap_revisions SET status = 'discarded', updated_at = now() WHERE roadmap_id = :r AND status IN ('running', 'ready', 'failed')", r=row['roadmap_id'])
            rev_id = str(t.val("INSERT INTO app_ext.roadmap_revisions(roadmap_id, request, status) VALUES(:r, :q, 'running') RETURNING revision_id",
                               r=row['roadmap_id'], q=db.J(dict(rev, key=body.get('key')))))

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        try:
            out = RM.revise(ctx, inp, sim=rt.sim_once(ctx, 'rev', str(body.get('key') or rev_id)))
            if skill:
                out = _skill_comment_option(out, base, targets, skill, handoff)
        except (AgentError, ApiError) as error:
            with db.tx() as t:
                t.run("UPDATE app_ext.roadmap_revisions SET status = 'failed', error = :e, updated_at = now() WHERE revision_id = CAST(:i AS uuid) AND status = 'running'",
                      e=db.J({'cause': jobs.error_info(error)}), i=rev_id)
            raise
        d = RM.keep_ids(out, base, base['version'] + 1)
        if retry:
            existing_ids = {activity['id'] for activity in base['acts']}
            for activity in d['acts']:
                if activity.get('skill') == retry_skill and activity['id'] not in existing_ids:
                    activity['id'] = 'retry-' + uuid.uuid4().hex
        if skill:
            # 교체된 산출물에는 이전 완료 기록을 연결하지 않는다.
            for index, activity in enumerate(d['acts']):
                if activity['id'] == targets['task']['id']:
                    activity['id'] = f"{base['opt'].lower()}-v{base['version'] + 1}-task-{index + 1}"
        to = RM.build_plan(d, {'start': ch['start'], 'hours': base['hours'] if skill else prefs_h['weeklyHours'] or d.get('weeklyHours') or base['hours'] or D['autoHours'], 'format': prefs_h['formatKey'], 'patch': {}}, base['goal'])
        if retry:
            pending = retry['result']
            updated = _mix_revision_skills(pending['to'], to, handoff, [retry_skill], done)
            with db.tx() as t:
                changed = t.run("""UPDATE app_ext.roadmap_revisions SET result = :result, updated_at = now()
                                   WHERE revision_id = CAST(:i AS uuid) AND status = 'ready' AND result = CAST(:previous AS jsonb)""",
                                i=rev_id, result=db.J(dict(pending, to=updated)), previous=db.J(pending))
                if not changed:
                    raise ApiError(409, 'REVISION_CHANGED', '수정안이 변경됐어요. 다시 확인해 주세요.')
            return {'revisionId': rev_id}
        summary = str(out.get('summary') or '').strip()
        pd = {'from': base, 'to': to, 'key': body.get('key'), 'request': req, 'fromComment': rev.get('fromComment') or False, 'summary': summary, 'notes': out.get('notes') or [],
              'source': d.get('source'), 'prefsFrom': base.get('prefs'), 'prefsTo': ch['raw'], 'handoff': handoff,
              'label': f"{'부서장 코멘트 반영' if rev.get('fromComment') else '수정 요청 반영'}{' · ' + summary if summary else ''}"[:70]}
        if skill:
            pd['skillComment'] = {'stamp': comment['stamp'], 'targets': [a['id'] for a in targets.values()]}
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
    work._resume = {'operation':'plans.revise_start','kwargs':{'employee_id':employee_id,'roadmap_id':roadmap_id,'body':body}}
    jid = jobs.start('revision', employee_id, roadmap_id, work)
    if retry:
        return {'revisionId': rev_id, 'jobId': jid}
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
    work._resume = {'operation':'plans.revision_support','kwargs':{'employee_id':employee_id,'roadmap_id':roadmap_id,'rev_id':rev_id}}
    return jobs.start('revision-support', employee_id, roadmap_id, work)


def _patch_current_support(roadmap_id: str, support: dict) -> None:
    with db.tx() as t:
        row = t.one('SELECT content FROM public.roadmaps WHERE roadmap_id = CAST(:r AS uuid) FOR UPDATE', r=roadmap_id)
        content = row['content']
        content.setdefault('def', {})['support'] = support
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


def _mix_revision_skills(current: dict, proposal: dict, handoff: dict, selected: list[str], done: set[str]) -> dict:
    from app.llm import LlmError
    from .material_plan import rebuild_revision
    old_report = (current.get('def') or {}).get('learningReport') or {}
    new_report = (proposal.get('def') or {}).get('learningReport') or {}
    old_names = old_report.get('skillOrder') or []
    new_names = set(new_report.get('skillOrder') or [])
    if (not isinstance(selected, list) or not selected
            or any(not isinstance(name, str) or name not in old_names or name not in new_names for name in selected)
            or len(set(selected)) != len(selected) or current['opt'] != proposal['opt']):
        raise ApiError(422, 'REVISION_SKILLS_INVALID', '확정할 스킬 선택을 다시 확인해 주세요.')
    chosen = set(selected)
    activities = []
    for name in old_names:
        old = [a for a in current['acts'] if a.get('skill') == name]
        book_ids = set((old_report.get('choices', {}).get(name) or {}).get('books') or [])
        book_ids.update((new_report.get('choices', {}).get(name) or {}).get('books') or [])
        new = old
        if name in chosen:
            new = [a for a in proposal['acts'] if a.get('skill') == name and a.get('res') not in book_ids]
            if not new:
                raise ApiError(422, 'REVISION_SKILLS_INVALID', '추천 활동이 없는 스킬은 기존 계획을 유지해 주세요.')
            for index, activity in enumerate(old):
                if activity.get('res') in book_ids:
                    new.insert(index, activity)
        old_by_id = {a['id']: a for a in old}
        new_by_id = {a['id']: a for a in new}
        if any(a['id'] in done and (
            a['id'] not in new_by_id or any(new_by_id[a['id']].get(key) != a.get(key) for key in ('res', 'title', 'how'))
        ) for a in old):
            raise ApiError(409, 'REVISION_CHANGED', '완료한 활동은 바꿀 수 없어요. 기존 안을 선택해 주세요.')
        activities.extend(dict(a, key=a['id'] if a['id'] in old_by_id else None) for a in new)
    activities.extend(dict(a, key=a['id']) for a in current['acts'] if a.get('skill') not in old_names)
    if len({a['id'] for a in activities}) != len(activities):
        raise ApiError(422, 'REVISION_SKILLS_INVALID', '추천 활동이 겹쳐요. 수정안을 다시 만들어 주세요.')
    option = copy.deepcopy(current['def'])
    option['acts'] = activities
    option.pop('support', None)
    option.pop('supportFail', None)
    try:
        option = rebuild_revision(option, current, handoff)
    except LlmError as error:
        raise ApiError(422, 'REVISION_SKILLS_INVALID', str(error)) from error
    for a in option['acts']:
        a.pop('key', None)
    result = RM.build_plan(option, {'start': current['start'], 'hours': current['hours'], 'format': current.get('format')}, current['goal'])
    if RM.sup_sig(result) == RM.sup_sig(current) and current['def'].get('support'):
        result['def']['support'] = copy.deepcopy(current['def']['support'])
    return result


def accept_revision(employee_id: int, roadmap_id: str, revision_id: str, selected_skills: list[str] | None = None) -> dict:
    row = _owned(employee_id, roadmap_id)
    with db.tx() as t:
        rv = t.one("SELECT result, status FROM app_ext.roadmap_revisions WHERE revision_id = CAST(:i AS uuid) AND roadmap_id = :r FOR UPDATE", i=revision_id, r=row['roadmap_id'])
        if not rv or rv['status'] != 'ready':
            raise ApiError(409, 'NO_REVISION', '확정할 수정안이 없어요')
        pd, cur = rv['result'], row['content']
        if selected_skills is not None:
            if pd.get('fromComment'):
                raise ApiError(422, 'REVISION_SKILLS_INVALID', '코멘트 수정안은 기존 확정 방식을 사용해 주세요.')
            current_row = t.one('SELECT content FROM public.roadmaps WHERE roadmap_id = :r FOR UPDATE', r=row['roadmap_id'])
            if not current_row or current_row['content'] != pd['from']:
                raise ApiError(409, 'REVISION_CHANGED', '로드맵이 바뀌었어요. 수정안을 다시 요청해 주세요.')
            cur = current_row['content']
            done = {item['activity_id'] for item in t.all(
                "SELECT activity_id FROM app_ext.activity_progress WHERE roadmap_id = :r AND status = 'done'", r=row['roadmap_id'])}
            handoff = cur.get('handoff') or pd['handoff']
            pd = dict(pd, to=_mix_revision_skills(cur, pd['to'], handoff, selected_skills, done),
                      prefsTo=cur.get('prefs'), handoff=handoff)

        changed = pd['to']['opt'] != cur['opt']
        from .drafts import selection_of
        plan = dict(pd['to'], version=cur['version'] + 1, confirmedAt=today(), why=pd['label'], assess=cur.get('assess'), prefs=pd['prefsTo'], handoff=pd['handoff'],
                    selection=selection_of(pd['to']['def']) if changed else cur.get('selection'))
        # 끝난 다음 주로 미룬 시작일은 수정안을 확정해도 그대로다. 수정안 내용(pd['to'])에는 시작일이 없다
        if cur.get('startDate'):
            plan['startDate'] = cur['startDate']
        # 최초 확정 근거는 수정 모델의 결과로 교체하거나 새로 만들지 않는다.
        baseline_row = t.one('SELECT baseline_content FROM public.roadmaps WHERE roadmap_id = :r FOR UPDATE', r=row['roadmap_id']) or {}
        baseline = baseline_row.get('baseline_content') or {}
        scoped = pd.get('skillComment')
        if scoped:
            source = t.one("""SELECT c.updated_at, m.fit, m.status
                               FROM public.roadmap_comments c LEFT JOIN app_ext.comment_meta m USING (comment_id)
                               WHERE c.comment_id = CAST(:c AS uuid) AND c.roadmap_id = :r FOR UPDATE OF c""",
                           c=pd['fromComment'], r=row['roadmap_id'])
            if (not source or source['fit'] == '__deleted__' or source['status'] == 'applied'
                    or source['updated_at'].isoformat() != scoped['stamp']):
                raise ApiError(409, 'COMMENT_UNAVAILABLE', '코멘트가 변경됐어요. 수정안을 다시 요청해 주세요.')
            current = t.val('SELECT content FROM public.roadmaps WHERE roadmap_id = :r', r=row['roadmap_id'])
            if current != pd['from']:
                raise ApiError(409, 'REVISION_CHANGED', '로드맵이 변경됐어요. 수정안을 다시 요청해 주세요.')
            done_ids = {item['activity_id'] for item in t.all(
                "SELECT activity_id FROM app_ext.activity_progress WHERE roadmap_id = :r AND status = 'done'",
                r=row['roadmap_id'])}
            if done_ids.intersection(scoped['targets']):
                raise ApiError(409, 'REVISION_CHANGED', '완료한 활동이 있어요. 수정안을 다시 요청해 주세요.')
        evidence = baseline.get('selectionEvidence') if isinstance(baseline, dict) else None
        if not isinstance(evidence, dict):
            evidence = cur.get('selectionEvidence')
        plan.pop('selectionEvidence', None)
        if isinstance(evidence, dict):
            plan['selectionEvidence'] = copy.deepcopy(evidence)
        validate_free_plan(t, plan)
        # 로드맵 내용이 바뀌면 팀 DB 트리거가 코멘트에 '수정 완료' 시각만 적는다. 그 갱신은 작성자 검사 트리거(본문·작성자·로드맵 열)를 거치지 않는다
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


_COMMENT_SKILL_PREFIX = '대상 스킬: '


def _comment_skill(body: str | None) -> str:
    first = (body or '').split('\n', 1)[0]
    return first.removeprefix(_COMMENT_SKILL_PREFIX) if first.startswith(_COMMENT_SKILL_PREFIX) else ''


def _comment_body(fit: str, fit_text: str, level: str, level_text: str, free: str, skill: str = '') -> str:
    lb = lambda lst, v: next((l for x, l in lst if x == v), '의견 없음')  # noqa: E731
    lines = [f"업무 적합성: {lb(D['commentFit'], fit)}{' — ' + fit_text if fit_text else ''}", f"수준·기간·분량: {lb(D['commentLevel'], level)}{' — ' + level_text if level_text else ''}"]
    if free:
        lines.append(f'자유 의견: {free}')
    return '\n'.join([_COMMENT_SKILL_PREFIX + skill, *lines] if skill else lines)


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
    if not any(f.values()):
        raise ApiError(422, 'COMMENT_FIELDS', '보낼 의견을 입력해 주세요')
    f['fit'] = f['fit'] or 'none'
    f['level'] = f['level'] or 'none'
    if f['fit'] not in {x for x, _ in D['commentFit']} or f['level'] not in {x for x, _ in D['commentLevel']}:
        raise ApiError(422, 'COMMENT_FIELDS', '선택한 코멘트 항목을 확인해 주세요')
    return f


def send_comments(head_id: int, member_id: int, roadmap_id: str, bodies: list[dict]) -> list[str]:
    if not isinstance(bodies, list) or not 1 <= len(bodies) <= 100 or any(not isinstance(body, dict) for body in bodies):
        raise ApiError(422, 'COMMENT_FIELDS', '보낼 코멘트를 확인해 주세요')
    row = _comment_target(head_id, member_id, roadmap_id, '보낼')
    entries = []
    for body in bodies:
        skill = body.get('skill', '')
        if skill != '':
            plan = row['content']
            learning = (plan.get('def') or {}).get('learningReport') or {}
            choices = learning.get('choices') or {}
            if choices:
                allowed = {name for name, choice in choices.items() if choice.get('enabled') is not False}
            else:
                allowed = {entry.get('name') for entry in (plan.get('def') or {}).get('learningSkills') or []}
                for activity in plan.get('acts') or []:
                    allowed.add(activity.get('skill'))
                    allowed.update(activity.get('skills') or [])
            if not isinstance(skill, str) or '\n' in skill or '\r' in skill or skill not in allowed:
                raise ApiError(422, 'COMMENT_SKILL_INVALID', '이 로드맵의 스킬을 선택해 주세요')
        entries.append((skill, _comment_fields(body)))
    ids = []
    with db.tx() as t:
        # 시연 초기화가 먼저 끝났다면 이미 사라진 대상에 코멘트를 쓰지 않는다.
        t.lock_workspace(member_id)
        if not t.val('SELECT 1 FROM public.roadmaps WHERE roadmap_id = :r', r=row['roadmap_id']):
            raise not_found('로드맵')
        t.actor(head_id)
        for skill, f in entries:
            cid = str(t.val('INSERT INTO public.roadmap_comments(roadmap_id, author_employee_id, body) VALUES(:r, :a, :b) RETURNING comment_id', r=row['roadmap_id'], a=head_id,
                            b=_comment_body(f['fit'], f['fitText'], f['level'], f['levelText'], f['free'], skill)))
            t.run("""INSERT INTO app_ext.comment_meta(comment_id, fit, fit_text, level, level_text, free_text, status) VALUES(CAST(:c AS uuid), :f, :ft, :l, :lt, :fr, 'new')""",
                  c=cid, f=f['fit'], ft=f['fitText'], l=f['level'], lt=f['levelText'], fr=f['free'])
            ids.append(cid)
        NT.comment_sent(t, head_id, member_id, str(row['roadmap_id']), ids[0])
    return ids


def send_comment(head_id: int, member_id: int, roadmap_id: str, body: dict) -> str:
    return send_comments(head_id, member_id, roadmap_id, [body])[0]


def delete_comment(head_id: int, member_id: int, roadmap_id: str, comment_id: str) -> None:
    row = _comment_target(head_id, member_id, roadmap_id, '지울')
    with db.tx() as t:
        comment = t.one('SELECT author_employee_id FROM public.roadmap_comments WHERE comment_id = CAST(:c AS uuid) AND roadmap_id = :r FOR UPDATE',
                        c=comment_id, r=row['roadmap_id'])
        if not comment:
            raise not_found('코멘트')
        if comment['author_employee_id'] != head_id:
            raise forbidden('내가 보낸 코멘트만 지울 수 있어요')
        meta = t.one('SELECT fit, status FROM app_ext.comment_meta WHERE comment_id = CAST(:c AS uuid) FOR UPDATE', c=comment_id) or {}
        if meta.get('fit') == '__deleted__':
            return
        if meta.get('status') == 'applied':
            raise ApiError(409, 'COMMENT_APPLIED', '이미 로드맵에 반영한 코멘트는 지울 수 없어요')
        t.actor(head_id)
        t.run("UPDATE public.roadmap_comments SET body = CASE WHEN body LIKE '대상 스킬: %' THEN split_part(body, chr(10), 1) || chr(10) || '삭제된 코멘트' ELSE '삭제된 코멘트' END WHERE comment_id = CAST(:c AS uuid)", c=comment_id)
        # 기존 필드로 삭제 표시를 남기고 구조화된 본문을 비운다.
        t.run("""INSERT INTO app_ext.comment_meta(comment_id, fit, status) VALUES(CAST(:c AS uuid), '__deleted__', 'read')
                 ON CONFLICT (comment_id) DO UPDATE SET fit = '__deleted__', status = 'read',
                   fit_text = NULL, level = NULL, level_text = NULL, free_text = NULL""", c=comment_id)
        # 묶음의 대표 코멘트를 삭제해도 같은 전송에 남은 코멘트로 알림을 유지한다.
        t.run("""UPDATE app_ext.notifications n
                   SET comment_id = sibling.comment_id
                  FROM public.roadmap_comments removed
                  CROSS JOIN LATERAL (
                    SELECT c.comment_id FROM public.roadmap_comments c
                    LEFT JOIN app_ext.comment_meta m USING (comment_id)
                    WHERE c.roadmap_id = removed.roadmap_id
                      AND c.author_employee_id = removed.author_employee_id
                      AND c.created_at = removed.created_at AND c.comment_id <> removed.comment_id
                      AND m.fit IS DISTINCT FROM '__deleted__'
                    ORDER BY c.comment_id LIMIT 1
                  ) sibling
                 WHERE removed.comment_id = CAST(:c AS uuid) AND n.comment_id = removed.comment_id
                   AND n.read_at IS NULL""", c=comment_id)
        t.run("DELETE FROM app_ext.notifications WHERE comment_id = CAST(:c AS uuid) AND read_at IS NULL", c=comment_id)


def edit_comment(head_id: int, member_id: int, roadmap_id: str, comment_id: str, body: dict) -> bool:
    """보낸 코멘트 고치기.
    직원이 수정안으로 반영하기 전(새·확인함)까지만 고칠 수 있고, 고치면 직원에게 다시 '새 코멘트'로 보인다. 이전 내용은 남기지 않는다(덮어쓰기).
    바뀐 값이 없으면 저장하지 않고 False"""
    row = _comment_target(head_id, member_id, roadmap_id, '고칠')
    f = _comment_fields(body)
    with db.tx() as t:
        c = t.one('SELECT author_employee_id, body FROM public.roadmap_comments WHERE comment_id = CAST(:c AS uuid) AND roadmap_id = :r FOR UPDATE', c=comment_id, r=row['roadmap_id'])
        if not c:
            raise not_found('코멘트')
        if c['author_employee_id'] != head_id:
            raise forbidden('내가 보낸 코멘트만 고칠 수 있어요')
        # 직원의 수정안 확정(accept_revision)이 같은 행을 'applied' 로 바꾸므로 잠근 뒤 상태를 본다
        m = t.one('SELECT fit, fit_text, level, level_text, free_text, status FROM app_ext.comment_meta WHERE comment_id = CAST(:c AS uuid) FOR UPDATE', c=comment_id) or {}
        if m.get('fit') == '__deleted__':
            raise not_found('코멘트')
        if m.get('status') == 'applied':
            raise ApiError(409, 'COMMENT_APPLIED', '직원이 이미 로드맵에 반영한 코멘트라 고칠 수 없어요', '새 의견은 새 코멘트로 보내 주세요')
        if m and [m['fit'], m['fit_text'] or '', m['level'], m['level_text'] or '', m['free_text'] or ''] == [f['fit'], f['fitText'], f['level'], f['levelText'], f['free']]:
            return False
        t.actor(head_id)
        t.run('UPDATE public.roadmap_comments SET body = :b WHERE comment_id = CAST(:c AS uuid)', c=comment_id,
              b=_comment_body(f['fit'], f['fitText'], f['level'], f['levelText'], f['free'], _comment_skill(c.get('body'))))
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
    from .post_quiz import validate as validate_quiz
    quiz_answers=None
    if 'quizAnswers' in body:
        from .post_quiz import with_survey,questions
        stored=(db.one('SELECT deep FROM app_ext.post_checks WHERE roadmap_id = :r',r=row['roadmap_id']) or {}).get('deep') or {}
        if questions(row['content']) and not stored.get('v2Quiz'):raise ApiError(409,'POST_QUIZ_REQUIRED','사후 퀴즈를 먼저 생성해 주세요.')
        quiz_answers=validate_quiz(with_survey(row['content'],stored['v2Quiz']) if stored.get('v2Quiz') else row['content'],body['quizAnswers'])
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
        if quiz_answers is not None:
            t.run("UPDATE app_ext.post_checks SET deep = coalesce(deep, '{}'::jsonb) || jsonb_build_object('v2Answers', CAST(:answers AS jsonb)), updated_at = now() WHERE roadmap_id = :r",answers=db.J(quiz_answers),r=row['roadmap_id'])
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


def _finish_report_plan(t: db.Tx, project_id, roadmap_id) -> None:
    t.run("UPDATE public.projects SET status = 'COMPLETED', updated_at = now() WHERE project_id = :p AND status <> 'COMPLETED'", p=project_id)
    t.run('UPDATE app_ext.roadmap_meta SET done_at = coalesce(done_at, now()) WHERE roadmap_id = :r', r=roadmap_id)
    t.run("UPDATE app_ext.roadmap_revisions SET status = 'discarded', updated_at = now() WHERE roadmap_id = :r AND status IN ('running', 'ready', 'failed')", r=roadmap_id)


def report_start(employee_id: int, roadmap_id: str) -> str:
    row = _owned(employee_id, roadmap_id)
    if STATUS.get(row.get('status')) == 'done':
        raise ApiError(409, 'REPORT_COMPLETED', '종료된 로드맵의 결과 보고서는 다시 만들 수 없어요.')
    rec = record(row)
    pl, post = rec['plan'], rec['post']
    A = pl['assess']
    if not all(post['answers'].get(q['id']) for q in A['questions']) or not post['goalSelf']:
        raise ApiError(409, 'POST_INCOMPLETE', '사후 점검 문항과 목표 달성에 모두 답해 주세요')
    from .post_quiz import validate as validate_quiz, comparison as quiz_comparison, report_details
    from .post_quiz import with_survey,questions
    stored=(db.one('SELECT deep FROM app_ext.post_checks WHERE roadmap_id = :r',r=row['roadmap_id']) or {}).get('deep') or {}
    if questions(pl) and not stored.get('v2Quiz'):raise ApiError(409,'POST_QUIZ_REQUIRED','사후 퀴즈를 먼저 완료해 주세요.')
    validate_quiz(with_survey(pl,stored['v2Quiz']) if stored.get('v2Quiz') else pl,post.get('quizAnswers') or {},complete=True)
    quiz_evidence=quiz_comparison(row['content'],post.get('quizAnswers') or {},stored.get('v2Quiz'))
    items = [{'id': q['id'], 'area': q['area'], 'text': q['text'], 'skill': DG.skill_label(q.get('skill') or ''), 'pre': A['answers'].get(q['id']), 'post': post['answers'][q['id']]} for q in A['questions']]
    prog = rec['progress']
    from .report_snapshot import capture,evidence
    tracked = tracked_acts(pl)
    execution_snapshot=capture(dict(pl,acts=tracked),prog)
    done = [a for a in tracked if (prog.get(a['id']) or {}).get('status') == 'done']
    rest = [a for a in tracked if (prog.get(a['id']) or {}).get('status') != 'done']
    goal_self = D['goalSelf'][int(post['goalSelf']) - 1] if post['goalSelf'] else ''
    deep_inp = _report_deep(row, A)
    with db.tx() as t:
        if t.one('SELECT 1 FROM public.growth_reports g JOIN app_ext.report_meta m ON m.report_id = g.report_id WHERE g.roadmap_id = :r AND m.confirmed', r=row['roadmap_id']):
            raise ApiError(409, 'REPORT_CONFIRMED', '확인한 보고서가 있어 다시 만들 수 없어요')
        t.run('UPDATE app_ext.post_checks SET running = true, fail = NULL WHERE roadmap_id = :r', r=row['roadmap_id'])
    level_pre = (db.val('SELECT diagnostic_result FROM public.diagnostic_rounds WHERE diagnostic_round_id = :d', d=row['diagnostic_round_id']) or {}).get('level')

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        inp = {'goal': pl['goal'], 'planName': course_name(pl['opt'], pl['name']), 'opt': pl['opt'], 'domain': A.get('domain'), 'items': items, 'doneTitles': [a['title'] for a in done],
               'restTitles': [a['title'] for a in rest], 'total': len(tracked), 'goalSelf': goal_self}
        inp['executionEvidence']=evidence(execution_snapshot)
        if quiz_evidence:inp['quizEvidence']=quiz_evidence
        if deep_inp:
            inp['deep'] = deep_inp
        try:
            out = DG.report(ctx, inp, sim=rt.sim_once(ctx, 'report', json.dumps([roadmap_id, post['answers'], post.get('quizAnswers'), post['goalSelf']], sort_keys=True)))
        except AgentError as e:
            with db.tx() as t:
                t.run('UPDATE app_ext.post_checks SET running = false, fail = :f WHERE roadmap_id = :r', f=db.J({'cause': e.info}), r=row['roadmap_id'])
            raise
        r = {'planId': roadmap_id, 'version': pl['version'], 'goal': pl['goal'], 'opt': pl['opt'],
             'gained': [{'skill': x['skill'], 'from': x['pre'], 'to': x['post']} for x in items if DG.rose(x['pre'], x['post'])],
             'still': [{'skill': x['skill'], 'from': x['pre'], 'to': x['post']} for x in items if not DG.rose(x['pre'], x['post'])],
             'doneTitles': inp['doneTitles'], 'restTitles': inp['restTitles'], 'goalSelf': goal_self, 'file': post.get('file'),
             'good': out['good'], 'improve': out['improve'], 'next': out['next'],
             'hidden': {'pre': level_pre, 'post': DG.level_of(A['questions'], post['answers'])}}
        r['executionSnapshot']=execution_snapshot
        # 생성한 설명이 아니라 동일 문항 ID로 대응한 실제 응답을 보고서 시점에 보존한다.
        r['surveyEvidence']=[dict(item) for item in items]
        if quiz_evidence:r['quizEvidence']=quiz_evidence
        post_quiz_details = report_details(stored.get('v2Quiz'), post.get('quizAnswers') or {})
        if post_quiz_details:
            r['postQuizDetails'] = post_quiz_details
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
            t.run('INSERT INTO app_ext.report_meta(report_id, confirmed, confirmed_at) VALUES(CAST(:i AS uuid), true, now())', i=rep_id)
            t.run('UPDATE public.diagnostic_rounds SET post_completed_at = now() WHERE diagnostic_round_id = :d', d=row['diagnostic_round_id'])
            t.run('UPDATE app_ext.post_checks SET running = false, fail = NULL WHERE roadmap_id = :r', r=row['roadmap_id'])
            # 보고서 작성 완료 알림(#82): 본인·부서장. 위에서 지운 이전 보고서의 알림은 함께 지워졌다(report_id ON DELETE CASCADE)
            _finish_report_plan(t, row['project_id'], row['roadmap_id'])
            NT.report_created(t, employee_id, str(row['roadmap_id']), rep_id)
        return {'reportId': rep_id}
    work._resume = {'operation':'plans.report_start','kwargs':{'employee_id':employee_id,'roadmap_id':roadmap_id}}
    jid = jobs.start('report', employee_id, roadmap_id, work)
    with db.tx() as t:
        t.run('UPDATE app_ext.post_checks SET job_id = CAST(:j AS uuid) WHERE roadmap_id = :r', j=jid, r=row['roadmap_id'])
    return jid


def confirm_report(employee_id: int, report_id: str) -> dict:
    with db.tx() as t:
        r = t.one("""SELECT g.report_id, g.roadmap_id, g.project_id, g.report_content, rm.content FROM public.growth_reports g JOIN public.roadmaps rm ON rm.roadmap_id = g.roadmap_id JOIN public.projects p ON p.project_id = g.project_id
                     WHERE g.report_id = CAST(:i AS uuid) AND p.employee_id = :e""", i=report_id, e=employee_id)
        if not r:
            raise not_found('결과 보고서')
        snapshot=(r.get('report_content') or {}).get('executionSnapshot')
        if snapshot:
            from .report_snapshot import matches
            progress={str(item['activity_id']):{'status':item['status'],'memo':item.get('memo') or '', 'file':item.get('attachment')}
                for item in t.all('SELECT activity_id,status,memo,attachment FROM app_ext.activity_progress WHERE roadmap_id = :r FOR UPDATE',r=r['roadmap_id'])}
            stored = r['content']
            if not matches(snapshot, dict(stored, acts=tracked_acts(stored)), progress):
                from .duration_proposals import apply_plan_schedule
                refreshed = apply_plan_schedule(stored)
                if not matches(snapshot, dict(refreshed, acts=tracked_acts(refreshed)), progress):
                    raise ApiError(409,'REPORT_STALE','보고서 작성 후 실행 기록이 바뀌었어요. 최신 기록으로 보고서를 다시 만든 뒤 종료해 주세요.')
        t.run('INSERT INTO app_ext.report_meta(report_id, confirmed, confirmed_at) VALUES(:i, true, now()) ON CONFLICT (report_id) DO UPDATE SET confirmed = true, confirmed_at = now()',
              i=r['report_id'])
        _finish_report_plan(t, r['project_id'], r['roadmap_id'])
    return {'planStatus': 'done', 'planId': str(r['roadmap_id'])}


# ── 부서장 (API-55~59) ──
def team_members(head_id: int) -> dict:
    me = profile.view(head_id)
    ids = profile.member_ids(head_id)
    rows = profile._rows()
    unseen = NT.unseen_counts(head_id)  # 부서장이 아직 읽지 않은 그 직원의 로드맵·보고서 알림(#96)
    out = []
    for r in rows:
        if r['employee_id'] not in ids:
            continue
        v = profile.view(r['employee_id'], rows)
        recs = records(r['employee_id'], for_mgr=True)
        reps = reports(r['employee_id'])
        act = [x for x in recs.values() if x['status'] == 'active']
        u = unseen.get(r['employee_id'], {})
        out.append({'user': profile.team_view(v), 'activePlans': len(act), 'pastPlans': len(recs) - len(act), 'reports': len(reps),
                    'unreadComments': sum(1 for x in act for c in x['comments'] if c['status'] == 'new'),
                    'unseenPlans': u.get('plans', 0), 'unseenReports': u.get('reports', 0)})
    return {'group': me.get('supGroup'), 'members': out}


def member_state(head_id: int, member_id: int) -> dict:
    if member_id not in profile.member_ids(head_id):
        raise forbidden('소속 직원이 아니에요')
    recs = records(member_id, for_mgr=True)
    return {'user': profile.team_view(profile.view(member_id)), 'plans': recs, 'reports': reports(member_id, for_mgr=True), 'res': resources_of(recs), 'reg': reg_of(recs),
            'unseen': NT.unseen_targets(head_id, member_id)}

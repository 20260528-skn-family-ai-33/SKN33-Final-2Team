"""시연 도구: 처음 상태로 초기화 · 단계로 바로 이동 (4차 GP.act.reset · GP.seed 를 서버로 옮김 · 설계서 부록 A 시연 전용).

로그인한 직원의 기록(작성 중인 로드맵·확정 로드맵·점검·보고서·받은 코멘트)만 지우고 다시 만든다. 다른 직원의 기록은 건드리지 않는다.
시연 데이터는 가데이터 규칙(에이전트 mock 함수)으로 만든다. '코멘트 받은 뒤'는 내 계획을 보는 부서장 이름으로 예시 코멘트를 넣는다.
"""
from __future__ import annotations

import copy

from .. import db
from ..agents import diag as DG
from ..agents import regulation as REG
from ..agents import roadmap as RM
from ..agents.demo import D
from ..errors import ApiError
from . import drafts as DR
from . import plans as PL
from . import profile

STAGES = ['start', 'details', 'quiz', 'result', 'options', 'review', 'active', 'multi', 'comment', 'post', 'report']


def reset(employee_id: int) -> None:
    with db.tx() as t:
        t.run('DELETE FROM public.projects WHERE employee_id = :e', e=employee_id)


def _new_project(t: db.Tx, employee_id: int, w: dict) -> str:
    pid = str(t.val("""INSERT INTO public.projects(employee_id, project_name, status, current_stage, tech_stack, milestones, key_issues, deliverables,
                       validation_criteria, draft_conversations, draft_choices) VALUES(:e, '새 로드맵(작성 중)', 'DRAFTING', 1, '[]', '[]', '[]', '[]', '[]', '[]', :w)
                       RETURNING project_id""", e=employee_id, w=db.J(w)))
    DR._write(t, pid, w)
    return pid


def _confirm_into(t: db.Tx, employee_id: int, d: dict, pid_opt: str, goal: str | None = None, existing_project: str | None = None) -> str:
    """시연용 확정: 진단(문항·응답)을 담은 프로젝트에 로드맵을 넣는다. 두 번째 로드맵은 같은 진단을 복사한 새 프로젝트"""
    g = d['gen']
    o = g['options'][pid_opt]
    plan = RM.build_plan(o, RM.params_of(d['handoff'], o), goal or d['goal'])
    plan.update(version=1, confirmedAt=DR.today(), why='최초 확정', assess={'questions': d['quiz']['questions'], 'answers': dict(d['answers']), 'domain': d['quiz']['domain']},
                prefs=copy.deepcopy(d['prefs']), handoff=d['handoff'], selection=DR.selection_of(o))
    w = {'gp5': 1, 'confirmed': True}
    pj = existing_project or _new_project(t, employee_id, {'gp5': 1, 'draft': dict(d, goal=goal or d['goal']), 'draftPlan': None, 'lastNew': None})
    if not existing_project:
        d2 = copy.deepcopy(d)
        DR._save_questions(t, pj, d2)
        DR._save_answers(t, pj, d2)
        plan['assess']['questions'] = d2['quiz']['questions']
    rid = DR._round(t, pj, d)
    t.run('UPDATE public.diagnostic_rounds SET diagnostic_result = :r, agent_input = :h, pre_completed_at = now() WHERE diagnostic_round_id = CAST(:i AS uuid)',
          r=db.J(d['diag']), h=db.J(d['handoff']), i=rid)
    roadmap_id = PL.insert_roadmap(t, pj, rid, plan)
    t.run("UPDATE public.projects SET status = 'IN_PROGRESS', current_stage = 7, project_goal = :g, project_name = :n, draft_choices = :w WHERE project_id = CAST(:p AS uuid)",
          g=plan['goal'], n=plan['goal'][:255], w=db.J(dict(w, roadmapId=roadmap_id)), p=pj)
    return roadmap_id


def _progress(t: db.Tx, roadmap_id: str, act_id: str, status: str, memo: str = '') -> None:
    t.run("""INSERT INTO app_ext.activity_progress(roadmap_id, activity_id, status, memo) VALUES(CAST(:r AS uuid), :a, :s, :m)
             ON CONFLICT (roadmap_id, activity_id) DO UPDATE SET status = EXCLUDED.status, memo = EXCLUDED.memo, updated_at = now()""", r=roadmap_id, a=act_id, s=status, m=memo)
    t.run("UPDATE public.roadmap_steps SET is_completed = :d WHERE roadmap_id = CAST(:r AS uuid) AND details->>'id' = :a", d=status == 'done', r=roadmap_id, a=act_id)


def jump(employee_id: int, stage: str) -> dict:
    if stage not in STAGES:
        raise ApiError(400, 'BAD_STAGE', '알 수 없는 시연 단계예요')
    me = profile.view(employee_id)
    if stage == 'comment' and not me.get('mySupervisor'):
        raise ApiError(409, 'NO_SUPERVISOR', '내 계획을 보는 부서장이 없는 계정이라 이 단계는 쓸 수 없어요')
    reset(employee_id)
    if stage == 'start':
        return {'entry': 'home'}
    sc = D['scenario']
    d = DR.fresh_draft()
    d['goal'] = sc['goal']
    w = {'gp5': 1, 'draft': d, 'draftPlan': None, 'lastNew': None}
    with db.tx() as t:
        if stage == 'details':
            w['lastNew'] = 'new-details'
            _new_project(t, employee_id, w)
            return {'entry': 'new-details'}
        d['prefs'].update(sc['details'])
        d['detailsOk'] = True
        q = DG._mock_questions({'goal': d['goal'], 'certPlan': None})
        d['quiz'] = {'key': DR.quiz_key(d), 'questions': q['questions'], 'domain': q['domain'], 'base': {'goal': d['goal'], 'project': None, 'doc': None}}
        pj = _new_project(t, employee_id, w)
        DR._save_questions(t, pj, d)
        if stage == 'quiz':
            w['lastNew'] = 'new-quiz'
            DR._write(t, pj, w)
            return {'entry': 'new-quiz'}
        d['answers'] = dict(sc['pre'])
        DR._save_answers(t, pj, d)
        prefs = dict(d['prefs'], certRes=DR.cert_res(d['prefs']))
        d['diag'] = dict({'key': DR.diag_key(d), 'answers': dict(d['answers'])},
                         **DG._mock_assess({'goal': d['goal'], 'prefs': prefs, 'questions': d['quiz']['questions'], 'answers': d['answers']}))
        if stage == 'result':
            w['lastNew'] = 'new-result'
            DR._write(t, pj, w)
            return {'entry': 'new-result'}
        d['handoff'] = DR.build_handoff(d)
        d['genPrefs'] = copy.deepcopy(d['prefs'])
        d['gen'] = {'key': d['handoff']['key'], 'options': {pid: RM._mock_option({'pid': pid, 'handoff': d['handoff']}) for pid in D['optionOrder']}, 'missing': []}
        for pid, o in d['gen']['options'].items():
            o['support'] = REG._mock_support_one(DR._sup_input(pid, o['name'], RM.build_plan(o, RM.params_of(d['handoff'], o), d['goal'])), me) \
                if REG.regstore.set_for(me.get('empGroup')) else REG.support_scope(me)
        if stage == 'options':
            w['lastNew'] = 'new-options'
            DR._write(t, pj, w)
            return {'entry': 'new-options'}
        d['chosen'] = 'A3'
        w['draftPlan'] = RM.build_plan(d['gen']['options']['A3'], RM.params_of(d['handoff'], d['gen']['options']['A3']), d['goal'])
        if stage == 'review':
            w['lastNew'] = 'new-review'
            DR._write(t, pj, w)
            return {'entry': 'new-review'}
        rid = _confirm_into(t, employee_id, d, 'A3', existing_project=pj)
    # 진행 기록·코멘트·사후 점검·보고서
    plan = PL._base_rows(employee_id, rid)[0]['content']
    ids = [a['id'] for a in plan['acts']]
    with db.tx() as t:
        for i in ids[:2]:
            _progress(t, rid, i, 'done')
        _progress(t, rid, ids[2], 'doing', '공개 가능 여부를 확인한 규정 6건까지 정리했어요.')
        if stage == 'multi':
            rid2 = _confirm_into(t, employee_id, d, 'A1', goal=D['scenario2Goal'])
            # 같은 트랜잭션 안에서 읽는다(아직 커밋 전이라 다른 연결로는 안 보임)
            first = t.val('SELECT content FROM public.roadmaps WHERE roadmap_id = CAST(:r AS uuid)', r=rid2)['acts'][0]['id']
            _progress(t, rid2, first, 'done')
    if stage in ('active', 'multi'):
        return {'entry': 'home'}
    if stage == 'comment':
        sup = me['mySupervisor']
        c = D['commentSample']
        PL.send_comment(int(sup['id']), employee_id, rid, {'fit': c['fit'], 'fitText': c['fitText'], 'level': c['level'], 'levelText': c['levelText'], 'free': c['free']})
        return {'entry': 'home'}
    with db.tx() as t:
        for i in ids[2:-1]:
            _progress(t, rid, i, 'done')
        _progress(t, rid, ids[-1], 'doing', '팀 시연 일정 조율 중')
    if stage == 'post':
        return {'entry': f'post:{rid}'}
    PL.save_post(employee_id, rid, {'answers': dict(sc['post']), 'goalSelf': '4', 'file': {'name': '규정QA_시제품_시연메모.pdf', 'size': 240000}})
    row = PL._base_rows(employee_id, rid)[0]
    rec = PL.record(row)
    pl, post, A = rec['plan'], rec['post'], rec['plan']['assess']
    items = [{'id': q['id'], 'area': q['area'], 'text': q['text'], 'skill': DG.skill_label(q.get('skill') or ''), 'pre': A['answers'].get(q['id']), 'post': post['answers'].get(q['id'])} for q in A['questions']]
    done = [a['title'] for a in pl['acts'] if (rec['progress'].get(a['id']) or {}).get('status') == 'done']
    rest = [a['title'] for a in pl['acts'] if (rec['progress'].get(a['id']) or {}).get('status') != 'done']
    out = DG._mock_report({'goal': pl['goal'], 'opt': 'A3', 'domain': A.get('domain'), 'items': items, 'doneTitles': done, 'restTitles': rest, 'total': len(pl['acts'])})
    r = {'planId': rid, 'version': 1, 'goal': pl['goal'], 'opt': pl['name'], 'gained': [{'skill': x['skill'], 'from': x['pre'], 'to': x['post']} for x in items if DG.rose(x['pre'], x['post'])],
         'still': [{'skill': x['skill'], 'from': x['pre'], 'to': x['post']} for x in items if not DG.rose(x['pre'], x['post'])], 'doneTitles': done, 'restTitles': rest,
         'goalSelf': D['goalSelf'][3], 'file': post.get('file'), 'good': out['good'], 'improve': out['improve'], 'next': out['next'],
         'hidden': {'pre': d['diag']['level'], 'post': DG.level_of(A['questions'], post['answers'])}}
    with db.tx() as t:
        rep = str(t.val("INSERT INTO public.growth_reports(project_id, roadmap_id, report_type, report_content) VALUES(:p, :r, 'PRE_POST', :c) RETURNING report_id",
                        p=row['project_id'], r=row['roadmap_id'], c=db.J(r)))
        t.run('INSERT INTO app_ext.report_meta(report_id) VALUES(CAST(:i AS uuid))', i=rep)
        t.run('UPDATE public.diagnostic_rounds SET post_completed_at = now() WHERE diagnostic_round_id = :d', d=row['diagnostic_round_id'])
    return {'entry': f'report:{rep}'}

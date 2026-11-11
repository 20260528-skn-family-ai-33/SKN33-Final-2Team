"""시연 도구: 처음 상태로 초기화 · 단계로 바로 이동 (4차 GP.act.reset · GP.seed 를 서버로 옮김 · 설계서 부록 A 시연 전용).

단계 이동에서 만든 프로젝트만 교체한다. 코멘트 예시는 화면에서만 보여 준다.
"""
from __future__ import annotations

import copy

from .. import db
from ..agents import diag as DG
from ..agents import roadmap as RM
from ..agents.demo import D
from ..errors import ApiError
from . import drafts as DR
from . import plans as PL

STAGES = ['start', 'details', 'quiz', 'result', 'options', 'review', 'active', 'multi', 'comment', 'post', 'report']


def reset(employee_id: int) -> None:
    with db.tx() as t:
        _clear_seeded_projects(t, employee_id)


def _clear_seeded_projects(t: db.Tx, employee_id: int) -> None:
    t.lock_workspace(employee_id)
    # 이전 버전의 데이터는 출처를 증명할 수 없다. 실제 부서장이 의견을 남긴 시연 계획도 보존한다.
    t.run("""DELETE FROM public.projects p WHERE p.employee_id = :e
             AND p.draft_choices @> '{"demoSeeded": true}'
             AND NOT EXISTS (SELECT 1 FROM public.roadmaps r JOIN public.roadmap_comments c USING (roadmap_id)
                             WHERE r.project_id = p.project_id)""", e=employee_id)


def _new_project(t: db.Tx, employee_id: int, w: dict) -> str:
    w['demoSeeded'] = True
    pid = str(t.val("""INSERT INTO public.projects(employee_id, project_name, status, current_stage, tech_stack, milestones, key_issues, deliverables,
                       validation_criteria, draft_conversations, draft_choices) VALUES(:e, '새 로드맵(작성 중)', 'DRAFTING', 1, '[]', '[]', '[]', '[]', '[]', '[]', :w)
                       RETURNING project_id""", e=employee_id, w=db.J(w)))
    DR._write(t, pid, w)
    return pid


def _confirm_into(t: db.Tx, employee_id: int, d: dict, pid_opt: str, goal: str | None = None, existing_project: str | None = None) -> tuple[str, dict]:
    """시연용 확정: 진단(문항·응답)을 담은 프로젝트에 로드맵을 넣는다. 두 번째 로드맵은 같은 진단을 복사한 새 프로젝트"""
    g = d['gen']
    o = g['options'][pid_opt]
    plan = RM.build_plan(o, RM.params_of(d['handoff'], o), goal or d['goal'])
    plan.update(version=1, confirmedAt=DR.today(), why='최초 확정', assess={'questions': d['quiz']['questions'], 'answers': dict(d['answers']), 'domain': d['quiz']['domain']},
                prefs=copy.deepcopy(d['prefs']), handoff=d['handoff'], selection=DR.selection_of(o))
    w = {'gp5': 1, 'confirmed': True, 'demoSeeded': True}
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
    return roadmap_id, plan


def _progress(t: db.Tx, roadmap_id: str, act_id: str, status: str, memo: str = '') -> None:
    t.run("""INSERT INTO app_ext.activity_progress(roadmap_id, activity_id, status, memo) VALUES(CAST(:r AS uuid), :a, :s, :m)
             ON CONFLICT (roadmap_id, activity_id) DO UPDATE SET status = EXCLUDED.status, memo = EXCLUDED.memo, updated_at = now()""", r=roadmap_id, a=act_id, s=status, m=memo)
    t.run("UPDATE public.roadmap_steps SET is_completed = :d WHERE roadmap_id = CAST(:r AS uuid) AND details->>'id' = :a", d=status == 'done', r=roadmap_id, a=act_id)


def jump(employee_id: int, stage: str) -> dict:
    if stage not in STAGES:
        raise ApiError(400, 'BAD_STAGE', '알 수 없는 시연 단계예요')
    if stage == 'comment':
        # 읽기 전용 미리보기. 다른 단계의 시연 기록도 바꾸지 않는다.
        return {'entry': 'home'}
    sc = D['scenario']
    d = DR.fresh_draft()
    d['goal'] = sc['goal']
    w = {'gp5': 1, 'draft': d, 'draftPlan': None, 'lastNew': None}
    with db.tx() as t:
        _clear_seeded_projects(t, employee_id)
        if stage == 'start':
            return {'entry': 'home'}
        if stage in ('details', 'quiz', 'result', 'options', 'review') and DR._current_row(t, employee_id):
            raise ApiError(409, 'EXISTING_DRAFT', '작성 중인 로드맵이 있어 이 계정에 시연 초안을 열 수 없어요')
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
        rid, plan = _confirm_into(t, employee_id, d, 'A3', existing_project=pj)
        ids = [a['id'] for a in plan['acts']]
        for i in ids[:2]:
            _progress(t, rid, i, 'done')
        _progress(t, rid, ids[2], 'doing', '공개 가능 여부를 확인한 규정 6건까지 정리했어요.')
        if stage == 'multi':
            rid2, second = _confirm_into(t, employee_id, d, 'A1', goal=D['scenario2Goal'])
            _progress(t, rid2, second['acts'][0]['id'], 'done')
        if stage in ('active', 'multi'):
            return {'entry': 'home'}
        for i in ids[2:-1]:
            _progress(t, rid, i, 'done')
        _progress(t, rid, ids[-1], 'doing', '팀 시연 일정 조율 중')
        if stage == 'post':
            return {'entry': f'post:{rid}'}
        return _seed_report(t, pj, rid, plan, d)


def _seed_report(t: db.Tx, project_id: str, rid: str, pl: dict, d: dict) -> dict:
    A = pl['assess']
    answers = dict(D['scenario']['post'])
    attachment = {'name': '규정QA_시제품_시연메모.pdf', 'size': 240000}
    post_draft = dict(d, quiz=copy.deepcopy(d['quiz']), answers=answers)
    DR._save_questions(t, project_id, post_draft, kind='POST')
    DR._save_answers(t, project_id, post_draft, kind='POST')
    t.run("INSERT INTO app_ext.post_checks(roadmap_id, goal_self, attachment) VALUES(CAST(:r AS uuid), 4, :f)",
          r=rid, f=db.J(attachment))
    items = [{'id': q['id'], 'area': q['area'], 'text': q['text'], 'skill': DG.skill_label(q.get('skill') or ''), 'pre': A['answers'].get(q['id']), 'post': answers.get(q['id'])} for q in A['questions']]
    tracked = PL.tracked_acts(pl)
    last_id = pl['acts'][-1]['id']
    done = [a['title'] for a in tracked if a['id'] != last_id]
    rest = [a['title'] for a in tracked if a['id'] == last_id]
    out = DG._mock_report({'goal': pl['goal'], 'opt': 'A3', 'domain': A.get('domain'), 'items': items, 'doneTitles': done, 'restTitles': rest, 'total': len(tracked)})
    r = {'planId': rid, 'version': 1, 'goal': pl['goal'], 'opt': pl['opt'], 'gained': [{'skill': x['skill'], 'from': x['pre'], 'to': x['post']} for x in items if DG.rose(x['pre'], x['post'])],
         'still': [{'skill': x['skill'], 'from': x['pre'], 'to': x['post']} for x in items if not DG.rose(x['pre'], x['post'])], 'doneTitles': done, 'restTitles': rest,
         'goalSelf': D['goalSelf'][3], 'file': attachment, 'good': out['good'], 'improve': out['improve'], 'next': out['next'],
         'hidden': {'pre': d['diag']['level'], 'post': DG.level_of(A['questions'], answers)}}
    rep = str(t.val("INSERT INTO public.growth_reports(project_id, roadmap_id, report_type, report_content) VALUES(CAST(:p AS uuid), CAST(:r AS uuid), 'PRE_POST', :c) RETURNING report_id",
                    p=project_id, r=rid, c=db.J(r)))
    t.run('INSERT INTO app_ext.report_meta(report_id) VALUES(CAST(:i AS uuid))', i=rep)
    t.run('UPDATE public.diagnostic_rounds SET post_completed_at = now() WHERE project_id = CAST(:p AS uuid) AND round_number = 1', p=project_id)
    return {'entry': f'report:{rep}'}

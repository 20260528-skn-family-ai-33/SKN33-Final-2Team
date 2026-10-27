"""목표 후보 미리 만들기·저장·재생성 (FR-05 · 2026-10-21 사용자 요구 1).

- 직원 데이터가 바뀔 때(관리자 업로드로 그 직원의 인사 정보·평정이 바뀜, 내 정보에서 본인 입력·평정 동의를 저장) 서버가 작업으로 미리 만들어
  팀 DB public.employee_recommended_prompts(1~3순위)에 저장한다. 추천 이유·근거 항목은 app_ext.goal_suggestion_meta.
- 새 로드맵 화면은 저장된 후보 3개를 보여 주고, '목표 후보 다시 만들기'를 누르면 이전 후보와 다른 후보로 다시 만든다.
- 실패하면 이전 후보는 지우지 않고 실패 상태만 남긴다. 다시 시도는 사용자가 누를 때만(자동 재시도 없음).
- 만들 때 쓰는 AI 모드는 그 직원이 고른 모드(시연 도구 '가데이터로 보기'면 가데이터). 본인 입력이 없으면 에이전트 없이 기본 후보.
"""
from __future__ import annotations

import hashlib
import json

from .. import db, jobs
from ..agents import goals as G
from ..agents import runtime as rt
from . import profile


def _hash(inp: dict) -> str:
    return hashlib.sha256(json.dumps(inp['profile'], ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:16]


def get(employee_id: int) -> dict:
    rows = db.all_("""SELECT p.display_order, p.prompt_text, m.why, m.basis, p.updated_at FROM public.employee_recommended_prompts p
                      LEFT JOIN app_ext.goal_suggestion_meta m ON m.employee_id = p.employee_id AND m.display_order = p.display_order
                      WHERE p.employee_id = :e AND p.prompt_text IS NOT NULL ORDER BY p.display_order""", e=employee_id)
    # 만들던 작업이 끊겼으면(서버 재시작) 실패로 바꾼다. 작업이 결과를 쓴 뒤 끝났으면 status 가 이미 running 이 아니라 바뀌지 않는다
    with db.tx() as t:
        t.run("""UPDATE app_ext.goal_suggestion_runs g SET status = 'failed', error = :x, finished_at = now() WHERE g.employee_id = :e AND g.status = 'running'
                 AND g.job_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM app_ext.jobs j WHERE j.job_id = g.job_id AND j.status = 'running')""",
              x=db.J(jobs.lost_cause()), e=employee_id)
    run = db.one('SELECT * FROM app_ext.goal_suggestion_runs WHERE employee_id = :e', e=employee_id) or {}
    me = profile.view(employee_id)
    inp = G.goal_input(me)
    return {'status': run.get('status') or ('ready' if rows else 'none'), 'source': run.get('source'), 'note': run.get('note') or '',
            'used': run.get('used') or inp['used'], 'trigger': run.get('trigger'), 'jobId': str(run['job_id']) if run.get('job_id') else None,
            'error': run.get('error'), 'stale': bool(run.get('profile_hash')) and run.get('profile_hash') != _hash(inp) and run.get('status') != 'running',
            'updatedAt': (rows[0]['updated_at'] or run.get('finished_at')).strftime('%Y-%m-%d %H:%M') if rows and (rows[0]['updated_at'] or run.get('finished_at')) else None,
            'candidates': [{'goal': r['prompt_text'], 'why': r['why'] or '', 'basis': r['basis'] or []} for r in rows],
            'who': ' · '.join(x for x in (me.get('name'), me.get('dept'), me.get('grade')) if x)}


def _save(t: db.Tx, employee_id: int, cands: list[dict]) -> None:
    t.run('DELETE FROM public.employee_recommended_prompts WHERE employee_id = :e', e=employee_id)
    t.run('DELETE FROM app_ext.goal_suggestion_meta WHERE employee_id = :e', e=employee_id)
    for i, c in enumerate(cands[:3], 1):
        t.run('INSERT INTO public.employee_recommended_prompts(employee_id, prompt_text, display_order, updated_at) VALUES(:e, :p, :o, now())',
              e=employee_id, p=c['goal'].replace('\n', ' ').strip(), o=i)
        t.run('INSERT INTO app_ext.goal_suggestion_meta(employee_id, display_order, why, basis) VALUES(:e, :o, :w, :b)', e=employee_id, o=i, w=c.get('why') or '', b=db.J(c.get('basis') or []))


def _run_state(t: db.Tx, employee_id: int, **v) -> None:
    cols = ['status', 'source', 'note', 'used', 'profile_hash', 'trigger', 'error', 'job_id']
    vals = {c: v.get(c) for c in cols}
    vals['used'] = db.J(vals['used'] or [])
    vals['error'] = db.J(vals['error']) if vals['error'] is not None else None
    t.run(f"""INSERT INTO app_ext.goal_suggestion_runs(employee_id, {', '.join(cols)}, requested_at, finished_at)
              VALUES(:e, {', '.join(':' + c for c in cols)}, now(), CASE WHEN :status = 'running' THEN NULL ELSE now() END)
              ON CONFLICT (employee_id) DO UPDATE SET {', '.join(f'{c} = EXCLUDED.{c}' for c in cols)}, requested_at = CASE WHEN EXCLUDED.status = 'running' THEN now() ELSE app_ext.goal_suggestion_runs.requested_at END,
                  finished_at = EXCLUDED.finished_at""", e=employee_id, **vals)


def request(employee_id: int, trigger: str, avoid: list[str] | None = None, mode: str | None = None) -> str | None:
    """미리 만들기·다시 만들기 작업을 시작한다. 본인 입력이 없으면 기본 후보를 바로 저장하고 작업을 만들지 않는다.
    mode 'mock' 은 관리자가 고른 '시연용 가데이터로 만들기', 'ollama'·'openai' 는 관리자가 고른 모델(직원이 고른 AI 모드 대신 ·
    직원 설정은 바꾸지 않음 · 실패 시연 없음). 없으면 그 직원이 고른 모드"""
    me = profile.view(employee_id)
    if not me:
        return None
    inp = G.goal_input(me)
    ph = _hash(inp)
    if not G.profile_enough(me):
        with db.tx() as t:
            _save(t, employee_id, G.defaults())
            _run_state(t, employee_id, status='default', source='default', used=inp['used'], profile_hash=ph, trigger=trigger)
        return None

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id, me)
        if trigger.startswith('admin'):   # admin-all · admin-pick · admin-upload
            ctx.by = '관리자'
        if mode == 'mock':
            ctx.demo, ctx.fail_sim = True, {}
        elif mode in ('ollama', 'openai'):
            ctx.provider, ctx.demo, ctx.fail_sim = mode, False, {}
        sim = rt.sim_once(ctx, 'goal', ph + '|' + '|'.join(avoid or []))
        try:
            out = G.run(ctx, dict(inp, avoid=avoid or []), sim=sim)
        except rt.AgentError as e:
            with db.tx() as t:
                _run_state(t, employee_id, status='failed', used=inp['used'], profile_hash=ph, trigger=trigger, error=e.info, job_id=job.job_id)
            raise
        with db.tx() as t:
            _save(t, employee_id, out['candidates'])
            _run_state(t, employee_id, status='ready', source=ctx.mode, note=out.get('note') or '', used=inp['used'], profile_hash=ph, trigger=trigger, job_id=job.job_id)
        return {'candidates': out['candidates']}

    jid = jobs.start('goal-suggestions', employee_id, str(employee_id), work)
    with db.tx() as t:
        _run_state(t, employee_id, status='running', used=inp['used'], profile_hash=ph, trigger=trigger, job_id=jid)
    return jid


def regenerate(employee_id: int) -> str | None:
    """'목표 후보 다시 만들기': 지금 후보와 다른 후보로(4차 '다른 후보 받기'를 바꿈)"""
    cur = [c['goal'] for c in get(employee_id)['candidates']]
    return request(employee_id, 'manual', cur[-9:])


def seed_all() -> int:
    """DB 준비(setup_db.py) 때 한 번: 가데이터 규칙으로 바로 만든다(에이전트 기록·지연 없음). 이미 후보가 있으면 건너뛴다"""
    n = 0
    for r in db.all_('SELECT employee_id FROM public.employees WHERE employee_id NOT IN (SELECT employee_id FROM app_ext.goal_suggestion_runs)'):
        eid = r['employee_id']
        me = profile.view(eid)
        inp = G.goal_input(me)
        with db.tx() as t:
            if G.profile_enough(me):
                out = G.mock(inp)
                _save(t, eid, out['candidates'])
                _run_state(t, eid, status='ready', source='mock', note=out['note'], used=inp['used'], profile_hash=_hash(inp), trigger='setup')
            else:
                _save(t, eid, G.defaults())
                _run_state(t, eid, status='default', source='default', used=inp['used'], profile_hash=_hash(inp), trigger='setup')
        n += 1
    return n

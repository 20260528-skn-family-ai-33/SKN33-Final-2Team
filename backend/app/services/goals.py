"""홈페이지 정보 저장 뒤 필요한 목표 후보만 미리 만들고 재사용한다.

- 로그인·세션 조회는 생성하지 않는다. 추천 정보 저장 뒤 갱신하고 목표 진입은 미준비 계정만 보완한다.
- 명시적 다시 만들기·관리자 일괄 생성은 즉시 실행하며 결과는 public.employee_recommended_prompts에 저장한다.
- 새 로드맵 화면은 저장된 후보 3개를 보여 주고, '목표 후보 다시 만들기'를 누르면 이전 후보와 다른 후보로 다시 만든다.
- 실패하면 이전 후보는 지우지 않고 실패 상태만 남긴다. 다시 시도는 사용자가 누를 때만(자동 재시도 없음).
- 만들 때 쓰는 AI 모드는 그 직원이 고른 모드(시연 도구 '가데이터로 보기'면 가데이터). 본인 입력이 없어도 제공된 사내 정보를 사용하며 근거가 전혀 없을 때만 기본 후보.
"""
from __future__ import annotations

from contextlib import nullcontext
import hashlib
import json
from typing import TypedDict

from .. import db, jobs, llm, provider_policy
from ..agents import goals as G
from ..agents import runtime as rt
from ..config import S
from ..errors import ApiError, cause
from . import profile
from app.learner_knowledge import VERSION as KNOWLEDGE_VERSION


def _hash(inp: dict) -> str:
    # 평정이 없던 기존 후보는 입력이 동일하므로 다시 생성하지 않는다.
    profile_signature = {'evaluations': [], **inp['profile']}
    return hashlib.sha256(json.dumps([G.PROMPT_VERSION,KNOWLEDGE_VERSION,profile_signature], ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:16]


def validate_mode(mode: str | None) -> None:
    """가데이터를 명시한 요청은 저장·작업 등록 전에 검사한다."""
    if mode == 'mock' and not S.demo_mode:
        raise ApiError(409, 'DEMO_DISABLED', '시연 모드가 꺼져 있어 가데이터로 만들 수 없어요',
                       '사용할 AI 모드를 직접 선택해 주세요', kind='config')


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
            'error': run.get('error'), 'stale': bool(rows) and run.get('profile_hash') != _hash(inp) and run.get('status') != 'running',
            'updatedAt': (rows[0]['updated_at'] or run.get('finished_at')).strftime('%Y-%m-%d %H:%M') if rows and (rows[0]['updated_at'] or run.get('finished_at')) else None,
            'candidates': [{'goal': r['prompt_text'], 'why': r['why'] or '', 'basis': r['basis'] or []} for r in rows],
            'who': ' · '.join(x for x in (me.get('name'), me.get('dept'), me.get('grade')) if x)}


def _save(t: db.Tx, employee_id: int, cands: list[dict]) -> None:
    # 기존 후보를 지우기 전에 완성된 3개인지 확인한다. 실패하면 이전 후보가 남는다.
    texts = [str(c.get('goal') or '').replace('\n', ' ').strip() for c in cands]
    if len(texts) != 3 or any(not text for text in texts) or len({''.join(text.split()) for text in texts}) != 3:
        raise ValueError('서로 다른 목표 후보 3개가 필요해요')
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


class BulkModel(TypedDict):
    provider: str
    model: str
    level: str | None
    default_level: str | None


def _default_level(provider: str) -> str | None:
    return {'openai': S.openai_reasoning, 'ollama': S.ollama_think}.get(provider)


def bulk_model(employee: dict, mode: str | None, level: str | None) -> BulkModel:
    if mode is None:
        provider = provider_policy.resolve('employee', employee.get('ai_provider'))
        level = (employee.get('reasoning') or {}).get(provider)
        if S.demo_mode and employee.get('demo_mock'):
            provider, level = 'mock', None
    else:
        provider = mode
    return BulkModel(provider=provider, model=llm.model_name(provider), level=level,
                     default_level=_default_level(provider) if level is None else None)


def _apply_bulk_model(ctx: rt.Ctx, approved: BulkModel, mode: str | None) -> None:
    provider, level = approved['provider'], approved['level']
    validate_mode(provider)
    if provider not in ('mock', 'openai', 'ollama') or approved['model'] != llm.model_name(provider):
        raise ApiError(409, 'BULK_MODEL_CHANGED', '승인한 모델을 사용할 수 없어요. 모델을 확인하고 다시 요청해 주세요.')
    if level is None and approved['default_level'] != _default_level(provider):
        raise ApiError(409, 'BULK_MODEL_CHANGED', '서버의 기본 추론 단계가 변경됐어요. 확인 후 다시 요청해 주세요.')
    ctx.demo = provider == 'mock'
    if not ctx.demo:
        ctx.provider = provider
        ctx.reasoning = {provider: level} if level else {}
    if mode is not None:
        ctx.fail_sim = {}


def request(employee_id: int, trigger: str, avoid: list[str] | None = None, mode: str | None = None,
            *, only_if_stale: bool = False, approved_model: BulkModel | None = None) -> str | None:
    """같은 직원의 동시 요청은 작업을 공유한다. 같은 입력의 실패는 수동으로만 재시도한다."""
    validate_mode(mode)
    with db.tx() as t:
        t.val('SELECT pg_advisory_xact_lock(:ns, :e)', ns=1196443475, e=employee_id)
        run = t.one('SELECT * FROM app_ext.goal_suggestion_runs WHERE employee_id=:e', e=employee_id) or {}
        jid = str(run['job_id']) if run.get('job_id') else None
        if run.get('status') == 'running' and jid and jid in jobs.alive([jid], t):
            return jid
        if only_if_stale:
            me = profile.view(employee_id, t=t)
            if not me:
                return None
            same = run.get('profile_hash') == _hash(G.goal_input(me))
            count = t.val('SELECT count(*) FROM public.employee_recommended_prompts WHERE employee_id=:e', e=employee_id)
            seeded_mock = run.get('trigger') == 'setup' and run.get('source') == 'mock'
            if same and (run.get('status') == 'failed' or (run.get('status') in ('ready', 'default') and count == 3 and not seeded_mock)):
                return None
        return _request(employee_id, trigger, avoid, mode, t=t, approved_model=approved_model)


def _request(employee_id: int, trigger: str, avoid: list[str] | None, mode: str | None, *,
             t: db.Tx | None = None, approved_model: BulkModel | None = None) -> str | None:
    """미리 만들기·다시 만들기 작업을 시작한다. 사내/본인 입력 근거가 전혀 없을 때만 기본 후보를 저장한다.
    mode 'mock' 은 관리자가 고른 '시연용 가데이터로 만들기', 'ollama'·'openai' 는 관리자가 고른 모델(직원이 고른 AI 모드 대신 ·
    직원 설정은 바꾸지 않음 · 실패 시연 없음). 없으면 그 직원이 고른 모드"""
    validate_mode(mode)
    me = profile.view(employee_id, t=t) if t is not None else profile.view(employee_id)
    if not me:
        return None
    inp = G.goal_input(me)
    ph = _hash(inp)
    if not G.profile_enough(me):
        with (nullcontext(t) if t is not None else db.tx()) as t:
            _save(t, employee_id, G.defaults())
            _run_state(t, employee_id, status='default', source='default', used=inp['used'], profile_hash=ph, trigger=trigger)
        return None

    def work(job: jobs.JobCtx):
        try:
            ctx = rt.context(employee_id, me)
            if trigger.startswith('admin'):
                ctx.by = '관리자'
            if approved_model is not None:
                _apply_bulk_model(ctx, approved_model, mode)
            elif trigger in ('admin-all', 'admin-pick'):
                # 이전 버전의 중단 작업에는 관리자가 확인한 추론 단계가 없다.
                raise ApiError(409, 'BULK_MODEL_UNKNOWN', '기존 일괄 작업의 모델 설정을 확인할 수 없어요. 다시 요청해 주세요.')
            elif mode == 'mock':
                ctx.demo, ctx.fail_sim = True, {}
            elif mode in ('ollama', 'openai'):
                if not ctx.provider_managed:
                    ctx.provider, ctx.reasoning = mode, {}
                ctx.demo, ctx.fail_sim = False, {}
            sim = rt.sim_once(ctx, 'goal', ph + '|' + '|'.join(avoid or []))
            out = G.run(ctx, dict(inp, avoid=avoid or []), sim=sim)
        except (rt.AgentError, ApiError) as e:
            with db.tx() as t:
                latest = t.one('SELECT job_id FROM app_ext.goal_suggestion_runs WHERE employee_id=:e FOR UPDATE', e=employee_id) or {}
                if str(latest.get('job_id')) == job.job_id:
                    _run_state(t, employee_id, status='failed', used=inp['used'], profile_hash=ph, trigger=trigger,
                               error=jobs.error_info(e), job_id=job.job_id)
            if isinstance(e, rt.AgentError) and _hash(G.goal_input(profile.view(employee_id))) != ph:
                request(employee_id, 'admin-profile-changed' if trigger.startswith('admin') else 'profile-changed',
                        mode=mode, only_if_stale=True, approved_model=approved_model)
            raise
        changed = None
        with db.tx() as t:
            latest = t.one('SELECT job_id FROM app_ext.goal_suggestion_runs WHERE employee_id=:e FOR UPDATE', e=employee_id) or {}
            if str(latest.get('job_id')) != job.job_id:
                return {'discarded': True}
            t.val('SELECT employee_id FROM public.employees WHERE employee_id=:e FOR UPDATE', e=employee_id)
            if _hash(G.goal_input(profile.view(employee_id, t=t))) != ph:
                changed = cause('후보 생성 중 내 정보가 바뀌었어요. 바뀐 정보로 다시 만들어 주세요.')
                _run_state(t, employee_id, status='failed', used=inp['used'], profile_hash=ph, trigger=trigger,
                           error=changed, job_id=job.job_id)
            else:
                _save(t, employee_id, out['candidates'])
                _run_state(t, employee_id, status='ready', source=ctx.mode, note=out.get('note') or '', used=inp['used'], profile_hash=ph, trigger=trigger, job_id=job.job_id)
        if changed:
            # 같은 실패 입력을 재시도하는 것이 아니라 저장 중 바뀐 새 입력을 준비한다.
            return {'discarded': True, 'nextJobId': request(employee_id,
                    'admin-profile-changed' if trigger.startswith('admin') else 'profile-changed', mode=mode,
                    only_if_stale=True, approved_model=approved_model)}
        return {'candidates': out['candidates']}

    def mark(jid: str) -> None:
        with (nullcontext(t) if t is not None else db.tx()) as state_tx:
            _run_state(state_tx, employee_id, status='running', used=inp['used'], profile_hash=ph, trigger=trigger, job_id=jid)

    work._resume = {'operation': 'goals.request', 'kwargs': {
        'employee_id': employee_id, 'trigger': trigger, 'avoid': avoid, 'mode': mode, 'approved_model': approved_model}}
    return jobs.start('goal-suggestions', employee_id, str(employee_id), work, before_start=mark, transaction=t)


def regenerate(employee_id: int) -> str | None:
    """'목표 후보 다시 만들기': 지금 후보와 다른 후보로(4차 '다른 후보 받기'를 바꿈)"""
    cur = [c['goal'] for c in get(employee_id)['candidates']]
    return request(employee_id, 'manual', cur[-9:])


def seed_all() -> int:
    """DB 준비(setup_db.py) 때 한 번: 가데이터 규칙으로 바로 만든다(에이전트 기록·지연 없음). 이미 후보가 있으면 건너뛴다"""
    validate_mode('mock')
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

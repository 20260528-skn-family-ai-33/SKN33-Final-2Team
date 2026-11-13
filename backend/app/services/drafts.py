"""새 로드맵 작성 (설계서 v1.7 API-14~35).

저장: 작성 중인 로드맵 = 팀 DB public.projects 한 행(status 'DRAFTING'). 화면이 쓰던 작성 문서(4차 S.draft)는 projects.draft_choices 에
{"gp5": 1, "draft": …, "draftPlan": …, "lastNew": …} 로 둔다. 사전 점검 문항·응답·진단은 ERD 표에도 쓴다
(diagnostic_rounds 1회차 · assessment_questions/responses PRE · 진단 결과·전달 내용은 diagnostic_result·agent_input).
문서 필드 중 화면이 고치는 것(목표·세부 사항·응답·고른 안 …)은 PATCH 로, 에이전트 결과(문항·진단·3안·지원 조건 …)는 서버 작업만 쓴다.
작업은 행을 잠그고(FOR UPDATE) 문서를 읽어 고친 뒤 쓴다 — A1·A2·A3 가 동시에 끝나도 서로 덮어쓰지 않는다.
확정하면 고르지 않은 안·버전은 버린다(API-35).
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from datetime import date

from .. import catalog, db, docread, jobs
from ..agents import deepcheck as DC
from ..agents import diag as DG
from ..agents import doc as DOC
from ..agents import regulation as REG
from ..agents import roadmap as RM
from ..agents import runtime as rt
from ..agents.demo import D, course_name
from ..errors import AgentError, ApiError, cause, not_found
from ..free_track import validate_free_plan
from . import notifications as NT
from . import plans as PL
from . import profile as PF

STEP_ROUTES = ['new-goal', 'new-details', 'new-details-check', 'new-quiz', 'new-result', 'new-result-edit', 'new-gen', 'new-options', 'new-materials', 'new-review']
# deepOn·deepMcq·deepEssay: 심화 질문을 풀지(체크)와 객관식·서술형 답(10/23)
# startMode: 진행 중인 로드맵이 있을 때 작성 탭에 들어오며 고른 시작 방식(확정 때 화면이 보낸다)
CLIENT_KEYS = ('goal', 'project', 'prefs', 'detailsOk', 'answers', 'deepOn', 'deepMcq', 'deepEssay', 'chosen', 'edit', 'lastNew', 'selectedSkills', 'skillInputKey', 'skillCandidates', 'fixedSkillNames', 'skillPool', 'startMode')
_images: dict[str, list] = {}   # 기획서 이미지(base64)는 DB에 넣지 않고 서버 메모리에만 잠깐 둔다
_img_lock = threading.Lock()


def fresh_draft() -> dict:
    return {'goal': '', 'project': None, 'prefs': {'format': '', 'cert': '', 'hours': '', 'weeks': '', 'budget': '', 'etc': ''}, 'detailsOk': False,
            'quiz': None, 'answers': {}, 'deepOn': False, 'deepMcq': {}, 'deepEssay': {}, 'diag': None, 'startStage': None, 'fix': None, 'edit': None, 'handoff': None, 'gen': None, 'chosen': None,
            'quizFail': None, 'diagFail': None, 'genRun': None, 'doc': None, 'genPrefs': None, 'quizRun': None, 'diagRun': None, 'startMode': None}


def today() -> str:
    return date.today().isoformat()


# ── 4차 계산 그대로 (gp-app.js · gp-parts.js) ──
def doc_summary(d: dict) -> str:
    doc = d.get('doc') or {}
    return str(doc.get('summary') or '').strip() if doc.get('status') == 'ok' else ''


def quiz_rest(d: dict) -> str:
    return f"{(d.get('goal') or '').strip()}|{(d.get('project') or {}).get('name', '') if d.get('project') else ''}|{doc_summary(d)}"


def quiz_key(d: dict) -> str:
    current = quiz_rest(d)
    saved = (d.get('quiz') or {}).get('key') or ''
    # Keep completed legacy assessments when their actual inputs match.
    return saved if saved.startswith(current + '|cert:') else current

def deep_on(d: dict) -> bool:
    return bool(d.get('deepOn') and (d.get('quiz') or {}).get('deep'))


def diag_key(d: dict) -> str:
    """심화 질문을 풀면 객관식 답(자가 진단 문항 순서)과 서술형 답도 키에 넣는다. 화면(P.diagKey)과 같은 계산"""
    q = d.get('quiz')
    base = (q['key'] if q else '') + '|' + (','.join(str(d['answers'].get(x['id']) or '-') for x in q['questions']) if q else '')
    if deep_on(d):
        dp = q['deep']
        base += ('|deep:' + ','.join(str((d.get('deepMcq') or {}).get(x['id']) or '-') for x in q['questions'] if x['id'] in dp['mcq'])
                 + '|' + '\x1f'.join(str((d.get('deepEssay') or {}).get(e['id']) or '').strip() for e in dp['essays']))
    return base


def blank(v) -> bool:
    return v is None or v == ''


def num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def pref_text(k: str, p: dict) -> str:
    v = p.get(k)
    if k == 'format':
        return next((l for x, l in D['formatOpts'] if x == v), '알아서')
    if k == 'cert':
        c = catalog.cert_by_code(p.get('cert'))
        return f"{c['title']} · 4단계에 준비 활동을 넣어요" if c else '계획 없음'
    if k == 'hours':
        return f'주 {v}시간' if num(v) > 0 else '알아서 (로드맵 계획 에이전트가 정해요)'
    if k == 'weeks':
        return f'{v}주 안에' if num(v) > 0 else '알아서 (정해진 기간 없음)'
    if k == 'budget':
        return '알아서' if blank(v) else f'{int(num(v)):,}원' if num(v) > 0 else '0원 (무료 자료만)'
    if k == 'etc':
        return str(v or '').strip() or '없음'
    return ''


def pref_summary(p: dict) -> dict:
    return {l: pref_text(k, p) for k, l in D['detailFields']}


def cert_res(p: dict) -> str | None:
    # 기존 호출 계약 유지. 자격증은 로드맵의 참고 추천으로만 제공한다.
    return None


def handoff_prefs(p: dict) -> dict:
    budget = None if blank(p.get('budget')) else max(0, int(num(p.get('budget'))))
    hours = num(p.get('hours'))
    weeks = num(p.get('weeks'))
    return {'format': pref_text('format', p), 'formatKey': p.get('format') or 'auto', 'certPlan': '없음', 'certRes': cert_res(p),
            'weeklyHours': min(40, hours) if hours > 0 else None, 'hoursAuto': not hours > 0, 'deadlineWeeks': min(52, round(weeks)) if weeks > 0 else None,
            'budgetWon': budget, 'budgetAuto': budget is None, 'budgetLimit': budget}


def start_of(d: dict) -> int:
    s = d.get('startStage')
    return int(s) if s and 1 <= int(s) <= 4 else d['diag']['startStage']


FIX = [('competencies', '익히게 될 역량'), ('resourceIds', '듣게 될 강좌·자료'), ('outcome', '만들 결과물'), ('known', '이미 할 수 있는 것')]


def dv(d: dict, k: str):
    return d['fix'][k] if d.get('fix') and d['fix'].get(k) is not None else d['diag'][k]


def edited(d: dict, k: str) -> bool:
    return start_of(d) != d['diag']['startStage'] if k == 'start' else bool(d.get('fix') and d['fix'].get(k) is not None)


def build_handoff(d: dict, profile: dict | None = None) -> dict:
    """profile: 업무 정보(diag.work_profile · 10/23 v2.2). 있을 때만 넣어 가데이터·업무 정보 없는 직원의 키는 그대로 둔다"""
    a, start = d['diag'], start_of(d)
    changed = start != a['startStage']
    h = {'goal': d['goal'], 'projectFile': (d.get('project') or {}).get('name') if d.get('project') else None, 'projectSummary': doc_summary(d) or None,
         'domain': (d.get('quiz') or {}).get('domain') or '', 'startStage': start,
         'startReason': f"사용자가 {start}단계부터 하기로 정함 (진단 제안: {a['startStage']}단계 · {a['startReason']})" if changed else a['startReason'],
         'startSuggested': a['startStage'], 'known': dv(d, 'known'), 'gaps': a.get('gaps') or [], 'focus': dv(d, 'competencies'), 'outcome': dv(d, 'outcome'),
         'resourceHints': dv(d, 'resourceIds'), 'prefs': handoff_prefs(d['prefs']), 'userNotes': [d['prefs']['etc'].strip()] if str(d['prefs'].get('etc') or '').strip() else [],
         'agentNotes': a.get('handoffNotes') or [], 'userEdited': (['시작 단계'] if changed else []) + [l for k, l in FIX if edited(d, k)]}
    if profile:
        h['profile'] = profile
    if deep_on(d) and a.get('deep'):
        # 심화 질문 결과 요약(10/23): 개념별 자기평가·객관식 결과, 영역별 서술형 판단, 자기평가와 다른 개념
        h['deepCheck'] = DC.handoff_summary(d['quiz']['questions'], d['answers'], d['quiz']['deep'], a['deep']['grade'], a['deep']['judge'], DG.ans, DG.skill_label)
    from .. import track_policy
    skills = catalog.roadmap_skills([h['goal'], h.get('projectSummary') or ''] + h['focus'] + h['gaps'])
    if skills:
        h['skillNames'] = skills
    h['trackPolicyVersion'] = track_policy.VERSION
    h['key'] = hashlib.sha1(json.dumps(h, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:16]
    return h


def clear_from(d: dict, stage: str) -> None:
    if stage == 'quiz':
        d.update(quiz=None, answers={}, deepMcq={}, deepEssay={}, quizFail=None, quizRun=None)
    if stage in ('quiz', 'diag'):
        d.update(diag=None, diagFail=None, diagRun=None, startStage=None, fix=None, edit=None)
    d.update(handoff=None, gen=None, chosen=None, genRun=None)


def input_signature(d):
    return json.dumps([d.get('goal'),d.get('project'),d.get('prefs'),doc_summary(d),d.get('selectedSkills')],ensure_ascii=False,sort_keys=True)


def invalidate_inputs(w):
    clear_from(w['draft'],'quiz')
    w['draft'].update(detailsOk=False,genPrefs=None)
    w['draft'].pop('v2Assessment',None)
    w.pop('v2Survey',None)
    w['draftPlan']=None


# ── 저장 ──
def _wrap(raw) -> dict:
    if isinstance(raw, dict) and raw.get('gp5') and isinstance(raw.get('draft'), dict):
        out = dict(raw)
        out['draft'] = dict(fresh_draft(), **raw['draft'])
        return out
    return {'gp5': 1, 'draft': fresh_draft(), 'draftPlan': None, 'lastNew': None}


def _current_row(t: db.Tx, employee_id: int, lock: bool = False) -> dict | None:
    return t.one(f"""SELECT project_id, draft_choices FROM public.projects WHERE employee_id = :e AND status = 'DRAFTING'
                    ORDER BY updated_at DESC LIMIT 1{' FOR UPDATE' if lock else ''}""", e=employee_id)


def _row(t: db.Tx, employee_id: int, draft_id: str, lock: bool = True) -> dict:
    r = t.one(f"""SELECT project_id, draft_choices FROM public.projects WHERE project_id = CAST(:p AS uuid) AND employee_id = :e AND status = 'DRAFTING'
                 {'FOR UPDATE' if lock else ''}""", p=draft_id, e=employee_id)
    if not r:
        raise not_found('작성 중인 로드맵')
    return r


def _write(t: db.Tx, draft_id: str, w: dict) -> None:
    d = w['draft']
    stage = STEP_ROUTES.index(w['lastNew'].split(':')[0]) + 1 if w.get('lastNew') and w['lastNew'].split(':')[0] in STEP_ROUTES else 1
    t.run("""UPDATE public.projects SET draft_choices = :w, project_goal = :g, project_name = :n, extracted_text = :x, refined_plan = :s,
             current_stage = :c, updated_at = now() WHERE project_id = CAST(:p AS uuid)""",
          w=db.J(w), g=d.get('goal') or None, n=(d.get('goal') or '새 로드맵(작성 중)')[:255], x=((d.get('doc') or {}).get('text') or None),
          s=doc_summary(d) or None, c=min(stage, 6), p=draft_id)


def _mutate(employee_id: int, draft_id: str, fn) -> dict:
    with db.tx() as t:
        r = _row(t, employee_id, draft_id)
        w = _wrap(r['draft_choices'])
        out = fn(t, w)
        _write(t, draft_id, w)
    return out if out is not None else w


def _res_keys(w: dict) -> list[str]:
    d, keys = w['draft'], []
    if d.get('diag'):
        keys += list(d['diag'].get('resourceIds') or []) + list((d.get('fix') or {}).get('resourceIds') or [])
    for o in ((d.get('gen') or {}).get('options') or {}).values():
        keys += [a.get('res') for a in o.get('acts', [])]
    for lst in ((d.get('gen') or {}).get('hist') or {}).values():
        for o in lst:
            keys += [a.get('res') for a in o.get('acts', [])]
    for row in ((d.get('genRun') or {}).get('rows') or {}).values():
        keys += [a.get('res') for a in ((row or {}).get('out') or {}).get('acts', [])]
    if w.get('draftPlan'):
        keys += [a.get('res') for a in w['draftPlan'].get('acts', [])]
    if cert_res(d['prefs']):
        keys.append(cert_res(d['prefs']))
    return [k for k in keys if k]


def present(w: dict | None, draft_id: str | None) -> dict:
    """화면에 줄 모양: 작성 문서 + 쓰인 자료·규정 근거"""
    if not w:
        return {'draftId': None, 'draft': None, 'draftPlan': None, 'lastNew': None, 'res': {}, 'reg': {'articles': {}, 'regs': {}}}
    d = w['draft']
    displayed_plan=w.get('draftPlan')
    invalid_selection=bool(d.get('chosen') and d['chosen'] not in ((d.get('gen') or {}).get('options') or {}))
    if invalid_selection:
        d=dict(d,chosen=None,selectionNotice='이전에 선택한 코스가 현재 제안에 없어요. 남아 있는 코스를 다시 선택해 주세요.')
        displayed_plan=None
    assessment = w.get('v2Survey')
    if isinstance(assessment, dict):
        from app.services.activity_selection import current_record, materials_ready
        from app.services.course_recommendations import scope_view
        scoped = None if invalid_selection else scope_view(assessment, d.get('chosen'), ((d.get('gen') or {}).get('options') or {}).get(d.get('chosen')))
        proposal = current_record(scoped, d) if scoped is not None else None
        from app.services.activity_selection import materials_key
        ready=(materials_ready(scoped) or bool(proposal)) if scoped is not None else False
        d = dict(d, v2Assessment={'generationId': assessment['generationId'], 'completed': bool(assessment.get('completed')), 'materialsReady': ready, 'materialsKey': materials_key(scoped) if ready else None, 'activitiesReady': bool(proposal and proposal.get('selectedIds'))})
        if ready and not displayed_plan:
            from app.services.material_plan import preview
            displayed_plan=preview(scoped,d)
    q = d.get('quiz')
    if q and q.get('deep'):
        # 심화 질문 정답·해설·모범 답안은 점검 결과가 나온 뒤에만 보낸다(10/23 · 화면에서는 접어 둠)
        d = dict(d, quiz=dict(q, deep=DC.public(q['deep'], bool((d.get('diag') or {}).get('deep')))))
    return {'draftId': draft_id, 'draft': dict(d, demoSeeded=w.get('demoSeeded') is True), 'draftPlan': displayed_plan, 'lastNew': w.get('lastNew'),
            'res': catalog.resources_for(_res_keys(w)), 'reg': {'articles': {}, 'regs': {}}}


def _run_jobs(w: dict) -> list[str]:
    d = w['draft']
    ids = [(d.get('quizRun') or {}).get('jobId'), (d.get('diagRun') or {}).get('jobId')]
    if (d.get('doc') or {}).get('status') == 'reading':
        ids.append(d['doc'].get('jobId'))
    ids += [row.get('jobId') for row in ((d.get('genRun') or {}).get('rows') or {}).values() if row and row.get('st') == 'run']
    ids += [x.get('jobId') for x in ((d.get('gen') or {}).get('regenRun') or {}).values() if x]
    return [x for x in ids if x]


def _heal(t: db.Tx, w: dict) -> None:
    """서버를 다시 켜는 등으로 끊긴 작업의 '작성 중' 표시를 '작업을 찾지 못함' 실패로 바꾼다(다시 시도는 사용자가 누를 때만).
    행을 잠근 채 작업 표를 보므로, 작업이 결과를 쓴 뒤 끝난 경우를 끊김으로 잘못 보지 않는다(작업은 결과를 쓴 다음에 끝남으로 바뀐다)"""
    ids = _run_jobs(w)
    live = jobs.alive(ids, t)
    if all(i in live for i in ids) and not _orphaned_options(w):
        return
    d, lost = w['draft'], jobs.lost_cause()
    for run, fail, key_of, done in (('quizRun', 'quizFail', quiz_key, 'quiz'), ('diagRun', 'diagFail', diag_key, 'diag')):
        r = d.get(run) or {}
        if r.get('jobId') and r['jobId'] not in live:
            if r.get('key') == key_of(d) and not ((d.get(done) or {}).get('key') == r['key']):
                d[fail] = {'key': r['key'], 'cause': lost}
            d[run] = None
    doc = d.get('doc') or {}
    if doc.get('status') == 'reading' and doc.get('jobId') and doc['jobId'] not in live:
        doc.update(status='fail', step=doc.get('step') or 'summary', fail={'cause': lost})
    for row in ((d.get('genRun') or {}).get('rows') or {}).values():
        if row and row.get('st') == 'run' and row.get('jobId') not in live:
            row.update(st='fail', err=lost, jobId=None)
    g = d.get('gen') or {}
    for pid, x in list((g.get('regenRun') or {}).items()):
        if x and x.get('jobId') and x['jobId'] not in live:
            g['regenRun'].pop(pid)
            g.setdefault('regenErr', {})[pid] = lost


def _orphaned_options(w: dict) -> bool:
    return any(row and row.get('st') == 'run' and not row.get('jobId')
               for row in ((w['draft'].get('genRun') or {}).get('rows') or {}).values())


def _healed(employee_id: int, draft_id: str, w: dict) -> dict:
    ids = _run_jobs(w)
    if _orphaned_options(w) or (ids and not all(i in jobs.alive(ids) for i in ids)):
        return _mutate(employee_id, draft_id, _heal)
    return w


def current(employee_id: int) -> dict:
    with db.tx() as t:
        r = _current_row(t, employee_id)
    if not r:
        return present(None, None)
    pid = str(r['project_id'])
    return present(_healed(employee_id, pid, _wrap(r['draft_choices'])), pid)


def get(employee_id: int, draft_id: str) -> dict:
    with db.tx() as t:
        r = _row(t, employee_id, draft_id, lock=False)
    return present(_healed(employee_id, draft_id, _wrap(r['draft_choices'])), draft_id)


def create(employee_id: int, body: dict) -> dict:
    """작성 시작(API-14). 이미 작성 중인 것이 있으면 그것을 돌려준다(작성 중인 로드맵은 하나)"""
    with db.tx() as t:
        t.lock_workspace(employee_id)
        r = _current_row(t, employee_id, lock=True)
        if r:
            return present(_wrap(r['draft_choices']), str(r['project_id']))
        w = {'gp5': 1, 'draft': fresh_draft(), 'draftPlan': None, 'lastNew': body.get('lastNew')}
        if isinstance(body.get('draft'), dict):
            _apply_client(w, body['draft'])
        pid = str(t.val("""INSERT INTO public.projects(employee_id, project_name, status, current_stage, tech_stack, milestones, key_issues, deliverables,
                           validation_criteria, draft_conversations, draft_choices) VALUES(:e, '새 로드맵(작성 중)', 'DRAFTING', 1, '[]', '[]', '[]', '[]', '[]', '[]', :w)
                           RETURNING project_id""", e=employee_id, w=db.J(w)))
        _write(t, pid, w)
    return present(w, pid)


def _check_start_mode(mode) -> None:
    if mode is not None and mode not in PL.START_MODES:
        raise ApiError(422, 'BAD_START_MODE', '새 로드맵의 시작 방식을 다시 골라 주세요')


def _apply_client(w: dict, body: dict) -> None:
    _check_start_mode(body.get('startMode'))
    d = w['draft']
    previous_inputs=input_signature(d)
    previous_chosen=d.get('chosen')
    for k in CLIENT_KEYS:
        if k in body:
            if k == 'lastNew':
                w['lastNew'] = body[k]
            else:
                d[k] = body[k]
    if 'docSummary' in body and d.get('doc'):
        d['doc']['summary'] = str(body['docSummary'] or '')[:1500]
    if 'genCur' in body and d.get('gen') and isinstance(body['genCur'], dict):
        g = d['gen']
        for pid, i in body['genCur'].items():
            lst = (g.get('hist') or {}).get(pid)
            if lst and 0 <= int(i) < len(lst) and int(i)!=(g.get('cur') or {}).get(pid,0):
                if (g.get('regenRun') or {}).get(pid):raise ApiError(409,'REGEN_RUNNING','계획 생성이 끝난 뒤 버전을 바꿔 주세요.')
                from app.services.course_recommendations import invalidate_course_tail
                invalidate_course_tail(w,pid)
                g.setdefault('cur', {})[pid] = int(i)
                g['options'][pid] = lst[int(i)]
                if w.get('draftPlan') and w['draftPlan'].get('opt') == pid:
                    w['draftPlan'] = None
    if input_signature(d)!=previous_inputs or body.get('resetAfter')=='inputs':
        invalidate_inputs(w)
        if input_signature(d)==previous_inputs and body.get('detailsOk'):
            d['detailsOk']=True
    elif previous_chosen!=d.get('chosen') or body.get('resetAfter')=='options':
        from app.services.course_recommendations import invalidate_course_tail
        if previous_chosen==d.get('chosen'):
            invalidate_course_tail(w,d.get('chosen'))
        w['draftPlan']=None
    if d.get('quizFail') and d['quizFail'].get('key') != quiz_key(d):
        d['quizFail'] = None


def patch(employee_id: int, draft_id: str, body: dict) -> dict:
    """목표·기획서 요약·세부 사항·응답 등 화면 입력 저장(API-16 · 응답은 API-24 도 같은 동작). 입력이 바뀌면 이후 결과를 초기화한다"""
    def fn(t: db.Tx, w: dict):
        before = dict(w['draft'].get('answers') or {})
        _apply_client(w, body)
        if 'answers' in body and w['draft'].get('quiz') and before != w['draft']['answers']:
            _save_answers(t, draft_id, w['draft'])
    w = _mutate(employee_id, draft_id, fn)
    return present(w, draft_id)


def discard(employee_id: int, draft_id: str) -> None:
    with db.tx() as t:
        _row(t, employee_id, draft_id)
        t.run('DELETE FROM public.projects WHERE project_id = CAST(:p AS uuid)', p=draft_id)
    with _img_lock:
        _images.pop(draft_id, None)


# ── ERD: 진단 회차·문항·응답 ──
def _round(t: db.Tx, draft_id: str, d: dict) -> str:
    saved_key = (d.get('quiz') or {}).get('key') or ''
    legacy_prefix = quiz_rest(d) + '|cert:'
    legacy_cert = saved_key[len(legacy_prefix):] if saved_key.startswith(legacy_prefix) else ''
    certification = catalog.cert_by_code(legacy_cert) if legacy_cert else None
    snap = {'goal': d.get('goal'), 'projectSummary': doc_summary(d) or None, 'certPlan': (certification or {}).get('title')}
    rid = t.val('SELECT diagnostic_round_id FROM public.diagnostic_rounds WHERE project_id = CAST(:p AS uuid) AND round_number = 1', p=draft_id)
    if rid:
        t.run('UPDATE public.diagnostic_rounds SET project_snapshot = :s WHERE diagnostic_round_id = :r', s=db.J(snap), r=rid)
        return str(rid)
    return str(t.val("INSERT INTO public.diagnostic_rounds(project_id, round_number, project_snapshot) VALUES(CAST(:p AS uuid), 1, :s) RETURNING diagnostic_round_id",
                     p=draft_id, s=db.J(snap)))


def _save_questions(t: db.Tx, draft_id: str, d: dict, kind: str = 'PRE') -> None:
    rid = _round(t, draft_id, d)
    t.run('DELETE FROM public.assessment_responses WHERE question_id IN (SELECT question_id FROM public.assessment_questions WHERE diagnostic_round_id = :r AND assessment_type = :k)', r=rid, k=kind)
    t.run('DELETE FROM public.assessment_questions WHERE diagnostic_round_id = :r AND assessment_type = :k', r=rid, k=kind)
    for i, q in enumerate(d['quiz']['questions'], 1):
        q['dbId'] = str(t.val("""INSERT INTO public.assessment_questions(project_id, diagnostic_round_id, assessment_type, skill, question, options, sequence_no)
                                VALUES(CAST(:p AS uuid), :r, :k, :s, :q, :o, :n) RETURNING question_id""",
                             p=draft_id, r=rid, k=kind, s=str(DG.skill_label(q.get('skill') or ''))[:100], q=q['text'], o=db.J([{'value': v, 'label': l} for v, l in D['answerOpts']]), n=i))


def _save_answers(t: db.Tx, draft_id: str, d: dict, kind: str = 'PRE') -> None:
    labels = dict(D['answerOpts'])
    for q in d['quiz']['questions']:
        v = d['answers'].get(q['id'])
        if not q.get('dbId'):
            continue
        if v:
            t.run("""INSERT INTO public.assessment_responses(project_id, question_id, assessment_type, selected_option, score)
                     VALUES(CAST(:p AS uuid), CAST(:q AS uuid), :k, :o, :s)
                     ON CONFLICT (project_id, question_id) DO UPDATE SET selected_option = EXCLUDED.selected_option, score = EXCLUDED.score, answered_at = now()""",
                  p=draft_id, q=q['dbId'], k=kind, o=labels.get(str(v), str(v)), s=int(v))
        else:
            t.run('DELETE FROM public.assessment_responses WHERE project_id = CAST(:p AS uuid) AND question_id = CAST(:q AS uuid)', p=draft_id, q=q['dbId'])


# ── 기획서 (API-20·21) ──
def doc_read(employee_id: int, draft_id: str, name: str, raw: bytes) -> dict:
    try:
        ex = docread.read(name, raw)
    except docread.DocError as e:
        raise AgentError(str(e)).api(422) from e
    with _img_lock:
        _images[draft_id] = ex.get('images') or []

    def fn(t, w):
        invalidate_inputs(w)
        w['draft']['project'] = {'name': name, 'size': len(raw)}
        w['draft']['doc'] = {'name': name, 'status': 'reading', 'step': 'vision', 'fail': None, 'format': ex.get('format'), 'chars': ex.get('chars'),
                             'truncated': ex.get('truncated'), 'pages': ex.get('pages'), 'text': ex.get('text') or '', 'imageTotal': ex.get('imageTotal') or 0,
                             'imageSkipped': ex.get('imageSkipped') or {}, 'imagePicked': len(ex.get('images') or []), 'warnings': ex.get('warnings') or [],
                             'imageNotes': [], 'imagesRead': 0, 'visionWhy': ''}
    return present(_mutate(employee_id, draft_id, fn), draft_id)


def doc_summary_start(employee_id: int, draft_id: str, skip_images: bool = False) -> str:
    """이미지 보기(비전 모델이 있을 때)·요약을 작업으로. 실패는 doc.fail 에 남기고 다시 시도는 사용자가 누를 때만"""
    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        with db.tx() as t:
            w = _wrap(_row(t, employee_id, draft_id, lock=False)['draft_choices'])
        doc = dict(w['draft'].get('doc') or {})
        with _img_lock:
            imgs = list(_images.get(draft_id) or [])
        step = 'vision'
        try:
            if doc.get('imageTotal') and not skip_images and imgs and ctx.live and DOC.vision_model(ctx):
                _set_doc(employee_id, draft_id, {'status': 'reading', 'step': 'vision', 'fail': None})
                v = DOC.vision(ctx, doc['name'], imgs, sim=rt.sim_once(ctx, 'doc', 'vision|' + doc['name'], 'doc'))
                doc.update(imageNotes=v['images'], imagesRead=len(v['images']))
            elif skip_images:
                doc['visionWhy'] = 'skip'
            else:
                doc['visionWhy'] = '' if not doc.get('imageTotal') else 'mock' if not ctx.live else 'none' if not imgs else 'novision' if not DOC.vision_model(ctx) else doc.get('visionWhy', '')
                if doc.get('imageTotal') and not imgs and ctx.live and DOC.vision_model(ctx):
                    doc['visionWhy'] = 'lost'
            step = 'summary'
            if not doc.get('text') and not doc.get('imageNotes'):
                _set_doc(employee_id, draft_id, dict(doc, status='ok', summary='', step='done'))
                return {'ok': True}
            _set_doc(employee_id, draft_id, dict(doc, status='reading', step='summary', fail=None))
            s = DOC.summary(ctx, {'goal': w['draft'].get('goal'), 'name': doc['name'], 'text': doc.get('text'), 'imageNotes': [f"{x['n']}번 이미지: {x['desc']}" for x in doc.get('imageNotes') or []]},
                            sim=rt.sim_once(ctx, 'doc', f"summary|{doc['name']}|{doc.get('chars', 0)}", 'doc'))
        except AgentError as e:
            _set_doc(employee_id, draft_id, dict(doc, status='fail', step=step, fail={'cause': e.info}))
            raise
        _set_doc(employee_id, draft_id, dict(doc, status='ok', step='done', summary=str(s['text'] or '')[:1500], source=ctx.mode, fail=None))
        return {'ok': True}
    _set_doc(employee_id, draft_id, {'status': 'reading', 'fail': None, 'jobId': None})
    work._resume = {'operation':'drafts.doc_summary_start','kwargs':{'employee_id':employee_id,'draft_id':draft_id,'skip_images':skip_images}}
    jid = jobs.start('doc-summary', employee_id, draft_id, work)

    def note_job(t, w):
        doc = w['draft'].get('doc') or {}
        if doc.get('status') == 'reading':
            doc['jobId'] = jid
    _mutate(employee_id, draft_id, note_job)
    return jid


def _set_doc(employee_id: int, draft_id: str, patch_: dict) -> None:
    def fn(t, w):
        before=doc_summary(w['draft'])
        w['draft']['doc'] = dict(w['draft'].get('doc') or {}, **patch_)
        if before!=doc_summary(w['draft']):invalidate_inputs(w)
    _mutate(employee_id, draft_id, fn)


def clear_project(employee_id: int, draft_id: str) -> dict:
    with _img_lock:
        _images.pop(draft_id, None)

    def fn(t, w):
        invalidate_inputs(w)
        w['draft']['project'] = None
        w['draft']['doc'] = None
    return present(_mutate(employee_id, draft_id, fn), draft_id)


# ── 사전 점검 문항 (API-23) ──
def assessment_start(employee_id: int, draft_id: str) -> str | None:
    """문항 생성 작업. 같은 조건으로 이미 만들었거나 만드는 중이면 그대로. 실패 상태여도 사용자가 다시 시도를 누른 것으로 보고 새로 만든다"""
    with db.tx() as t:
        w = _wrap(_row(t, employee_id, draft_id)['draft_choices'])
        d = w['draft']
        key = quiz_key(d)
        if d.get('quiz') and d['quiz']['key'] == key:
            return None
        if d.get('quizRun') and d['quizRun'].get('key') == key:
            st = db.val("SELECT status FROM app_ext.jobs WHERE job_id = CAST(:j AS uuid)", j=d['quizRun']['jobId'])
            if st == 'running':
                return d['quizRun']['jobId']
        inp = {'goal': d['goal'], 'project': (d.get('project') or {}).get('name') if d.get('project') else None, 'projectSummary': doc_summary(d) or None,
               'certPlan': None}
        base = {'goal': d['goal'], 'project': copy.deepcopy(d.get('project')), 'doc': copy.deepcopy(d.get('doc')) if (d.get('doc') or {}).get('status') == 'ok' else None}

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        try:
            r = DG.questions(ctx, inp, sim=rt.sim_once(ctx, 'quiz', key))
        except AgentError as e:
            def fail(t, w):
                if quiz_key(w['draft']) == key:
                    w['draft']['quizFail'] = {'key': key, 'cause': e.info}
                    w['draft']['quizRun'] = None
            _mutate(employee_id, draft_id, fail)
            raise

        def ok(t, w):
            d2 = w['draft']
            if quiz_key(d2) != key:
                return
            clear_from(d2, 'quiz')
            d2['quiz'] = {'key': key, 'questions': r['questions'], 'domain': r['domain'], 'base': base, 'deep': r.get('deep')}
            _save_questions(t, draft_id, d2)
        _mutate(employee_id, draft_id, ok)
        return {'ok': True}

    def mark(t, w):
        w['draft']['quizFail'] = None
        w['draft']['quizRun'] = {'key': key, 'jobId': None}
    _mutate(employee_id, draft_id, mark)
    work._resume = {'operation':'drafts.assessment_start','kwargs':{'employee_id':employee_id,'draft_id':draft_id}}
    jid = jobs.start('assessment', employee_id, draft_id, work)

    def note_job(t, w):
        if (w['draft'].get('quizRun') or {}).get('key') == key:
            w['draft']['quizRun']['jobId'] = jid
    _mutate(employee_id, draft_id, note_job)
    return jid


# ── 수준 진단 (API-25) ──
def diagnosis_start(employee_id: int, draft_id: str) -> str | None:
    with db.tx() as t:
        w = _wrap(_row(t, employee_id, draft_id)['draft_choices'])
        d = w['draft']
        if not d.get('quiz') or not all(d['answers'].get(q['id']) for q in d['quiz']['questions']):
            raise ApiError(409, 'QUIZ_INCOMPLETE', '사전 점검 문항에 모두 답해 주세요')
        if deep_on(d) and not DC.complete(d['quiz']['deep'], d.get('deepMcq')):
            raise ApiError(409, 'DEEP_INCOMPLETE', '심화 질문의 객관식에 모두 답해 주세요(‘잘 모르겠어요’도 돼요)')
        key = diag_key(d)
        if d.get('diag') and d['diag']['key'] == key:
            return None
        if d.get('diagRun') and d['diagRun'].get('key') == key and db.val("SELECT status FROM app_ext.jobs WHERE job_id = CAST(:j AS uuid)", j=d['diagRun']['jobId']) == 'running':
            return d['diagRun']['jobId']
        prefs = dict(d['prefs'], certRes=cert_res(d['prefs']))
        inp = {'goal': d['goal'], 'project': (d.get('project') or {}).get('name') if d.get('project') else None, 'projectSummary': doc_summary(d) or None,
               'prefs': prefs, 'prefSummary': pref_summary(d['prefs']), 'questions': d['quiz']['questions'], 'answers': dict(d['answers'])}
        if deep_on(d):
            inp['deep'] = {'quiz': d['quiz']['deep'], 'mcq': dict(d.get('deepMcq') or {}), 'essay': dict(d.get('deepEssay') or {})}

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        try:
            r = DG.assess(ctx, inp, sim=rt.sim_once(ctx, 'diag', key))
        except AgentError as e:
            def fail(t, w):
                if diag_key(w['draft']) == key:
                    w['draft']['diagFail'] = {'key': key, 'cause': e.info}
                    w['draft']['diagRun'] = None
            _mutate(employee_id, draft_id, fail)
            raise

        def ok(t, w):
            d2 = w['draft']
            if diag_key(d2) != key:
                return
            d2['diagFail'] = None
            d2['diagRun'] = None
            d2['diag'] = dict({'key': key, 'answers': dict(d2['answers'])}, **r)
            if inp.get('deep'):
                # 되돌리기(changes_revert)용: 진단에 쓴 심화 답
                d2['diag']['deepAnswers'] = {'mcq': inp['deep']['mcq'], 'essay': inp['deep']['essay']}
            rid = _round(t, draft_id, d2)
            t.run('UPDATE public.diagnostic_rounds SET diagnostic_result = :r, pre_completed_at = now() WHERE diagnostic_round_id = CAST(:i AS uuid)', r=db.J(d2['diag']), i=rid)
        _mutate(employee_id, draft_id, ok)
        return {'ok': True}

    def mark(t, w):
        w['draft']['diagFail'] = None
        w['draft']['diagRun'] = {'key': key, 'jobId': None}
    _mutate(employee_id, draft_id, mark)
    work._resume = {'operation':'drafts.diagnosis_start','kwargs':{'employee_id':employee_id,'draft_id':draft_id}}
    jid = jobs.start('diagnosis', employee_id, draft_id, work)

    def note_job(t, w):
        if (w['draft'].get('diagRun') or {}).get('key') == key:
            w['draft']['diagRun']['jobId'] = jid
    _mutate(employee_id, draft_id, note_job)
    return jid


# ── 앞 단계를 고쳤을 때 (API-17·18) ──
def changes_apply(employee_id: int, draft_id: str, kind: str) -> dict:
    def fn(t, w):
        clear_from(w['draft'], 'gen' if kind == 'gen' else kind)
        w['draftPlan'] = None
    return present(_mutate(employee_id, draft_id, fn), draft_id)


def changes_revert(employee_id: int, draft_id: str, kind: str) -> dict:
    def fn(t, w):
        d = w['draft']
        if kind == 'quiz' and d.get('quiz') and d['quiz'].get('base'):
            b = d['quiz']['base']
            d['goal'], d['project'], d['doc'] = b['goal'], copy.deepcopy(b.get('project')), copy.deepcopy(b.get('doc'))
            d['quizFail'] = None
        elif kind == 'diag' and d.get('diag'):
            d['answers'] = dict(d['diag']['answers'])
            da = d['diag'].get('deepAnswers')
            d['deepOn'] = bool(da)
            if da:
                d['deepMcq'], d['deepEssay'] = dict(da['mcq']), dict(da['essay'])
            _save_answers(t, draft_id, d)
        elif kind == 'gen' and d.get('genPrefs'):
            d['prefs'] = copy.deepcopy(d['genPrefs'])
            d['detailsOk'] = True
    return present(_mutate(employee_id, draft_id, fn), draft_id)


# ── 점검 결과 수정 (API-26) ──
def overrides(employee_id: int, draft_id: str, body: dict) -> dict:
    """직접 고친 항목만 fix 에 둔다. 바뀌었고 3안이 있으면 3안을 버린다(화면이 먼저 확인창을 띄움)"""
    def fn(t, w):
        d = w['draft']
        a = d['diag']
        start = int(body.get('start') or a['startStage'])
        vals = {'competencies': body.get('competencies') or [], 'resourceIds': body.get('resourceIds') or [], 'outcome': str(body.get('outcome') or '').strip(), 'known': body.get('known') or []}
        if not vals['competencies'] or not vals['outcome']:
            raise ApiError(422, 'EDIT_MISSING', '익히게 될 역량과 만들 결과물은 비울 수 없어요')
        same = lambda k: sorted(vals[k]) == sorted(a[k] or []) if k == 'resourceIds' else vals[k] == a[k]  # noqa: E731
        fix = {k: vals[k] for k, _ in FIX if not same(k)}
        nxt = {'startStage': None if start == a['startStage'] else start, 'fix': fix or None, 'prefs': body.get('prefs') or d['prefs']}
        changed = json.dumps([d.get('startStage'), d.get('fix'), d['prefs']], sort_keys=True, ensure_ascii=False) != json.dumps([nxt['startStage'], nxt['fix'], nxt['prefs']], sort_keys=True, ensure_ascii=False)
        d.update(nxt, edit=None)
        if changed and (d.get('handoff') or d.get('gen')):
            clear_from(d, 'gen')
            w['draftPlan'] = None
        return {'changed': changed}
    out = {}

    def wrap(t, w):
        out.update(fn(t, w))
    w = _mutate(employee_id, draft_id, wrap)
    return dict(present(w, draft_id), changed=out.get('changed'))


# ── 3안 (API-27~33) ──
def education_guide(employee_id: int, draft_id: str) -> dict:
    """생성 화면에서 요청한 공통 근거를 초안에 한 번만 기록한다. 동시 요청도 같은 행을 잠근다."""
    with db.tx() as t:
        w = _wrap(_row(t, employee_id, draft_id)['draft_choices'])
        draft = w['draft']
        if not draft.get('genRun') and not draft.get('gen'):
            raise ApiError(409, 'GENERATION_REQUIRED', '로드맵 생성이 시작된 뒤 확인할 수 있어요.')
        if 'educationGuide' not in draft:
            draft['educationGuide'] = REG.education_guide(t, PF.employee_group(employee_id, t=t))
            _write(t, draft_id, w)
        return draft['educationGuide']


def options_start(employee_id: int, draft_id: str) -> dict:
    """전달 내용 확정 + 3안 병렬 작성 시작(API-27). 같은 내용으로 세 안을 모두 받은 적이 있으면 그 결과를 쓴다"""
    jids, pending = {}, []
    work_info = DG.work_profile(PF.view(employee_id))  # 업무 정보가 바뀌면 전달 내용 키도 바뀌어 3안을 새로 만든다

    def fn(t, w):
        d = w['draft']
        if w.get('v2Survey'):
            from app.routers.preassessment import recommendation_context
            from app.services.planning_handoff import build_handoff as build_v2_handoff
            saved = recommendation_context(t, employee_id, draft_id)
            try:
                h = build_v2_handoff(saved, handoff_prefs(d['prefs']), work_info)
            except ValueError as error:
                raise ApiError(422, 'PLAN_INPUT_INVALID', str(error)) from error
        else:
            if not d.get('diag') or d['diag']['key'] != diag_key(d):
                raise ApiError(409, 'DIAG_REQUIRED', '점검 결과를 먼저 정리해 주세요')
            h = build_handoff(d, work_info)
        _heal(t, w)
        if (d.get('gen') or {}).get('key') != h['key'] and (d.get('genRun') or {}).get('key') != h['key']:
            d.update(gen=None, chosen=None, genRun=None)
            w['draftPlan'] = None
        d['handoff'] = h
        d['genPrefs'] = copy.deepcopy(d['prefs'])
        rid = _round(t, draft_id, d)
        t.run('UPDATE public.diagnostic_rounds SET agent_input = :h WHERE diagnostic_round_id = CAST(:r AS uuid)', h=db.J(h), r=rid)
        if not d.get('genRun') or d['genRun'].get('key') != h['key']:
            if d.get('gen'):
                return
            # 아직 작업이 없는 안은 실행 중으로 표시하지 않는다.
            d['genRun'] = {'key': h['key'], 'rows': {pid: {'st': 'fail', 'tries': 0, 'out': None, 'err': None, 'jobId': None} for pid in D['optionOrder']}}
        pending.extend((pid, h['key']) for pid, row in d['genRun']['rows'].items() if row.get('st') == 'fail')
    w = _mutate(employee_id, draft_id, fn)
    for pid, key in pending:
        try:
            jids[pid] = _run_option(employee_id, draft_id, pid, expected_key=key)
        except ApiError as error:
            if error.code not in ('OPTION_RUNNING', 'OPTION_READY', 'STALE_RUN'):
                raise
    if pending:
        w = _mutate(employee_id, draft_id, lambda t, w: None)
    return dict(present(w, draft_id), jobs=jids)


def _run_option(employee_id: int, draft_id: str, pid: str, *, expected_key: str | None = None) -> str:
    # 작업 ID와 실행 상태를 같은 행 잠금 안에서 저장한 뒤 워커를 시작한다.
    info: dict = {}

    def mark(jid: str) -> None:
        def save_run(t, w2):
            _heal(t, w2)
            r = w2['draft'].get('genRun')
            if not r or (expected_key is not None and r['key'] != expected_key):
                raise ApiError(409, 'STALE_RUN', '입력이 바뀌었어요. 현재 계획을 확인해 주세요')
            row = r['rows'][pid]
            if row.get('st') == 'run':
                raise ApiError(409, 'OPTION_RUNNING', '이미 작성 중인 계획이에요')
            if row.get('st') == 'ok':
                raise ApiError(409, 'OPTION_READY', '이미 작성된 계획이에요')
            # startedAt(밀리초): 화면의 '기다린 시간'이 화면을 다시 열어도 처음 요청한 때부터 이어서 세도록 서버가 기록한다
            row.update(st='run', err=None, jobId=jid, tries=(row.get('tries') or 0) + 1, startedAt=int(time.time() * 1000))
            info.update(h=copy.deepcopy(w2['draft']['handoff']), key=r['key'], tries=row['tries'], jid=jid)
        _mutate(employee_id, draft_id, save_run)

    def work(job: jobs.JobCtx):
        h, key, tries = info['h'], info['key'], info['tries']
        ctx = rt.context(employee_id)
        sim = rt.SIM_ERR['openai' if ctx.provider == 'openai' else 'ollama'][pid] if ctx.fail_sim.get('gen') and pid in ('A2', 'A3') and tries == 1 else None
        out, failure = None, None
        try:
            out = RM.option(ctx, {'pid': pid, 'handoff': h}, sim=sim)
        except (AgentError, ApiError) as error:
            failure = error

        def save(t, w2):
            r = w2['draft'].get('genRun')
            if not r or r['key'] != key:
                return
            row = r['rows'][pid]
            if row.get('jobId') != job.job_id or row.get('tries') != tries:
                return
            row.update(st='ok' if out else 'fail', out=out, err=jobs.error_info(failure) if failure else None, jobId=None)
            rows = [r['rows'][x] for x in D['optionOrder']]
            d2 = w2['draft']
            current = d2.get('gen')
            if out and current and current['key'] == key and pid in (current.get('missing') or []):
                current['options'][pid] = out
                current['missing'] = [name for name in current['missing'] if name != pid]
            if not any(x['st'] == 'run' for x in rows) and all(x['st'] == 'ok' for x in rows) and (not d2.get('gen') or d2['gen'].get('key') != key):
                d2['gen'] = {'key': key, 'options': {x: r['rows'][x]['out'] for x in D['optionOrder']}, 'missing': []}
        updated = _mutate(employee_id, draft_id, save)
        if updated.get("v2Survey"):
            from app.services.material_preparation import prepare as prepare_materials
            prepare_materials(employee_id,draft_id)
        if failure:
            raise failure
        return {'pid': pid}
    try:
        work._resume = {'operation':'drafts.option_retry','kwargs':{'employee_id':employee_id,'draft_id':draft_id,'pid':pid},'inputKey':expected_key}
        return jobs.start('option', employee_id, f'{draft_id}:{pid}', work, before_start=mark)
    except Exception:
        if info:
            def failed_start(t, w2):
                r = w2['draft'].get('genRun')
                row = (r or {}).get('rows', {}).get(pid) or {}
                if r and r['key'] == info['key'] and row.get('jobId') == info['jid']:
                    row.update(st='fail', jobId=None, err=cause('작업을 시작하지 못했어요. 다시 시도해 주세요.'))
            _mutate(employee_id, draft_id, failed_start)
        raise


def option_retry(employee_id: int, draft_id: str, pid: str) -> dict:
    """실패한 안만 다시 작성(API-29 · 사용자가 누를 때만)"""
    w = _mutate(employee_id, draft_id, _heal)
    r = w['draft'].get('genRun')
    if not r or (r['rows'].get(pid) or {}).get('st') != 'fail':
        raise ApiError(409, 'NOT_FAILED', '다시 작성할 안이 없어요')
    jid = _run_option(employee_id, draft_id, pid, expected_key=r['key'])
    return dict(get(employee_id, draft_id), jobs={pid: jid})


def accept_partial(employee_id: int, draft_id: str) -> dict:
    """작성된 안만으로 진행(API-30). 실패한 안은 저장하지 않는다"""
    with db.tx() as t:
        w = _wrap(_row(t, employee_id, draft_id)['draft_choices'])
        d = w['draft']
        r = d.get('genRun')
        if not r:
            raise ApiError(409, 'NOTHING_TO_ACCEPT', '작성된 안이 없어요')
        # 같은 생성 결과를 다시 수락해도 비교표에서 고른 버전과 계획을 보존한다.
        gen = d.get('gen')
        already_accepted = gen is not None and gen.get('key') == r['key']
        if not already_accepted:
            _heal(t, w)
            rows = {pid: r['rows'][pid] for pid in D['optionOrder']}
            if any(row['st'] == 'run' for row in rows.values()) or not any(row['st'] == 'ok' for row in rows.values()):
                raise ApiError(409, 'NOTHING_TO_ACCEPT', '작성된 안이 없어요')
            d['gen'] = {'key': r['key'], 'options': {pid: row['out'] for pid, row in rows.items() if row['st'] == 'ok'},
                        'missing': [pid for pid, row in rows.items() if row['st'] != 'ok']}
            d['chosen'] = None
            w['draftPlan'] = None
            _write(t, draft_id, w)
    if not already_accepted and w.get("v2Survey"):
        from app.services.material_preparation import prepare as prepare_materials
        prepare_materials(employee_id,draft_id)
    return present(w, draft_id)


def _sync(g: dict) -> None:
    for pid, lst in (g.get('hist') or {}).items():
        i = (g.get('cur') or {}).get(pid, 0)
        if lst and i < len(lst):
            g['options'][pid] = lst[i]


def _hist(g: dict, pid: str) -> list:
    g.setdefault('hist', {})
    g.setdefault('cur', {})
    if pid not in g['hist']:
        g['hist'][pid] = [g['options'][pid]]
        g['cur'][pid] = 0
    return g['hist'][pid]


def regenerate(employee_id: int, draft_id: str, pid: str, req: dict | None) -> dict:
    """이 안만 다시 만들기(API-32 · 요청 반영 · 새 버전). 실패하면 이전 안을 그대로 둔다"""
    def mark(t, w):
        g = w['draft'].get('gen')
        if not g or pid not in g['options']:
            raise ApiError(409, 'NO_OPTION', '다시 만들 안이 없어요')
        if (g.get('regenRun') or {}).get(pid):raise ApiError(409,'REGEN_RUNNING','해당 계획을 이미 다시 생성하고 있어요.')
        _sync(g)
        from app.services.course_recommendations import archive_course_cache
        archive_course_cache(w,pid)
        lst = _hist(g, pid)
        g.setdefault('regenRun', {})[pid] = {'req': req, 'from': g['cur'].get(pid, 0), 'err': None}
        g.setdefault('regenErr', {}).pop(pid, None)
        return {'prev': copy.deepcopy(g['options'][pid]), 'variant': len(lst), 'handoff': w['draft']['handoff'], 'key': g['key']}
    info = {}
    _mutate(employee_id, draft_id, lambda t, w: info.update(mark(t, w)))
    prev = info['prev']

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        try:
            o = RM.option(ctx, {'pid': pid, 'handoff': info['handoff'], 'variant': info['variant'], 'request': req, 'previousDef': prev,
                                'previous': {'tagline': prev['tagline'], 'acts': [dict({'key': a['id'], 'stage': a['stage'], 'title': a['title'], 'res': a.get('res'), 'hours': a.get('hours')},
                                                                                       **({} if a.get('res') else {'skills': a.get('skills') or []})) for a in prev['acts']]}})
        except (AgentError, ApiError) as error:
            err = jobs.error_info(error)
            def fail(t, w):
                g = w['draft'].get('gen')
                if g and g['key'] == info['key']:
                    (g.get('regenRun') or {}).pop(pid, None)
                    g.setdefault('regenErr', {})[pid] = err
            _mutate(employee_id, draft_id, fail)
            raise
        req_text = ' · '.join(x for x in [req.get('wish') if req else '', ', '.join((req or {}).get('quick') or []),
                                         ('빼기: ' + ', '.join(x['title'] for x in req['removeActs'])) if req and req.get('removeActs') else '',
                                         ('바꾸기: ' + ', '.join(x['title'] for x in req['replaceActs'])) if req and req.get('replaceActs') else ''] if x)
        o['revRequest'] = req_text if req else ''
        o['revSummary'] = o.pop('summary', '') or ('' if req else '같은 관점으로 활동 구성을 바꿔 새로 썼어요')
        o['revNotes'] = o.pop('notes', [])

        def ok(t, w):
            g = w['draft'].get('gen')
            if not g or g['key'] != info['key']:
                return
            _sync(g)
            from app.services.course_recommendations import archive_course_cache
            archive_course_cache(w,pid)
            lst = _hist(g, pid)
            lst.append(o)
            if len(lst) > 6:
                del lst[1]  # 처음 안과 최근 다섯 버전만 둔다
            g['cur'][pid] = len(lst) - 1
            g['options'][pid] = lst[-1]
            from app.services.course_recommendations import invalidate_course_tail
            invalidate_course_tail(w,pid)
            from app.services.course_recommendations import prune_course_versions
            prune_course_versions(w,pid)
            (g.get('regenRun') or {}).pop(pid, None)
            if w.get('draftPlan') and w['draftPlan'].get('opt') == pid:
                w['draftPlan'] = None
        updated = _mutate(employee_id, draft_id, ok)
        if updated.get("v2Survey"):
            from app.services.material_preparation import prepare as prepare_materials
            prepare_materials(employee_id,draft_id,[pid])
        return {'pid': pid, 'version': info['variant'] + 1}
    work._resume = {'operation':'drafts.regenerate','kwargs':{'employee_id':employee_id,'draft_id':draft_id,'pid':pid,'req':req}}
    jid = jobs.start('regenerate', employee_id, f'{draft_id}:{pid}', work)

    def note_job(t, w):
        g = w['draft'].get('gen')
        if g and (g.get('regenRun') or {}).get(pid):
            g['regenRun'][pid]['jobId'] = jid
    w = _mutate(employee_id, draft_id, note_job)
    return dict(present(w, draft_id), jobs={pid: jid})


def select(employee_id: int, draft_id: str, pid: str, displayed: list | None = None) -> dict:
    """안 선택 → 검토용 계획(API-34)"""
    def fn(t, w):
        d = w['draft']
        g = d.get('gen')
        if not g or pid not in g['options']:
            raise ApiError(409, 'NO_OPTION', '고를 안이 없어요')
        if (g.get('regenRun') or {}).get(pid):
            raise ApiError(409, 'REGEN_RUNNING', '그 안을 다시 쓰는 중이에요. 잠시 뒤에 골라 주세요')
        _sync(g)
        from app.services.prompt_selection_store import comparison_snapshot
        d['selectionComparison'] = comparison_snapshot(g, displayed)
        # Course caches are scoped by option; selecting a course must preserve its materials.
        d['chosen'] = pid
        o = g['options'][pid]
        w['draftPlan'] = RM.build_plan(o, RM.params_of(d['handoff'], o), d['goal'])
        w['lastNew'] = 'new-materials'
    return present(_mutate(employee_id, draft_id, fn), draft_id)


def selection_of(d: dict) -> dict:
    name = course_name(d['id'], d['name'])
    return {'perspective': d['id'], 'name': name, 'agent': f"로드맵 계획 에이전트 · {d['id']} {name}", 'source': d.get('source'), 'at': today()}


def confirm(employee_id: int, draft_id: str, start_mode: str | None = None) -> dict:
    """개인 로드맵 확정(API-35 · 기관 승인·결재 아님). 고르지 않은 안·버전은 버린다.
    진행 중인 다른 로드맵은 start_mode 대로: together(기본 · 그대로 함께) · after(모두 끝난 다음 주부터 시작) · archive(같은 트랜잭션에서 보관)"""
    _check_start_mode(start_mode)
    mode = 'together' if start_mode is None else start_mode
    active =PL.active_rows(employee_id) if mode != 'together' else []
    with db.tx() as t:
        r = _row(t, employee_id, draft_id)
        w = _wrap(r['draft_choices'])
        d = w['draft']
        demo_seeded = w.get('demoSeeded') is True
        if demo_seeded and mode == 'archive':
            raise ApiError(409, 'DEMO_ARCHIVE_FORBIDDEN', '시연 초안은 기존 로드맵을 보관할 수 없어요. 다른 시작 방식을 골라 주세요.')
        if not w.get('draftPlan') or not d.get('chosen'):
            raise ApiError(409, 'NOT_SELECTED', '확정할 안을 먼저 골라 주세요')
        g = d['gen']
        _sync(g)
        assessment = w.get('v2Survey')
        final_handoff = copy.deepcopy(d['handoff'])
        if assessment:
            from app.services.activity_selection import context as activity_context, current_record, selection_option
            assessment, _ = activity_context(t, employee_id, draft_id)
            proposal = current_record(assessment, d)
            o = selection_option(assessment, d, (proposal or {}).get('selectedIds') or [])
            if assessment.get('skillSelectionKey'):
                names=list(assessment['skillOrder'])
                final_handoff.update(focus=names,skillNames=names,skillOrder=names,
                    skillDetails=copy.deepcopy(assessment['selection']['skills']),
                    skillMaterials=copy.deepcopy(assessment['resourceChoices']),
                    excludedSkills=[name for name in d['handoff'].get('skillNames',[]) if name not in names])
        else:
            o = g['options'][d['chosen']]
        plan = RM.build_plan(o, RM.params_of(d['handoff'], o), d['goal'])
        validate_free_plan(t, plan)
        if assessment:
            questions = [dict(q, skill=group['skill'], area=group['skill']) for group in assessment['survey']['groups'] for q in group['surveys']]
            answers = {q['id']: str(assessment['answers'][q['id']]) for q in questions}
            capture = dict(d, quiz={'questions': questions, 'domain': ' · '.join(final_handoff['focus'])}, answers=answers)
            _save_questions(t, draft_id, capture)
            _save_answers(t, draft_id, capture)
            assess = {'questions': questions, 'answers': answers, 'domain': capture['quiz']['domain'],
                'v2': {'survey': copy.deepcopy(assessment['survey']), 'answers': copy.deepcopy(assessment['answers'])}}
        else:
            assess = {'questions': d['quiz']['questions'], 'answers': dict(d['answers']), 'domain': d['quiz']['domain']}
        if not assessment and deep_on(d) and (d.get('diag') or {}).get('deep'):
            # 심화 질문(사전): 사후 점검 비교와 결과 보고서용. 부서장 화면에는 보내지 않는다(plans.record for_mgr 가 assess 를 비움)
            assess['deep'] = {'on': True, 'quiz': d['quiz']['deep'], 'mcq': dict(d.get('deepMcq') or {}), 'essay': dict(d.get('deepEssay') or {}),
                              'grade': d['diag']['deep']['grade'], 'judge': d['diag']['deep']['judge']}
        plan.update(version=1, confirmedAt=today(), why='최초 확정', assess=assess,
                    prefs=copy.deepcopy(d['prefs']), handoff=final_handoff, selection=selection_of(o))
        from app.services.prompt_selection_store import confirmation_evidence
        evidence = confirmation_evidence(str(draft_id), d)
        if evidence:
            plan['selectionEvidence'] = evidence
        start_date = PL.next_start(active) if mode == 'after' else None
        if start_date:
            plan['startDate'] = start_date
        rid = _round(t, draft_id, d)
        roadmap_id = PL.insert_roadmap(t, draft_id, rid, plan)
        if mode == 'archive':
            # active 를 읽은 뒤 다른 요청이 마친 로드맵은 archive_row 가 건너뛴다. 새 로드맵 확정은 그대로 진행한다
            for row in active:
                PL.archive_row(t, row)
        confirmed = {'gp5': 1, 'confirmed': True, 'roadmapId': roadmap_id}
        if demo_seeded:
            confirmed['demoSeeded'] = True
        t.run("""UPDATE public.projects SET status = 'IN_PROGRESS', current_stage = 7, draft_choices = :w, updated_at = now() WHERE project_id = CAST(:p AS uuid)""",
              w=db.J(confirmed), p=draft_id)
        if not demo_seeded:
            NT.roadmap_created(t, employee_id, roadmap_id)
        NT.draft_confirmed(t, employee_id, draft_id)
    with _img_lock:
        _images.pop(draft_id, None)
    from app.services.post_quiz import prepare as prepare_post_quiz
    prepare_post_quiz(employee_id,roadmap_id,plan)
    return {'planId': roadmap_id, 'version': 1, 'selection': plan['selection'], 'sharedWith': PL.shared_with(employee_id)}

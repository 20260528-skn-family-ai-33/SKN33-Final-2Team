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
from datetime import date

from .. import catalog, db, docread, jobs, regstore
from ..agents import deepcheck as DC
from ..agents import diag as DG
from ..agents import doc as DOC
from ..agents import regulation as REG
from ..agents import roadmap as RM
from ..agents import runtime as rt
from ..agents.demo import D
from ..errors import AgentError, ApiError, not_found
from ..free_track import validate_free_plan
from . import plans as PL
from . import profile as PF

STEP_ROUTES = ['new-goal', 'new-details', 'new-details-check', 'new-quiz', 'new-result', 'new-result-edit', 'new-gen', 'new-options', 'new-review']
# deepOn·deepMcq·deepEssay: 심화 질문을 풀지(체크)와 객관식·서술형 답(10/23)
CLIENT_KEYS = ('goal', 'project', 'prefs', 'detailsOk', 'answers', 'deepOn', 'deepMcq', 'deepEssay', 'chosen', 'edit', 'lastNew')
_images: dict[str, list] = {}   # 기획서 이미지(base64)는 DB에 넣지 않고 서버 메모리에만 잠깐 둔다
_img_lock = threading.Lock()


def fresh_draft() -> dict:
    return {'goal': '', 'project': None, 'prefs': {'format': '', 'cert': '', 'hours': '', 'weeks': '', 'budget': '', 'etc': ''}, 'detailsOk': False,
            'quiz': None, 'answers': {}, 'deepOn': False, 'deepMcq': {}, 'deepEssay': {}, 'diag': None, 'startStage': None, 'fix': None, 'edit': None, 'handoff': None, 'gen': None, 'chosen': None,
            'quizFail': None, 'diagFail': None, 'genRun': None, 'doc': None, 'genPrefs': None, 'quizRun': None, 'diagRun': None}


def today() -> str:
    return date.today().isoformat()


# ── 4차 계산 그대로 (gp-app.js · gp-parts.js) ──
def doc_summary(d: dict) -> str:
    doc = d.get('doc') or {}
    return str(doc.get('summary') or '').strip() if doc.get('status') == 'ok' else ''


def cert_key(p: dict) -> str:
    return p.get('cert') or '' if catalog.cert_by_code(p.get('cert')) else ''


def quiz_rest(d: dict) -> str:
    return f"{(d.get('goal') or '').strip()}|{(d.get('project') or {}).get('name', '') if d.get('project') else ''}|{doc_summary(d)}"


def quiz_key(d: dict) -> str:
    ck = cert_key(d.get('prefs') or {})
    return quiz_rest(d) + (f'|cert:{ck}' if ck else '')


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
    c = catalog.cert_by_code(p.get('cert'))
    return c['id'] if c else None


def handoff_prefs(p: dict) -> dict:
    budget = None if blank(p.get('budget')) else max(0, int(num(p.get('budget'))))
    hours = num(p.get('hours'))
    weeks = num(p.get('weeks'))
    return {'format': pref_text('format', p), 'formatKey': p.get('format') or 'auto', 'certPlan': pref_text('cert', p), 'certRes': cert_res(p),
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


def _basis_ids(w: dict) -> list[str]:
    ids = []
    for o in list(((w['draft'].get('gen') or {}).get('options') or {}).values()) + [o for l in ((w['draft'].get('gen') or {}).get('hist') or {}).values() for o in l]:
        ids += list((o.get('support') or {}).get('basis') or [])
    return ids


def present(w: dict | None, draft_id: str | None) -> dict:
    """화면에 줄 모양: 작성 문서 + 쓰인 자료·규정 근거"""
    if not w:
        return {'draftId': None, 'draft': None, 'draftPlan': None, 'lastNew': None, 'res': {}, 'reg': {'articles': {}, 'regs': {}}}
    d = w['draft']
    q = d.get('quiz')
    if q and q.get('deep'):
        # 심화 질문 정답·해설·모범 답안은 점검 결과가 나온 뒤에만 보낸다(10/23 · 화면에서는 접어 둠)
        d = dict(d, quiz=dict(q, deep=DC.public(q['deep'], bool((d.get('diag') or {}).get('deep')))))
    return {'draftId': draft_id, 'draft': d, 'draftPlan': w.get('draftPlan'), 'lastNew': w.get('lastNew'),
            'res': catalog.resources_for(_res_keys(w)), 'reg': regstore.bundle(_basis_ids(w))}


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
    if all(i in live for i in ids):
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
        if row and row.get('st') == 'run' and row.get('jobId') and row['jobId'] not in live:
            row.update(st='fail', err=lost, jobId=None)
    g = d.get('gen') or {}
    for pid, x in list((g.get('regenRun') or {}).items()):
        if x and x.get('jobId') and x['jobId'] not in live:
            g['regenRun'].pop(pid)
            g.setdefault('regenErr', {})[pid] = lost


def _healed(employee_id: int, draft_id: str, w: dict) -> dict:
    ids = _run_jobs(w)
    if ids and not all(i in jobs.alive(ids) for i in ids):
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


def _apply_client(w: dict, body: dict) -> None:
    d = w['draft']
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
            if lst and 0 <= int(i) < len(lst):
                g.setdefault('cur', {})[pid] = int(i)
                g['options'][pid] = lst[int(i)]
                if w.get('draftPlan') and w['draftPlan'].get('opt') == pid:
                    w['draftPlan'] = None
    if d.get('quizFail') and d['quizFail'].get('key') != quiz_key(d):
        d['quizFail'] = None


def patch(employee_id: int, draft_id: str, body: dict) -> dict:
    """목표·기획서 요약·세부 사항·응답 등 화면 입력 저장(API-16 · 응답은 API-24 도 같은 동작). 뒤 단계 결과는 지우지 않는다"""
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
    snap = {'goal': d.get('goal'), 'projectSummary': doc_summary(d) or None, 'certPlan': catalog.cert_by_code((d.get('prefs') or {}).get('cert')) and pref_text('cert', d['prefs'])}
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


def _save_answers(t: db.Tx, draft_id: str, d: dict) -> None:
    labels = dict(D['answerOpts'])
    for q in d['quiz']['questions']:
        v = d['answers'].get(q['id'])
        if not q.get('dbId'):
            continue
        if v:
            t.run("""INSERT INTO public.assessment_responses(project_id, question_id, assessment_type, selected_option, score)
                     VALUES(CAST(:p AS uuid), CAST(:q AS uuid), 'PRE', :o, :s)
                     ON CONFLICT (project_id, question_id) DO UPDATE SET selected_option = EXCLUDED.selected_option, score = EXCLUDED.score, answered_at = now()""",
                  p=draft_id, q=q['dbId'], o=labels.get(str(v), str(v)), s=int(v))
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
        _set_doc(employee_id, draft_id, dict(doc, status='ok', step='done', summary=s['text'], source=ctx.mode, fail=None))
        return {'ok': True}
    _set_doc(employee_id, draft_id, {'status': 'reading', 'fail': None, 'jobId': None})
    jid = jobs.start('doc-summary', employee_id, draft_id, work)

    def note_job(t, w):
        doc = w['draft'].get('doc') or {}
        if doc.get('status') == 'reading':
            doc['jobId'] = jid
    _mutate(employee_id, draft_id, note_job)
    return jid


def _set_doc(employee_id: int, draft_id: str, patch_: dict) -> None:
    def fn(t, w):
        w['draft']['doc'] = dict(w['draft'].get('doc') or {}, **patch_)
    _mutate(employee_id, draft_id, fn)


def clear_project(employee_id: int, draft_id: str) -> dict:
    with _img_lock:
        _images.pop(draft_id, None)

    def fn(t, w):
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
               'certPlan': (catalog.cert_by_code(d['prefs'].get('cert')) or {}).get('title')}
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
            d['prefs']['cert'] = (str(d['quiz']['key']).split('|cert:') + [''])[1]
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
def _sup_input(pid: str, name: str, pl: dict) -> dict:
    items = catalog.items()
    used = list(dict.fromkeys(a['res'] for a in pl['acts'] if a.get('res')))
    paid = [r for r in used if (items.get(r) or {}).get('cost')]
    unknown = [r for r in used if r in items and items[r]['cost'] is None and items[r]['kind'] != '자격']
    cert = next((a['res'] for a in pl['acts'] if a.get('res') and (items.get(a['res']) or {}).get('kind') == '자격'), None)
    view = lambda r: {'title': items[r]['title'], 'provider': items[r]['provider'], 'costWon': items[r]['cost'], 'kind': items[r]['kind']}  # noqa: E731
    return {'pid': pid, 'name': f'{pid} {name}', 'weeks': pl['weeks'], 'weeklyHours': pl['hours'], 'totalCostWon': pl['cost'],
            'paidResources': [view(r) for r in paid], 'unknownCostResources': [view(r) for r in unknown], 'certification': items[cert]['title'] if cert else None,
            'onlineOnly': True}


def _plans_brief(employee_id: int) -> list:
    return [{'goal': r['plan']['goal'], 'name': r['plan']['name'], 'weeklyHours': r['plan']['hours'], 'costWon': r['plan']['cost']}
            for r in PL.records(employee_id, statuses=('active',)).values()]


def options_start(employee_id: int, draft_id: str) -> dict:
    """전달 내용 확정 + 3안 병렬 작성 시작(API-27). 같은 내용으로 세 안을 모두 받은 적이 있으면 그 결과를 쓴다"""
    jids = {}
    work_info = DG.work_profile(PF.view(employee_id))  # 업무 정보가 바뀌면 전달 내용 키도 바뀌어 3안을 새로 만든다

    def fn(t, w):
        d = w['draft']
        if not d.get('diag') or d['diag']['key'] != diag_key(d):
            raise ApiError(409, 'DIAG_REQUIRED', '점검 결과를 먼저 정리해 주세요')
        h = build_handoff(d, work_info)
        if not d.get('gen') or d['gen'].get('key') != h['key'] or (d['gen'].get('missing') or []):
            d.update(gen=None, chosen=None, genRun=None)
            w['draftPlan'] = None
        d['handoff'] = h
        d['genPrefs'] = copy.deepcopy(d['prefs'])
        rid = _round(t, draft_id, d)
        t.run('UPDATE public.diagnostic_rounds SET agent_input = :h WHERE diagnostic_round_id = CAST(:r AS uuid)', h=db.J(h), r=rid)
        if not d.get('gen'):
            d['genRun'] = {'key': h['key'], 'rows': {pid: {'st': 'run', 'tries': 0, 'out': None, 'err': None, 'jobId': None} for pid in D['optionOrder']}}
            return True
        return False
    w = _mutate(employee_id, draft_id, lambda t, w: jids.__setitem__('start', fn(t, w)))
    if jids['start']:
        for pid in D['optionOrder']:
            jids[pid] = _run_option(employee_id, draft_id, pid)
        w = _mutate(employee_id, draft_id, lambda t, w: None)
    return dict(present(w, draft_id), jobs={k: v for k, v in jids.items() if k != 'start'})


def _run_option(employee_id: int, draft_id: str, pid: str) -> str:
    # 작업을 시작하기 전에 '작성 중'으로 표시한다(작업이 빨리 끝나도 결과를 덮어쓰지 않게)
    info: dict = {}

    def mark(t, w2):
        r = w2['draft'].get('genRun')
        if not r:
            raise ApiError(409, 'NO_RUN', '작성 중인 3안이 없어요')
        row = r['rows'][pid]
        row.update(st='run', err=None, jobId=None, tries=(row.get('tries') or 0) + 1)
        info.update(h=w2['draft']['handoff'], key=r['key'], tries=row['tries'])
    _mutate(employee_id, draft_id, mark)
    h, key, tries = info['h'], info['key'], info['tries']

    def work(job: jobs.JobCtx):
        ctx = rt.context(employee_id)
        sim = rt.SIM_ERR['openai' if ctx.provider == 'openai' else 'ollama'][pid] if ctx.fail_sim.get('gen') and pid in ('A2', 'A3') and tries == 1 else None
        out, err = None, None
        try:
            out = RM.option(ctx, {'pid': pid, 'handoff': h}, sim=sim)
        except AgentError as e:
            err = e.info

        def save(t, w2):
            r = w2['draft'].get('genRun')
            if not r or r['key'] != key:
                return
            row = r['rows'][pid]
            row.update(st='ok' if out else 'fail', out=out, err=err, jobId=None)
            rows = [r['rows'][x] for x in D['optionOrder']]
            d2 = w2['draft']
            if not any(x['st'] == 'run' for x in rows) and all(x['st'] == 'ok' for x in rows) and (not d2.get('gen') or d2['gen'].get('key') != key):
                d2['gen'] = {'key': key, 'options': {x: r['rows'][x]['out'] for x in D['optionOrder']}, 'missing': []}
        _mutate(employee_id, draft_id, save)
        _maybe_support(employee_id, draft_id)
        if err:
            raise AgentError(err['raw'] or err['text'])
        return {'pid': pid}
    jid = jobs.start('option', employee_id, f'{draft_id}:{pid}', work)

    def note_job(t, w2):
        r = w2['draft'].get('genRun')
        if r and r['key'] == key and r['rows'][pid]['st'] == 'run':
            r['rows'][pid]['jobId'] = jid
    _mutate(employee_id, draft_id, note_job)
    return jid


def option_retry(employee_id: int, draft_id: str, pid: str) -> dict:
    """실패한 안만 다시 작성(API-29 · 사용자가 누를 때만)"""
    with db.tx() as t:
        w = _wrap(_row(t, employee_id, draft_id, lock=False)['draft_choices'])
    r = w['draft'].get('genRun')
    if not r or (r['rows'].get(pid) or {}).get('st') != 'fail':
        raise ApiError(409, 'NOT_FAILED', '다시 작성할 안이 없어요')
    jid = _run_option(employee_id, draft_id, pid)
    return dict(get(employee_id, draft_id), jobs={pid: jid})


def accept_partial(employee_id: int, draft_id: str) -> dict:
    """작성된 안만으로 진행(API-30). 실패한 안은 저장하지 않는다"""
    def fn(t, w):
        d = w['draft']
        r = d.get('genRun')
        rows = [r['rows'][x] for x in D['optionOrder']] if r else []
        if not r or any(x['st'] == 'run' for x in rows) or not any(x['st'] == 'ok' for x in rows):
            raise ApiError(409, 'NOTHING_TO_ACCEPT', '작성된 안이 없어요')
        d['gen'] = {'key': r['key'], 'options': {x: r['rows'][x]['out'] for x in D['optionOrder'] if r['rows'][x]['st'] == 'ok'},
                    'missing': [x for x in D['optionOrder'] if r['rows'][x]['st'] != 'ok']}
        d['chosen'] = None
        w['draftPlan'] = None
    w = _mutate(employee_id, draft_id, fn)
    _maybe_support(employee_id, draft_id)
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


_sup_busy: set = set()
_sup_lock = threading.Lock()


def _maybe_support(employee_id: int, draft_id: str, force: list | None = None) -> str | None:
    """3안이 정해지면 규정 에이전트를 한 번 불러 안별 지원 조건을 확인한다(다시 만든 안은 그 안만). 실패는 안(버전)마다 남긴다"""
    with _sup_lock:
        if draft_id in _sup_busy:
            return None
        with db.tx() as t:
            w = _wrap(_row(t, employee_id, draft_id, lock=False)['draft_choices'])
        g = w['draft'].get('gen')
        if not g:
            return None
        _sync(g)
        need = [pid for pid in D['optionOrder'] if g['options'].get(pid) and not g['options'][pid].get('support') and not g['options'][pid].get('supportFail')]
        if not need:
            return None
        _sup_busy.add(draft_id)
    h = w['draft']['handoff']
    sigs = {pid: json.dumps(g['options'][pid]['acts'], ensure_ascii=False, sort_keys=True) for pid in need}
    plans = [_sup_input(pid, g['options'][pid]['name'], RM.build_plan(g['options'][pid], RM.params_of(h, g['options'][pid]), h['goal'])) for pid in need]

    def work(job: jobs.JobCtx):
        try:
            ctx = rt.context(employee_id)
            context = REG.reg_context(ctx.me, _plans_brief(employee_id), None)
            out, err = None, None
            try:
                out = REG.support(ctx, plans, context, sim=rt.sim_once(ctx, 'sup', g['key']))
            except AgentError as e:
                err = e.info

            def save(t, w2):
                g2 = w2['draft'].get('gen')
                if not g2 or g2['key'] != g['key']:
                    return
                _sync(g2)
                for pid in need:
                    o = g2['options'].get(pid)
                    if not o or json.dumps(o['acts'], ensure_ascii=False, sort_keys=True) != sigs[pid]:
                        continue
                    if err:
                        o['supportFail'] = {'cause': err}
                    else:
                        o['support'] = (out or {}).get(pid) or {'level': 'missing', 'summary': '이 안은 확인 결과를 받지 못했어요. 담당 부서에 확인해 주세요.', 'basis': [], 'missing': []}
                        o.pop('supportFail', None)
            _mutate(employee_id, draft_id, save)
            if err:
                raise AgentError(err['raw'] or err['text'])
            return {'ok': True}
        finally:
            with _sup_lock:
                _sup_busy.discard(draft_id)
            # 확인하는 동안 다시 만든 안이 생겼으면 그 안도 확인
            _maybe_support(employee_id, draft_id)
    return jobs.start('support', employee_id, draft_id, work)


def support_retry(employee_id: int, draft_id: str, pid: str | None) -> dict:
    def fn(t, w):
        g = w['draft'].get('gen')
        if not g:
            return
        _sync(g)
        for x in D['optionOrder']:
            if g['options'].get(x) and (not pid or pid == 'all' or x == pid):
                g['options'][x].pop('supportFail', None)
    w = _mutate(employee_id, draft_id, fn)
    jid = _maybe_support(employee_id, draft_id)
    return dict(present(w, draft_id), jobs={'support': jid} if jid else {})


def regenerate(employee_id: int, draft_id: str, pid: str, req: dict | None) -> dict:
    """이 안만 다시 만들기(API-32 · 요청 반영 · 새 버전). 실패하면 이전 안을 그대로 둔다"""
    def mark(t, w):
        g = w['draft'].get('gen')
        if not g or pid not in g['options']:
            raise ApiError(409, 'NO_OPTION', '다시 만들 안이 없어요')
        _sync(g)
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
        except AgentError as e:
            def fail(t, w):
                g = w['draft'].get('gen')
                if g and g['key'] == info['key']:
                    (g.get('regenRun') or {}).pop(pid, None)
                    g.setdefault('regenErr', {})[pid] = e.info
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
            lst = _hist(g, pid)
            lst.append(o)
            if len(lst) > 6:
                del lst[1]  # 처음 안과 최근 다섯 버전만 둔다
            g['cur'][pid] = len(lst) - 1
            g['options'][pid] = lst[-1]
            (g.get('regenRun') or {}).pop(pid, None)
            if w.get('draftPlan') and w['draftPlan'].get('opt') == pid:
                w['draftPlan'] = None
        _mutate(employee_id, draft_id, ok)
        _maybe_support(employee_id, draft_id)
        return {'pid': pid, 'version': info['variant'] + 1}
    jid = jobs.start('regenerate', employee_id, f'{draft_id}:{pid}', work)

    def note_job(t, w):
        g = w['draft'].get('gen')
        if g and (g.get('regenRun') or {}).get(pid):
            g['regenRun'][pid]['jobId'] = jid
    w = _mutate(employee_id, draft_id, note_job)
    return dict(present(w, draft_id), jobs={pid: jid})


def select(employee_id: int, draft_id: str, pid: str) -> dict:
    """안 선택 → 검토용 계획(API-34)"""
    def fn(t, w):
        d = w['draft']
        g = d.get('gen')
        if not g or pid not in g['options']:
            raise ApiError(409, 'NO_OPTION', '고를 안이 없어요')
        if (g.get('regenRun') or {}).get(pid):
            raise ApiError(409, 'REGEN_RUNNING', '그 안을 다시 쓰는 중이에요. 잠시 뒤에 골라 주세요')
        _sync(g)
        d['chosen'] = pid
        o = g['options'][pid]
        w['draftPlan'] = RM.build_plan(o, RM.params_of(d['handoff'], o), d['goal'])
        w['lastNew'] = 'new-review'
    return present(_mutate(employee_id, draft_id, fn), draft_id)


def selection_of(d: dict) -> dict:
    return {'perspective': d['id'], 'name': d['name'], 'agent': f"로드맵 계획 에이전트 · {d['id']} {d['name']}", 'source': d.get('source'), 'at': today()}


def confirm(employee_id: int, draft_id: str) -> dict:
    """개인 로드맵 확정(API-35 · 기관 승인·결재 아님). 진행 중인 다른 로드맵은 그대로, 고르지 않은 안·버전은 버린다"""
    with db.tx() as t:
        r = _row(t, employee_id, draft_id)
        w = _wrap(r['draft_choices'])
        d = w['draft']
        if not w.get('draftPlan') or not d.get('chosen'):
            raise ApiError(409, 'NOT_SELECTED', '확정할 안을 먼저 골라 주세요')
        g = d['gen']
        _sync(g)
        o = g['options'][d['chosen']]
        plan = RM.build_plan(o, RM.params_of(d['handoff'], o), d['goal'])
        validate_free_plan(t, plan)
        assess = {'questions': d['quiz']['questions'], 'answers': dict(d['answers']), 'domain': d['quiz']['domain']}
        if deep_on(d) and (d.get('diag') or {}).get('deep'):
            # 심화 질문(사전): 사후 점검 비교와 결과 보고서용. 부서장 화면에는 보내지 않는다(plans.record for_mgr 가 assess 를 비움)
            assess['deep'] = {'on': True, 'quiz': d['quiz']['deep'], 'mcq': dict(d.get('deepMcq') or {}), 'essay': dict(d.get('deepEssay') or {}),
                              'grade': d['diag']['deep']['grade'], 'judge': d['diag']['deep']['judge']}
        plan.update(version=1, confirmedAt=today(), why='최초 확정', assess=assess,
                    prefs=copy.deepcopy(d['prefs']), handoff=d['handoff'], selection=selection_of(o))
        rid = _round(t, draft_id, d)
        roadmap_id = PL.insert_roadmap(t, draft_id, rid, plan)
        t.run("""UPDATE public.projects SET status = 'IN_PROGRESS', current_stage = 7, draft_choices = :w, updated_at = now() WHERE project_id = CAST(:p AS uuid)""",
              w=db.J({'gp5': 1, 'confirmed': True, 'roadmapId': roadmap_id}), p=draft_id)
    with _img_lock:
        _images.pop(draft_id, None)
    return {'planId': roadmap_id, 'version': 1, 'selection': plan['selection'], 'sharedWith': PL.shared_with(employee_id)}

"""진단 에이전트 · 목표 후보 제안 (FR-05 · 4차 AI.goalCandidates).

목표를 적기 전에 보여 주는 후보 3개. 직원 프로필(인사 정보 + 본인 입력 + 목표 추천 활용에 동의한 평정)만 본다.
5차: 직원 데이터가 바뀔 때 미리 만들어 DB에 저장하고(services/goals.py), 새 로드맵 화면은 저장된 후보를 보여 준다(2026-10-21 사용자 결정).
본인 입력(업무 설명·경험 요약·기술 스택)이 없으면 에이전트를 부르지 않고 AI 활용 업무 기본 후보 3개.
"""
from __future__ import annotations

import re

from . import runtime as rt
from .demo import D, GOAL_RULES

G_LABEL = {'job': '직무', 'task': '담당 업무', 'workDescription': '업무 설명', 'experience': '경험 요약', 'techStack': '기술 스택',
           'certifications': '보유 자격', 'learning': '교육 이력', 'projects': '프로젝트', 'evaluations': '평정(목표 추천 활용 동의)'}
G_BASIS = ['직무', '담당 업무', '업무 설명', '경험 요약', '기술 스택', '보유 자격', '교육 이력', '프로젝트']
EVAL_RE = re.compile(r'(평정|\d+\s*/\s*50|점수|등급|인사평가)')

G_SYS = """너는 GrowPath의 진단 에이전트다. 직원이 목표를 적기 전에, 입력의 profile(사내 DB의 직원 프로필)만 보고 AI 역량 성장 목표 후보 3개를 제안한다.
- 후보는 그 직원의 담당 업무에 AI(생성형 AI·RAG·데이터 분석·업무 자동화 등)를 활용하는 학습 목표다. 직원이 쓴 것처럼 '~하고 싶어요.'로 끝나는 한 문장으로 쓴다.
- 세 후보는 서로 다른 방향이어야 한다. avoid에 있는 목표와 같은 후보는 내지 않는다. 프로필에 없는 업무·경력·자격·프로젝트를 지어내지 않는다.
- why: 프로필의 어떤 내용 때문에 이 후보를 골랐는지 1문장(해요체). basis: 근거로 쓴 항목 이름만(직무, 담당 업무, 업무 설명, 경험 요약, 기술 스택, 보유 자격, 교육 이력, 프로젝트).
- evaluations(근무성적평정)는 본인이 목표 추천 활용에 동의한 것만 들어온다. 목표의 난이도를 가늠하는 참고로만 쓰고, 평정으로 목표를 정하거나 goal·why에 등급·점수·평정을 쓰지 않는다.
- areas는 GrowPath가 로드맵을 만들 수 있는 분야다. 후보는 이 분야와 이어지면 좋다.
- 근거가 부족한 부분이 있으면 note에 1문장으로 적는다(없으면 빈 문자열).
JSON 형식: {"candidates":[{"goal":"...하고 싶어요.","why":"...","basis":["업무 설명"]}],"note":""}"""


def profile_enough(e: dict) -> bool:
    p = e.get('profile') or {}
    return bool(p.get('workDesc') or p.get('expSummary') or e.get('tech'))


def goal_input(e: dict) -> dict:
    p = e.get('profile') or {}
    evals = [{'period': x['period'], 'result': ', '.join(v for v in (x.get('grade'), x.get('score')) if v)} for x in e.get('evals', []) if x.get('consent')]
    profile = {'grade': e.get('grade'), 'department': e.get('dept'), 'parentDepartment': e.get('parentDept'), 'job': e.get('job'), 'task': e.get('task'),
               'position': e.get('position'), 'workDescription': p.get('workDesc'), 'experience': p.get('expSummary'), 'developmentYears': p.get('devYears'),
               'techStack': e.get('tech') or [], 'certifications': e.get('certs') or [], 'learning': e.get('learning') or [], 'projects': e.get('projects') or [],
               'evaluations': evals}
    used = [G_LABEL[k] for k in G_LABEL if (len(profile[k]) if isinstance(profile[k], list) else bool(profile[k]))]
    return {'profile': profile, 'used': ['직급·부서'] + used, 'areas': [d['label'] for d in D['domains'].values()]}


def clean(lst, avoid) -> list[dict]:
    seen = {re.sub(r'\s', '', x) for x in (avoid or [])}
    out = []
    for c in lst if isinstance(lst, list) else []:
        g = str((c or {}).get('goal') or '').strip()
        why = str((c or {}).get('why') or '').strip()
        basis = [str(b) for b in ((c or {}).get('basis') or []) if str(b) in G_BASIS]
        key = re.sub(r'\s', '', g)
        if not (8 <= len(g) <= 160) or EVAL_RE.search(g) or key in seen:
            continue
        seen.add(key)
        out.append({'goal': g, 'why': '프로필의 업무 내용을 바탕으로 골랐어요.' if EVAL_RE.search(why) else why, 'basis': basis})
    return out[:3]


def _api(ctx: rt.Ctx, inp: dict) -> dict:
    r = rt.llm_json(ctx, G_SYS, {'profile': inp['profile'], 'areas': inp['areas'], 'avoid': inp.get('avoid') or []})
    cands = clean(r.get('candidates'), inp.get('avoid'))
    if len(cands) < 2:
        raise rt.llm.LlmError('목표 후보가 너무 적어요')
    return {'candidates': cands, 'note': str(r.get('note') or '').strip()}


def mock(inp: dict) -> dict:
    """가데이터: 프로필 문장에서 업무 단서를 찾아 정해진 후보로 바꾼다(실제 추론 아님)"""
    p, avoid = inp['profile'], {re.sub(r'\s', '', x) for x in inp.get('avoid') or []}
    fields = [('업무 설명', p.get('workDescription')), ('담당 업무', p.get('task')), ('경험 요약', p.get('experience')),
              ('기술 스택', ' '.join(p.get('techStack') or [])), ('프로젝트', ' '.join(p.get('projects') or [])), ('직무', p.get('job'))]
    out = []
    for pat, goal in GOAL_RULES:
        if len(out) >= 3 or re.sub(r'\s', '', goal) in avoid or any(c['goal'] == goal for c in out):
            continue
        f = next(((n, v) for n, v in fields if v and re.search(pat, v)), None)
        if f:
            out.append({'goal': goal, 'why': f"{f[0]}에 ‘{re.search(pat, f[1]).group(0)}’ 관련 내용이 있어요.", 'basis': [f[0]]})
    for x in D['goalDefaults']:
        if len(out) < 3 and not any(c['goal'] == x['goal'] for c in out) and re.sub(r'\s', '', x['goal']) not in avoid:
            out.append({'goal': x['goal'], 'why': '프로필에서 더 구체적인 단서를 찾지 못해 AI 활용 업무 기본 후보를 더했어요.', 'basis': []})
    note = '' if p.get('techStack') else '기술 스택 정보가 없어 난이도는 업무 설명만 보고 가늠했어요.'
    return {'candidates': out[:3], 'note': note}


def defaults() -> list[dict]:
    return [{'goal': x['goal'], 'why': x['why'], 'basis': []} for x in D['goalDefaults']]


def run(ctx: rt.Ctx, inp: dict, sim: str | None = None) -> dict:
    task = '목표 후보 제안 (다른 후보)' if inp.get('avoid') else '목표 후보 제안'
    return rt.run(ctx, '진단 에이전트', task, inp, mock, lambda i: _api(ctx, i), sim=sim, mock_delay=0.5)

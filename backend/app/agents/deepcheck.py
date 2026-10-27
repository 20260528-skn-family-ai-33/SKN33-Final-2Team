"""심화 질문(10/23 사용자 요구): 자가 진단 문항마다 객관식 1개, 영역마다 서술형 1개.

- 자가 진단(5점 척도)은 그대로 두고, 심화 질문은 사용자가 고를 때만 푼다(체크). 문항은 자가 진단 문항과 같은 호출에서 함께 만든다(10/23 결정).
- 사후 점검은 같은 개념의 새 문제(diag.post_deep). 사전에 심화를 고른 사람에게만 보인다.
- 객관식 쏠림 막기: 정답만 유독 길거나, 선택지 길이 차이가 크거나, 극단 표현(무조건·반드시·절대 …)이 있으면 문제로 보고
  진단 에이전트에게 그 문항만 한 번 다시 쓰게 한다(diag.fix_checks). 선택지 순서는 서버가 섞어 정답 위치를 고르게 한다.
- 채점: 객관식은 서버, 서술형은 수준 진단(사전)·결과 보고서(사후) 호출에서 함께 판단한다(10/23 결정).
- 정답·해설·모범 답안은 답을 낸 뒤(점검 결과·보고서)에만 화면에 보낸다(public 이 가린다).
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

DK = 'dk'  # '잘 모르겠어요'
LEVELS = ('충분', '부분', '부족', '답 없음')
# 극단 표현: 정답·오답 어디에도 쓰지 않는다(낱말만 보고 오답을 걸러 내지 못하게)
ABSOLUTE = re.compile(r'(무조건|반드시|절대|항상|오직|결코|언제나|전혀|어떤 경우에도|모든 경우|100\s*%|만으로|만 사용|만 하면|뿐이다|뿐이에요|모두 맞|모두 옳|모두 틀|모두 해당|위의 모든)')
LONG_RATIO = 1.2   # 정답이 가장 길면서 나머지 평균의 1.2배를 넘으면 문제
SPREAD_RATIO = 1.8  # 가장 긴 선택지가 가장 짧은 것의 1.8배를 넘으면 문제

BANK = json.loads(Path(__file__).with_name('demo_deep.json').read_text(encoding='utf-8'))

# 객관식 작성 규칙: 문항 생성(Q_SYS)·고치기(FIX_SYS)·사후 문항(PD_SYS)이 함께 쓴다
MCQ_RULES = """- 객관식은 용어 뜻을 묻기보다 업무 상황을 주고 무엇이 알맞은지 고르게 한다. q는 한두 문장, options는 4개, answer는 정답 번호(0~3), explain은 왜 정답인지와 대표 오답이 왜 틀렸는지 1~2문장(해요체).
- 선택지만 보고 정답을 알아맞힐 수 없게 쓴다.
  · 네 선택지를 같은 문장 형태(같은 어미)와 비슷한 글자 수로 쓴다. 정답을 가장 길거나 가장 자세하게 쓰지 않는다. 가장 긴 선택지가 가장 짧은 것의 1.5배를 넘지 않게 한다.
  · 오답은 실제로 자주 하는 오해, 비슷하지만 다른 개념, 다른 상황에서는 맞는 방법으로 그럴듯하게 쓴다. 터무니없는 오답을 넣지 않는다.
  · 무조건·반드시·절대·항상·오직·전혀·결코·모든 경우·~만 같은 극단 표현을 정답에도 오답에도 쓰지 않는다. '모두 맞다', '모두 틀리다' 선택지를 쓰지 않는다.
  · 정답에만 질문이나 점검 문항(statement)의 낱말을 되풀이하지 않는다."""


def _len(s: str) -> int:
    return len(re.sub(r'\s+', '', s or ''))


def clean_mcq(raw) -> dict | None:
    """에이전트가 쓴 객관식 한 개 → {q, options[4], answer, explain}. 모양이 틀리면 None"""
    if not isinstance(raw, dict):
        return None
    opts = [str(x).strip() for x in (raw.get('options') or []) if str(x).strip()] if isinstance(raw.get('options'), list) else []
    try:
        ans = int(raw.get('answer'))
    except (TypeError, ValueError):
        return None
    q = str(raw.get('q') or raw.get('question') or '').strip()
    if not q or len(opts) != 4 or len(set(opts)) != 4 or not 0 <= ans < 4:
        return None
    return {'q': q[:200], 'options': [o[:120] for o in opts], 'answer': ans, 'explain': str(raw.get('explain') or '').strip()[:300]}


def issues(m: dict) -> list[str]:
    """객관식 쏠림 검사. 사람이 읽는 문제 목록(비어 있으면 통과)"""
    out = []
    lens = [_len(o) for o in m['options']]
    right, others = lens[m['answer']], [n for i, n in enumerate(lens) if i != m['answer']]
    if right > max(others) and right > LONG_RATIO * (sum(others) / len(others)):
        out.append('정답 선택지만 다른 선택지보다 눈에 띄게 길어요')
    if max(lens) > SPREAD_RATIO * max(1, min(lens)):
        out.append('선택지 길이 차이가 커요')
    bad = sorted({w for o in m['options'] for w in ABSOLUTE.findall(o)})
    if bad:
        out.append(f"극단 표현이 있어요: {', '.join(bad)}")
    return out


def shuffle(m: dict, seed: str) -> dict:
    """선택지 순서를 섞는다(같은 문항은 늘 같은 순서). 정답 번호도 따라 바꾼다"""
    order = list(range(4))
    random.Random(seed).shuffle(order)
    return dict(m, options=[m['options'][i] for i in order], answer=order.index(m['answer']))


def clean_essays(raw, areas: list[str]) -> list[dict]:
    """영역마다 서술형 하나 → [{id, area, q, points[2~4], model}]. 영역 이름이 없거나 겹치면 뺀다"""
    out, seen = [], set()
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        a, q = str(x.get('area') or '').strip(), str(x.get('q') or x.get('question') or '').strip()
        pts = [str(p).strip()[:80] for p in (x.get('points') or []) if str(p).strip()][:4] if isinstance(x.get('points'), list) else []
        if a not in areas or a in seen or not q or len(pts) < 2:
            continue
        seen.add(a)
        out.append({'id': f'e{len(out) + 1}', 'area': a, 'q': q[:240], 'points': pts, 'model': str(x.get('model') or '').strip()[:500]})
    return out


def build(questions: list[dict], raw_checks: dict, raw_essays, seed: str) -> dict:
    """문항별 객관식과 영역별 서술형을 정리하고 검사 결과(issues)를 붙인다. 섞기는 고치기가 끝난 뒤(finish)"""
    mcq, bad = {}, {}
    for q in questions:
        m = clean_mcq(raw_checks.get(q['id']))
        if m:
            mcq[q['id']] = m
            if issues(m):
                bad[q['id']] = issues(m)
    areas = list(dict.fromkeys(q['area'] for q in questions))
    return {'mcq': mcq, 'essays': clean_essays(raw_essays, areas), 'issues': bad, 'seed': seed}


def finish(deep: dict) -> dict | None:
    """고치기 뒤 마무리: 남은 문제를 다시 세고, 선택지를 섞는다. 객관식이 하나도 없으면 None(심화 질문 없음)"""
    if not deep or not deep['mcq']:
        return None
    left = {k: issues(m) for k, m in deep['mcq'].items() if issues(m)}
    if deep.get('fixError'):
        left['_fix'] = [f"고치기 호출 실패: {deep['fixError']}"]
    mcq = {k: shuffle(m, f"{deep['seed']}|{k}") for k, m in deep['mcq'].items()}
    return {'mcq': mcq, 'essays': deep['essays'], 'warn': left, 'fixed': deep.get('fixed') or []}


def public(deep: dict | None, reveal: bool) -> dict | None:
    """화면에 보낼 모양. 답을 내기 전에는 정답·해설·채점 핵심 요소·모범 답안을 뺀다"""
    if not deep:
        return None
    if reveal:
        return deep
    return {'mcq': {k: {'q': m['q'], 'options': m['options']} for k, m in deep['mcq'].items()},
            'essays': [{'id': e['id'], 'area': e['area'], 'q': e['q']} for e in deep['essays']], 'warn': {}}


def grade(deep: dict, mcq_ans: dict) -> dict:
    """객관식 채점: {문항 id: {chosen: 번호|'dk'|None, result: 맞음|틀림|모름|답 안 함}}"""
    out = {}
    for k, m in (deep or {}).get('mcq', {}).items():
        v = (mcq_ans or {}).get(k)
        if v in (None, ''):
            out[k] = {'chosen': None, 'result': '답 안 함'}
        elif str(v) == DK:
            out[k] = {'chosen': DK, 'result': '모름'}
        else:
            try:
                i = int(v)
            except (TypeError, ValueError):
                out[k] = {'chosen': None, 'result': '답 안 함'}
                continue
            out[k] = {'chosen': i, 'result': '맞음' if i == m['answer'] else '틀림'}
    return out


def complete(deep: dict | None, mcq_ans: dict) -> bool:
    """객관식은 모두 골라야 한다('잘 모르겠어요' 포함). 서술형은 비워 둬도 된다(답 없음으로 판단)"""
    return bool(deep) and all(str((mcq_ans or {}).get(k) or '') for k in deep['mcq'])


def chosen_text(m: dict, v) -> str:
    if str(v) == DK:
        return '잘 모르겠어요'
    try:
        return m['options'][int(v)]
    except (TypeError, ValueError, IndexError):
        return '답 안 함'


def agent_items(questions: list[dict], answers: dict, deep: dict, mcq_ans: dict, essay_ans: dict, ans_label) -> dict:
    """진단 에이전트 입력(deepCheck): 문항별 자기평가와 객관식 결과, 영역별 서술형 답"""
    g = grade(deep, mcq_ans)
    items = []
    for q in questions:
        m = deep['mcq'].get(q['id'])
        if not m:
            continue
        items.append({'area': q['area'], 'statement': q['text'], 'skill': q.get('skill'), 'self': ans_label(answers.get(q['id'])),
                      'question': m['q'], 'chosen': chosen_text(m, (mcq_ans or {}).get(q['id'])), 'result': g[q['id']]['result']})
    essays = [{'id': e['id'], 'area': e['area'], 'question': e['q'], 'points': e['points'], 'answer': str((essay_ans or {}).get(e['id']) or '').strip()[:1500]}
              for e in deep['essays']]
    return {'items': items, 'essays': essays}


def clean_judge(raw, essays: list[dict], essay_ans: dict) -> dict:
    """서술형 판단 → {e1: {level, why}}. 답이 비면 '답 없음'으로 둔다(에이전트 판단과 관계없이)"""
    got = {str(x.get('id')): x for x in raw if isinstance(x, dict)} if isinstance(raw, list) else {}
    out = {}
    for e in essays:
        blank = not str((essay_ans or {}).get(e['id']) or '').strip()
        x = got.get(e['id']) or {}
        lv = '답 없음' if blank else (str(x.get('level') or '').strip() if str(x.get('level') or '').strip() in LEVELS[:3] else None)
        out[e['id']] = {'level': lv or '판단 못 함', 'why': '답을 쓰지 않았어요.' if blank else str(x.get('why') or '').strip()[:200]}
    return out


def handoff_summary(questions: list[dict], answers: dict, deep: dict, g: dict, judge: dict, ans_label, skill_label) -> dict:
    """로드맵 에이전트에 넘기는 요약(handoff.deepCheck): 개념별 자기평가·객관식 결과, 영역별 서술형 판단, 자기평가와 다른 개념"""
    concepts, mismatch = [], []
    for q in questions:
        r = (g.get(q['id']) or {}).get('result')
        if not r:
            continue
        name = skill_label(q.get('skill') or '') or q['text']
        concepts.append({'area': q['area'], 'concept': name, 'statement': q['text'], 'self': ans_label(answers.get(q['id'])), 'check': r})
        sv = int(answers.get(q['id']) or 0)
        if (sv >= 4 and r in ('틀림', '모름')) or (sv and sv <= 2 and r == '맞음'):
            mismatch.append(name)
    essays = [{'area': e['area'], 'level': (judge.get(e['id']) or {}).get('level'), 'why': (judge.get(e['id']) or {}).get('why')} for e in deep['essays']]
    return {'concepts': concepts, 'essays': essays, 'selfMismatch': mismatch}


# ── 가데이터(시연용 고정 문항 · demo_deep.json) ──
def mock_pre(questions: list[dict], seed: str) -> dict | None:
    """가데이터 사전 문항: 문항 id(ai1·dev2·rag3 …)에 맞춘 객관식, 영역 이름에 맞춘 서술형. 자격증 문항은 객관식이 없다"""
    mcq = {q['id']: dict(BANK['pre']['mcq'][q['id']]) for q in questions if q['id'] in BANK['pre']['mcq']}
    areas = list(dict.fromkeys(q['area'] for q in questions))
    essays = [dict(BANK['pre']['essays'][a], area=a) for a in areas if a in BANK['pre']['essays']]
    return finish({'mcq': mcq, 'essays': clean_essays(essays, areas), 'seed': seed})


def mock_post(questions: list[dict], seed: str) -> tuple[dict | None, list[str]]:
    """가데이터 사후 문항: 같은 개념의 새 문제(준비한 분야만). 준비하지 않은 문항은 사전 문제를 다시 쓰고 그렇다고 알린다"""
    notes, mcq = [], {}
    for q in questions:
        if q['id'] in BANK['post']['mcq']:
            mcq[q['id']] = dict(BANK['post']['mcq'][q['id']])
        elif q['id'] in BANK['pre']['mcq']:
            mcq[q['id']] = dict(BANK['pre']['mcq'][q['id']])
            notes.append(q['id'])
    areas = list(dict.fromkeys(q['area'] for q in questions))
    essays = [dict(BANK['post']['essays'].get(a) or BANK['pre']['essays'][a], area=a) for a in areas if a in BANK['pre']['essays']]
    return finish({'mcq': mcq, 'essays': clean_essays(essays, areas), 'seed': seed + '|post'}), notes


def mock_judge(essays: list[dict], essay_ans: dict) -> list[dict]:
    """가데이터 서술형 판단: 핵심 요소의 낱말이 답에 보이는지만 센다(내용을 이해하지 않음 · 그렇다고 적음)"""
    out = []
    for e in essays:
        a = str((essay_ans or {}).get(e['id']) or '')
        hit = sum(1 for p in e['points'] if any(w in a for w in re.findall(r'[A-Za-z]{3,}|[가-힣]{2,}', p) if w not in ('확인', '내용', '여부')))
        n = len(e['points'])
        lv = '충분' if hit * 3 >= n * 2 else '부분' if hit * 3 >= n else '부족'
        out.append({'id': e['id'], 'level': lv, 'why': f'(가데이터) 내용을 이해하지 않고 핵심 요소 {n}개 중 {hit}개의 낱말이 답에 보이는지만 셌어요.'})
    return out

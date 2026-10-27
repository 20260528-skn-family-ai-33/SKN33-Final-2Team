"""지시문 비교: 진단 A_SYS · 로드맵 계획 R_SYS 의 v1(10/23 반영 전 · tools/prompts_v1_baseline.py)과 v2(지금 앱 · v2.2).

근거·방법: 지시문_개선안_20261023.md 5장. 같은 입력을 고정본(사례 파일)으로 만들고, 지시문만 바꿔 OpenAI 에 보낸다.
- fixture: 확정한 로드맵 기록(DB)에서 사례 고정본을 만든다. DB 는 읽기만 한다.
- run: A(진단 v1·v2) → R(같은 v1 전달 내용으로 3안 v1·v2) → E(v2 진단 → v2 3안 이어서). 결과·지표·가림 비교 HTML 을 var/prompt_eval/ 에 남긴다.
유료 API 라 명령을 실행할 때만 호출하고 자동으로 반복하지 않는다. --dry 는 호출 수만 보여 준다.

  .venv\\Scripts\\python tools\\prompt_eval.py fixture c1 --project <project_id>
  .venv\\Scripts\\python tools\\prompt_eval.py run c1 --dry
  .venv\\Scripts\\python tools\\prompt_eval.py run c1
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

from app import catalog, db, llm  # noqa: E402
from app.agents import diag as DG  # noqa: E402
from app.agents import roadmap as RM  # noqa: E402
from app.agents import runtime as rt  # noqa: E402
from app.agents.demo import D  # noqa: E402
from app.agents.goals import goal_input  # noqa: E402
from app.services import drafts, profile  # noqa: E402
import prompts_v1_baseline as V1  # noqa: E402

OUT = ROOT / 'var' / 'prompt_eval'
PROVIDER = 'openai'
PIDS = D['optionOrder']


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:10]


def _dump(path: Path, v) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(v, ensure_ascii=False, indent=1, default=str), encoding='utf-8')


# ── 사례 고정본 ──
def build_fixture(case: str, project_id: str, purpose: str, drift: list[str] | None = None) -> Path:
    """확정한 로드맵의 첫 버전(v1 지시문으로 만든 기록)에서 입력을 모은다"""
    p = db.one('SELECT employee_id, draft_choices FROM public.projects WHERE project_id = CAST(:p AS uuid)', p=project_id)
    if not p:
        raise SystemExit(f'프로젝트를 찾지 못했어요: {project_id}')
    rid = (p['draft_choices'] or {}).get('roadmapId')
    v = db.one('SELECT plan, confirmed_at FROM app_ext.roadmap_versions WHERE roadmap_id = CAST(:r AS uuid) ORDER BY version LIMIT 1', r=rid) if rid else None
    if not v:
        raise SystemExit('확정한 로드맵 기록이 없어요(작성 중 사례는 아직 지원하지 않음)')
    plan = v['plan']
    dr = db.one('SELECT diagnostic_result FROM public.diagnostic_rounds WHERE project_id = CAST(:p AS uuid) AND round_number = 1', p=project_id) or {}
    h, a, prefs = plan['handoff'], plan['assess'], plan['prefs']
    prof = goal_input(profile.view(p['employee_id']))['profile']
    cat_a = [catalog.agent_view(x) for x in catalog.for_agent([plan['goal'], h.get('projectSummary') or ''], drafts.cert_res(prefs))]
    cat_r = RM.agent_catalog(h)
    fx = {'case': case, 'purpose': purpose, 'madeAt': datetime.now().isoformat(timespec='seconds'),
          'source': {'projectId': project_id, 'roadmapId': rid, 'version': 1, 'confirmedAt': v['confirmed_at'], 'employeeId': p['employee_id']},
          'goal': plan['goal'], 'project': h.get('projectFile'), 'projectSummary': h.get('projectSummary'),
          'prefs': dict(prefs, certRes=drafts.cert_res(prefs)), 'prefSummary': drafts.pref_summary(prefs),
          'domain': a.get('domain'), 'questions': a['questions'], 'answers': a['answers'],
          'profile': {k: prof.get(k) for k in DG.PROFILE_KEYS},
          'handoffV1': h, 'diagV1Original': dr.get('diagnostic_result'), 'catalogA': cat_a, 'catalogR': cat_r, 'driftWords': list(drift or [])}
    path = OUT / 'cases' / f'{case}.json'
    _dump(path, fx)
    return path


# ── 호출 ──
def call(system: str, inp: dict, role: str) -> dict:
    """앱과 같은 모양(system + user JSON 한 덩어리)으로 호출. 실패는 error 로 남긴다(성공으로 바꾸지 않음)"""
    msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(inp, ensure_ascii=False, default=str)}]
    t0 = time.perf_counter()
    try:
        res = llm.chat(PROVIDER, msgs, role=role, json_mode=True)
        out = {'raw': rt.parse_json(res['content']), 'model': res.get('model')}
    except llm.LlmError as e:
        out = {'error': str(e)}
    out.update(ms=round((time.perf_counter() - t0) * 1000), systemSha=_sha(system), inChars=len(msgs[1]['content']))
    return out


def a_input(fx: dict, ver: str) -> dict:
    qs = fx['questions']
    if ver == 'v1':  # 지금 앱(diag.assess)과 같은 입력
        ans = [{'area': q['area'], 'statement': q['text'], 'answer': DG.ans(fx['answers'].get(q['id']))} for q in qs]
        return {'goal': fx['goal'], 'projectFile': fx['project'], 'projectSummary': fx['projectSummary'], 'details': fx['prefSummary'],
                'answers': ans, 'catalog': fx['catalogA']}
    ans = [{'area': q['area'], 'statement': q['text'], 'skill': q.get('skill'), 'answer': DG.ans(fx['answers'].get(q['id']))} for q in qs]
    return {'goal': fx['goal'], 'projectFile': fx['project'], 'projectSummary': fx['projectSummary'], 'details': fx['prefSummary'],
            'profile': fx['profile'], 'answers': ans, 'catalog': fx['catalogA']}


def a_clean(raw: dict, fx: dict, gaps_max: int = 6) -> dict:
    """diag.assess 의 후처리와 같게(자료 id 는 목록에 있는 것만). gaps_max 는 v2.1 의 3~8개용(앱은 지금 6개)"""
    ids = {r['id'] for r in fx['catalogA']}
    try:
        start = min(4, max(1, round(float(raw.get('startStage') or 1))))
    except (TypeError, ValueError):
        start = 1
    return {'startStage': start, 'startReason': str(raw.get('startReason') or '').strip(), 'known': rt.arr(raw.get('known')), 'gaps': rt.arr(raw.get('gaps'), gaps_max),
            'competencies': rt.arr(raw.get('competencies')), 'resourceIds': [x for x in rt.arr(raw.get('resourceIds')) if x in ids],
            'droppedIds': [x for x in rt.arr(raw.get('resourceIds')) if x not in ids], 'outcome': str(raw.get('outcome') or '').strip(),
            'handoffNotes': rt.arr(raw.get('handoffNotes'))}


def handoff_from(fx: dict, dg: dict) -> dict:
    """v2 진단 결과로 전달 내용을 다시 만든다(drafts.build_handoff 와 같은 칸 + D2 업무 정보)"""
    h = dict(fx['handoffV1'])
    h.update(startStage=dg['startStage'], startReason=dg['startReason'], startSuggested=dg['startStage'], known=dg['known'], gaps=dg['gaps'],
             focus=dg['competencies'], outcome=dg['outcome'], resourceHints=dg['resourceIds'], agentNotes=dg['handoffNotes'], userEdited=[],
             profile=fx['profile'])
    h.pop('key', None)
    return h


def r_run(pid: str, ver: str, h: dict, cat: list) -> dict:
    per = D['perspectives'][pid]
    system = V1.R_SYS_V1.format(**dict(per, id=pid)) if ver == 'v1' else RM._sys(pid, RM.R_SYS)
    out = call(system, {'handoff': h, 'catalog': cat, 'previous': None, 'request': None}, 'roadmap')
    if 'raw' in out:
        out['taglineLen'] = len(str(out['raw'].get('tagline') or ''))  # 앱(finish_option)은 60자에서 자른다
        raw_acts = [a for a in (out['raw'].get('acts') or []) if isinstance(a, dict)]
        try:
            o = RM.finish_option(pid, out['raw'], PROVIDER)
            pl = RM.build_plan(o, RM.params_of(h, o), h['goal'])
            out.update(option=o, weeks=pl['weeks'], totalH=pl['totalH'], droppedActs=len(raw_acts) - len(o['acts']))
        except llm.LlmError as e:
            out['error'] = str(e)
    return out


# ── 지표 (개선안 5-3) ──
VAGUE = re.compile(r'(이해|파악|익히|정리|검토|살펴보?)(하기|기)?$')
OUTPUT_W = re.compile(r'(남아요|남겨요|남습니다|만들어요|작성해요|저장소|스크립트|대시보드|표|문서|코드|보고서|결과물|시제품|노트북|목록)')
DONE_W = re.compile(r'(되면|면 완료|완료|통과|기준으로|이상|이하|\d+\s*(건|개|%|번|회|초|ms))')
TOOL_RE = re.compile(r'[A-Za-z][A-Za-z0-9.+#-]{1,}')


def _norm(t: str) -> str:
    return re.sub(r'(하기|기)$', '', re.sub(r'\s+', '', re.sub(r'^\(보강\)', '', t or '')))


def tool_names(fx: dict) -> list[str]:
    names = set()
    for q in fx['questions']:
        names |= {w for w in TOOL_RE.findall(q['text']) if len(w) >= 3}
    for t in fx['profile'].get('techStack') or []:
        names |= {w for w in TOOL_RE.findall(t)}
    return sorted(names, key=str.lower)


def drift_count(texts: list[str], words: list[str]) -> int:
    """사례 고정본의 driftWords(업무 설명에만 있고 목표에는 없는 말)가 나온 문장 수"""
    return sum(1 for t in texts if any(w in (t or '') for w in words))


def r_metrics(o: dict, gaps: list, tools: list, res_titles: dict, drift: list | None = None) -> dict:
    acts = o['acts']
    tasks = [a for a in acts if not a.get('res')]
    titles = [a['title'] for a in acts]
    copy = sum(1 for t in titles if any(difflib.SequenceMatcher(None, _norm(t), _norm(g)).ratio() >= 0.7 for g in gaps))
    text_of = lambda a: f"{a['title']} {a.get('how') or ''}"  # noqa: E731
    used_tools = sorted({t for a in acts for t in tools if t.lower() in text_of(a).lower()}, key=str.lower)
    hay = ' '.join(text_of(a) for a in acts) + ' ' + (o.get('scope') or '')
    toks = lambda s: {w for w in re.findall(r'[A-Za-z]{3,}|[가-힣]{2,}', re.sub(r'^\(보강\)\s*', '', s)) if w not in ('응답', '기준', '적용', '설계')}  # noqa: E731
    covered = sum(1 for g in gaps if len(toks(g) & toks(hay)) >= 2)
    return {'acts': len(acts), 'res': len(acts) - len(tasks), 'tasks': len(tasks),
            'vague': sum(1 for t in titles if VAGUE.search(t.strip())), 'gapCopy': copy, 'bundle': sum(1 for t in titles if t.count('·') >= 2),
            'howChars': round(sum(len(a.get('how') or '') for a in tasks) / max(1, len(tasks))),
            'taskOutput': sum(1 for a in tasks if OUTPUT_W.search(a.get('how') or '')), 'taskDone': sum(1 for a in tasks if DONE_W.search(a.get('how') or '')),
            'tools': used_tools, 'gapsCovered': f'{covered}/{len(gaps)}', 'resTitles': [res_titles.get(a['res'], a['res']) for a in acts if a.get('res')],
            'drift': drift_count([text_of(a) for a in acts] + [o.get('scope'), o.get('tagline')], drift or [])}


def a_metrics(dg: dict, tools: list, fx: dict) -> dict:
    kg = ' '.join(dg['known'] + dg['gaps'])
    sim = [max((difflib.SequenceMatcher(None, _norm(c), _norm(g)).ratio() for g in dg['gaps']), default=0) for c in dg['competencies']]
    repeat = sum(1 for n in dg['handoffNotes'] if re.search(r'(목표는|학습 방식|주당|기간|예산|자격증 계획)', n))
    titles = {r['id']: r['title'] for r in fx['catalogA']}
    return {'known': len(dg['known']), 'gaps': len(dg['gaps']), 'boost': sum(1 for g in dg['gaps'] if g.startswith('(보강)')),
            'toolsKept': sorted({t for t in tools if t.lower() in kg.lower()}, key=str.lower), 'compGapSim': round(sum(sim) / max(1, len(sim)), 2),
            'notesRepeat': f"{repeat}/{len(dg['handoffNotes'])}", 'resources': [titles.get(x, x) for x in dg['resourceIds']],
            'drift': drift_count([dg['outcome']] + dg['competencies'] + dg['gaps'] + dg['handoffNotes'], fx.get('driftWords') or [])}


def overlap(opts: dict) -> dict:
    """세 안 사이 활동 제목 단어·자료 겹침(Jaccard)"""
    words = {p: {w for a in o['acts'] for w in re.findall(r'[A-Za-z]{3,}|[가-힣]{2,}', a['title'])} for p, o in opts.items()}
    res = {p: {a['res'] for a in o['acts'] if a.get('res')} for p, o in opts.items()}
    j = lambda x, y: round(len(x & y) / len(x | y), 2) if x | y else 0  # noqa: E731
    ps = list(opts)
    return {f'{a}-{b}': {'title': j(words[a], words[b]), 'res': j(res[a], res[b])} for i, a in enumerate(ps) for b in ps[i + 1:]}


# ── 보고 ──
def _opt_md(o: dict, extra: dict) -> list[str]:
    lines = [f"**{o['id']} {o['name']}** · {o['tagline']} · 주당 {o.get('weeklyHours')}시간 · {extra.get('weeks')}주 · 총 {extra.get('totalH')}시간",
             f"- 범위: {o.get('scope') or '-'}", f"- 이유: {o.get('reason') or '-'}", '', '| 단계 | 활동 | 자료 | 시간 | how |', '|---|---|---|---|---|']
    for a in o['acts']:
        lines.append(f"| {a['stage']} | {a['title']} | {a.get('res') or '과제'} | {a['hours']:g} | {(a.get('how') or '').replace('|', '/')} |")
    return lines + ['']


def report(run_dir: Path, fx: dict, res: dict) -> None:
    tools = tool_names(fx)
    titles = {r['id']: r['title'] for r in fx['catalogR']}
    md = [f"# 지시문 비교 결과 · {fx['case']} · {res['startedAt']}", '',
          f"- 모델: {res.get('model')} ({PROVIDER}) · 호출 {res['calls']}회 · 실패 {res['failed']}회 · 걸린 시간 {res['seconds']}초",
          f"- 지시문: 표의 v2 = 앱 {DG.PROMPT_VERSION} · A v1 `{_sha(V1.A_SYS_V1)}` · A v2 `{_sha(DG.A_SYS)}` · R v1 `{_sha(V1.R_SYS_V1)}` · R v2 `{_sha(RM.R_SYS)}`",
          f"- 사례: {fx['purpose']} · 목표: {fx['goal']}", f"- 문항·기술 스택에서 뽑은 도구 이름: {', '.join(tools)}", '',
          '> 자동 지표는 단어 규칙으로 센 참고값이다. 결과물·완료 기준·지어낸 이름·자료 관련성은 사람이 다시 확인해야 한다.', '']
    drift = ', '.join(fx.get('driftWords') or []) or '없음'
    md += ['## A. 진단 (v1 · v2)', '', f'끌려간 말: 사례의 driftWords({drift})가 나온 문장 수',
           '', '| 실행 | known | gaps(보강) | 남은 도구 이름 | 역량·gaps 유사도 | 메모 되풀이 | 끌려간 말 | 자료 |', '|---|---|---|---|---|---|---|---|']
    for k, x in res['A'].items():
        if x.get('error'):
            md.append(f"| {k} | 실패: {x['error']} | | | | | | |")
            continue
        m = x['metrics']
        md.append(f"| {k} | {m['known']} | {m['gaps']}({m['boost']}) | {', '.join(m['toolsKept']) or '-'} | {m['compGapSim']} | {m['notesRepeat']} | {m.get('drift', '-')} | "
                  f"{' / '.join(m['resources'])} |")
    for k, x in res['A'].items():
        if x.get('clean'):
            c = x['clean']
            md += ['', f'### {k}', f"- startStage {c['startStage']} · {c['startReason']}", f"- known: {c['known']}", f"- gaps: {c['gaps']}",
                   f"- competencies: {c['competencies']}", f"- outcome: {c['outcome']}", f"- handoffNotes: {c['handoffNotes']}"]
    for stage, title in (('R', 'R. 3안 (같은 v1 전달 내용 · 자료 목록 고정)'), ('E', 'E. 이어서 (v2 진단 → v2 3안 · 자료 목록은 v2 전달 내용으로 다시 고름)')):
        if not res.get(stage):
            continue
        md += ['', f'## {title}', '', '| 실행 | 활동(자료/과제) | 막연한 제목 | gaps 옮겨 쓰기 | 묶음 제목 | 과제 how 평균 글자 | 결과물 표현 | 완료 기준 표현 | 쓴 도구 이름 | gaps 범위 | '
               '끌려간 말 | tagline 글자 | 주·시간 |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for k, x in res[stage].items():
            if x.get('error'):
                md.append(f"| {k} | 실패: {x['error']} | | | | | | | | | | | |")
                continue
            m = x['metrics']
            md.append(f"| {k} | {m['acts']}({m['res']}/{m['tasks']}) | {m['vague']} | {m['gapCopy']} | {m['bundle']} | {m['howChars']} | {m['taskOutput']}/{m['tasks']} | "
                      f"{m['taskDone']}/{m['tasks']} | {', '.join(m['tools']) or '-'} | {m['gapsCovered']} | {m.get('drift', '-')} | {x.get('taglineLen', '-')} | "
                      f"{x.get('weeks')}주·{x.get('totalH')}h |")
        if res.get(f'{stage}overlap'):
            md += ['', '세 안 겹침(제목 단어 · 자료, Jaccard): ' + ' · '.join(f"{ver} {pair} {v['title']}/{v['res']}" for ver, ov in res[f'{stage}overlap'].items() for pair, v in ov.items())]
        for k, x in res[stage].items():
            if x.get('option'):
                md += ['', f'### {k}'] + _opt_md(x['option'], x)
                if x['metrics']['resTitles']:
                    md.append('- 쓴 자료: ' + ' / '.join(x['metrics']['resTitles']))
    (run_dir / 'results.md').write_text('\n'.join(md), encoding='utf-8')
    blind(run_dir, fx, res, titles)


def blind(run_dir: Path, fx: dict, res: dict, titles: dict) -> None:
    """R 단계 v1·v2 를 가리고 좌우를 섞은 평가 화면. 정답 열쇠는 key.json 에만"""
    rnd = random.Random(res['startedAt'])
    pairs, key = [], {}
    for pid in PIDS:
        a, b = res['R'].get(f'{pid}-v1') or {}, res['R'].get(f'{pid}-v2') or {}
        if not (a.get('option') and b.get('option')):
            continue
        sides = [('v1', a), ('v2', b)]
        rnd.shuffle(sides)
        key[pid] = {'left': sides[0][0], 'right': sides[1][0]}
        pairs.append((pid, sides))
    _dump(run_dir / 'key.json', key)
    crit = ['이번 주에 무엇을 할지 바로 알 수 있다', '다 했는지 스스로 판단할 수 있다', '목표·업무에 맞는다', '지어낸 내용(없는 자료·장 번호·사내 시스템)이 없다']
    esc = html.escape

    def side(pid: str, pos: str, x: dict) -> str:
        o = x['option']
        rows = ''.join(f"<tr><td>{a['stage']}</td><td><b>{esc(a['title'])}</b><div class=how>{esc(a.get('how') or '')}</div>"
                       f"<div class=res>{esc(titles.get(a['res'], '') if a.get('res') else '직접 수행 과제')}</div></td><td>{a['hours']:g}h</td></tr>" for a in o['acts'])
        form = ''.join(f"<div class=q>{esc(c)}<span>" + ''.join(f"<label><input type=radio name='{pid}-{pos}-{i}' value={v}>{v}</label>" for v in range(1, 6)) + '</span></div>'
                       for i, c in enumerate(crit))
        # 좁은 화면에서는 위아래로 쌓이므로 왼쪽/오른쪽 대신 '가'/'나'로 부른다(점수 이름은 L/R 그대로)
        return (f"<section><h3>안 {'가' if pos == 'L' else '나'}</h3><p class=tag>{esc(o['tagline'])} · 주당 {o.get('weeklyHours')}시간 · {x.get('weeks')}주</p>"
                f"<p class=scope>범위: {esc(o.get('scope') or '-')}</p><table>{rows}</table>{form}</section>")
    body = ''.join(f"<h2>{pid} {esc(D['perspectives'][pid]['name'])}</h2><div class=pair>{side(pid, 'L', s[0][1])}{side(pid, 'R', s[1][1])}</div>"
                   f"<label class=memo>메모(선택 · 어느 쪽이 왜 나은지 등)<textarea name='{pid}-memo' rows=2></textarea></label>" for pid, s in pairs)
    total = len(pairs) * 2 * len(crit)
    page = f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>지시문 가림 비교</title>
<style>body{{font:14px/1.55 system-ui,sans-serif;margin:16px;background:#fff;color:#1f2328}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:800px){{.pair{{grid-template-columns:1fr}}}}section{{border:1px solid #d0d7de;border-radius:8px;padding:12px}}table{{border-collapse:collapse;width:100%}}
td{{border-top:1px solid #eee;padding:6px 4px;vertical-align:top}}.how{{color:#444;margin-top:2px}}.res{{color:#0969da;font-size:12px}}.tag,.scope{{margin:4px 0;color:#57606a}}
.q{{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;border-top:1px dashed #ddd;padding:6px 0}}.q label{{margin-left:6px}}
.memo{{display:block;margin:8px 0 24px}}textarea{{display:block;width:100%;box-sizing:border-box;font:inherit}}button{{font-size:15px;padding:8px 14px;margin:8px 8px 8px 0}}
#bar{{position:sticky;bottom:0;background:#fff;border-top:1px solid #d0d7de;padding:8px 0}}</style></head>
<body><h1>지시문 가림 비교 · {esc(fx['case'])}</h1><p>목표: {esc(fx['goal'])}</p>
<p>관점마다 두 안(가·나) 중 어느 쪽이 새 지시문인지 가렸어요. 각 안의 네 항목에 1(전혀 아님)~5(매우 그렇다)를 골라 주세요. 다 고른 뒤 맨 아래 '결과 보기'를 눌러 나온 글을 복사해 채팅에 붙여 넣거나, '평가 내려받기'로 파일을 저장해 주세요.</p>
{body}<label>평가한 사람 <input id=who></label>
<div id=bar><span id=cnt>0/{total}</span> 항목 선택 <button id=show>결과 보기</button><button id=dl>평가 내려받기</button></div>
<textarea id=out rows=8 readonly placeholder="'결과 보기'를 누르면 여기에 평가 결과가 나와요"></textarea>
<script>const total={total};const collect=()=>{{const r={{case:'{esc(fx['case'])}',run:'{esc(res['startedAt'])}',who:document.getElementById('who').value,at:new Date().toISOString(),scores:{{}},memo:{{}}}};
document.querySelectorAll('input[type=radio]:checked').forEach(x=>r.scores[x.name]=+x.value);
document.querySelectorAll('textarea[name]').forEach(x=>{{if(x.value.trim())r.memo[x.name]=x.value.trim()}});return r}};
document.addEventListener('change',()=>{{document.getElementById('cnt').textContent=document.querySelectorAll('input[type=radio]:checked').length+'/'+total}});
document.getElementById('show').onclick=()=>{{const o=document.getElementById('out');o.value=JSON.stringify(collect());o.focus();o.select()}};
document.getElementById('dl').onclick=()=>{{const a=document.createElement('a');
a.href=URL.createObjectURL(new Blob([JSON.stringify(collect(),null,1)],{{type:'application/json'}}));a.download='평가_{esc(fx['case'])}.json';a.click()}}</script></body></html>"""
    (run_dir / 'compare_blind.html').write_text(page, encoding='utf-8')


# ── 실행 ──
def run(case: str, a_repeat: int, dry: bool) -> None:
    fx = json.loads((OUT / 'cases' / f'{case}.json').read_text(encoding='utf-8'))
    plan = [('A', f'A-{v}-{i + 1}') for v in ('v1', 'v2') for i in range(a_repeat)] + [('R', f'{p}-{v}') for p in PIDS for v in ('v1', 'v2')] + [('E', f'{p}-v2') for p in PIDS]
    print(f'호출 예정 {len(plan)}회 (진단 {2 * a_repeat} · 3안 {2 * len(PIDS)} · 이어서 {len(PIDS)}) · 모드 {PROVIDER} · 모델 {llm.model_name(PROVIDER, "roadmap")}')
    if dry:
        return
    if not llm.available(PROVIDER):
        raise SystemExit('OpenAI 설정이 없어요(.env 의 OPENAI_API_KEY)')
    started = datetime.now()
    run_dir = OUT / f"{started:%Y%m%d_%H%M}_{case}"
    res = {'startedAt': started.isoformat(timespec='seconds'), 'A': {}, 'R': {}, 'E': {}}
    tools = tool_names(fx)
    for k in [k for s, k in plan if s == 'A']:
        ver = k.split('-')[1]
        x = call(V1.A_SYS_V1 if ver == 'v1' else DG.A_SYS, a_input(fx, ver), 'default')
        if 'raw' in x:
            x['clean'] = a_clean(x['raw'], fx, 6 if ver == 'v1' else DG.GAPS_MAX)
            x['metrics'] = a_metrics(x['clean'], tools, fx)
        res['A'][k] = x
        print(k, x.get('error') or f"{x['ms']}ms")
    gaps_v1 = fx['handoffV1'].get('gaps') or []
    h1 = dict(fx['handoffV1'])
    h2 = dict(h1, profile=fx['profile'])  # D2: v2 는 업무 정보를 함께 받는다
    for pid in PIDS:
        for ver, h in (('v1', h1), ('v2', h2)):
            x = r_run(pid, ver, h, fx['catalogR'])
            if x.get('option'):
                x['metrics'] = r_metrics(x['option'], gaps_v1, tools, {r['id']: r['title'] for r in fx['catalogR']}, fx.get('driftWords'))
            res['R'][f'{pid}-{ver}'] = x
            print(f'{pid}-{ver}', x.get('error') or f"{x['ms']}ms")
    first_v2 = next((x['clean'] for k, x in res['A'].items() if k.startswith('A-v2') and x.get('clean')), None)
    if first_v2:
        h3 = handoff_from(fx, first_v2)
        cat3 = RM.agent_catalog(h3)
        res['Ehandoff'], res['Ecatalog'] = h3, [r['id'] for r in cat3]
        for pid in PIDS:
            x = r_run(pid, 'v2', h3, cat3)
            if x.get('option'):
                x['metrics'] = r_metrics(x['option'], h3['gaps'], tools, {r['id']: r['title'] for r in cat3}, fx.get('driftWords'))
            res['E'][f'{pid}-v2'] = x
            print(f'E {pid}-v2', x.get('error') or f"{x['ms']}ms")
    for stage in ('R', 'E'):
        for ver in ('v1', 'v2'):
            opts = {k.split('-')[0]: x['option'] for k, x in res[stage].items() if k.endswith(ver) and x.get('option')}
            if len(opts) == len(PIDS):
                res.setdefault(f'{stage}overlap', {})[ver] = overlap(opts)
    allx = [x for s in ('A', 'R', 'E') for x in res[s].values()]
    res.update(calls=len(allx), failed=sum(1 for x in allx if x.get('error')), seconds=round((datetime.now() - started).total_seconds()),
               model=next((x.get('model') for x in allx if x.get('model')), llm.model_name(PROVIDER)))
    _dump(run_dir / 'case.json', fx)
    _dump(run_dir / 'results.json', res)
    report(run_dir, fx, res)
    print('결과:', run_dir)


def main() -> None:
    ap = argparse.ArgumentParser(description='지시문 v1/v2 비교 (지시문_개선안_20261023.md 5장)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('fixture')
    f.add_argument('case')
    f.add_argument('--project', required=True)
    f.add_argument('--purpose', default='튜닝용', choices=['튜닝용', '확인용'])
    f.add_argument('--drift', nargs='*', default=[], help='업무 설명에만 있고 목표에는 없는 말(끌려감 확인용)')
    r = sub.add_parser('run')
    r.add_argument('case')
    r.add_argument('--a-repeat', type=int, default=2)
    r.add_argument('--dry', action='store_true')
    b = sub.add_parser('blind', help='저장된 실행 결과로 가림 평가 화면만 다시 만든다(모델 호출 없음 · 좌우 배치 같음)')
    b.add_argument('run_dir')
    a = ap.parse_args()
    if a.cmd == 'fixture':
        print('사례 고정본:', build_fixture(a.case, a.project, a.purpose, a.drift))
    elif a.cmd == 'blind':
        d = OUT / a.run_dir
        fx = json.loads((d / 'case.json').read_text(encoding='utf-8'))
        blind(d, fx, json.loads((d / 'results.json').read_text(encoding='utf-8')), {r['id']: r['title'] for r in fx['catalogR']})
        print('가림 평가 화면:', d / 'compare_blind.html')
    else:
        run(a.case, a.a_repeat, a.dry)


if __name__ == '__main__':
    main()

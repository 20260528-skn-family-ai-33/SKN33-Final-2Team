/* GrowPath 5차 목업 (Claude) · 화면
   로그인 / 홈 / 새 로드맵 작성(목표·기획서 → 세부 사항 → 사전 점검 → 점검 결과 → 3안 → 검토·확정) / 내 로드맵 / 점검·보고서
   5차: 에이전트 호출과 기록 저장은 서버(/api/v1)가 한다. 화면은 작업을 시작하고(202 jobId), 서버에 저장된 진행 상태를 다시 읽어 그린다.
   그래서 새로 고치거나 다른 PC에서 들어와도 같은 단계·같은 결과가 보이고, 끊긴 작업은 '작업을 찾지 못함'으로 안내한다(다시 시도는 눌러야만) */
(function () {
  'use strict';
  const GP = window.GP, D = GP.D, AI = GP.AI, P = GP.P, API = GP.API, { esc, won, hrs, icon } = GP;
  const S = () => GP.S, scr = GP.screens;
  const clone = o => JSON.parse(JSON.stringify(o));
  /* 객체 열쇠 순서가 달라도 같은 값이면 같다고 본다(서버를 거친 세부 사항 비교용) */
  const sortKeys = o => (Array.isArray(o) ? o.map(sortKeys) : o && typeof o === 'object' ? Object.fromEntries(Object.keys(o).sort().map(k => [k, sortKeys(o[k])])) : o);
  const sameJ = (a, b) => JSON.stringify(sortKeys(a)) === JSON.stringify(sortKeys(b));
  /* 작성 중인 로드맵 서버 호출: 입력을 먼저 저장하고(작성 시작 포함) 부른 뒤, 응답(작성 문서)을 상태에 넣는다 */
  async function draftCall(what, fn, opts) {
    const st = GP.own();
    try {
      const id = await GP.ensureDraft();
      const r = await fn(id);
      if (GP.own() !== st) return null;
      if (r && r.draft !== undefined) GP.takeDraft(r, opts && opts.soft);
      return r || {};
    } catch (err) { GP.fail(err, what); return null; }
  }
  const draftId = () => GP.own().draftId;

  /* ───────── 새 로드맵 작성 단계 ───────── */
  const STEPS = [['goal', '목표·기획서', 'new-goal'], ['details', '세부 사항', 'new-details'], ['quiz', '사전 점검', 'new-quiz'], ['result', '점검 결과', 'new-result'], ['options', '로드맵 3안', 'new-options'], ['review', '검토·확정', 'new-review']];
  const stepDone = k => {
    const d = S().draft;
    /* 세부 사항은 모두 선택 사항이라, 확인 화면에서 '다음'을 눌렀거나 사전 점검 문항이 있으면 지난 것으로 본다 */
    return { goal: GP.valid.goal(), details: !!(d.detailsOk || d.quiz), quiz: GP.valid.quizDone(), result: !!(d.handoff || d.gen), options: !!S().draftPlan, review: false }[k];
  };
  const blockedTo = k => { const i = STEPS.findIndex(s => s[0] === k); const b = STEPS.slice(0, i).find(([kk]) => !stepDone(kk)); return b ? b[2] : null; };
  GP.stepper = cur => `<nav class="stepper" aria-label="새 로드맵 작성 단계"><ol>${STEPS.map(([k, l, r], i) => {
    const st = k === cur ? 'cur' : stepDone(k) ? 'done' : !blockedTo(k) ? 'open' : 'lock';
    return `<li class="${st}"><button data-go="${r}" ${st === 'lock' ? 'disabled' : ''} ${k === cur ? 'aria-current="step"' : ''}><span class="sn">${st === 'done' ? icon('check') : i + 1}</span><span class="sl">${l}</span></button></li>`;
  }).join('')}</ol></nav>`;
  GP.draftActive = () => { const d = S().draft; return !!(d && (String(d.goal || '').trim() || d.detailsOk)); };
  /* 단계 표시에 따로 없는 하위 화면은 속한 단계로 보여 준다 */
  const SUB = { 'new-details-check': 'details', 'new-result-edit': 'result', 'new-gen': 'options' };
  GP.newRoute = () => S().lastNew || 'new-goal';

  /* 사전 점검 문항은 목표·기획서(파일과 요약)·자격증 계획으로 만든다. 요약이나 자격증 계획을 고쳐도 문항을 다시 만든다
     (설계서 v1.7 SCR-NEW-12 · 10/20). 열쇠 계산은 서버(drafts.quiz_key·diag_key)와 같다 */
  P.docSummary = d => (d.doc && d.doc.status === 'ok' ? String(d.doc.summary || '').trim() : '');
  P.certKey = p => (AI.certOf(p) ? p.cert : '');
  P.quizRest = d => String(d.goal || '').trim() + '|' + (d.project ? d.project.name : '') + '|' + P.docSummary(d);
  P.quizKey = d => P.quizRest(d) + (P.certKey(d.prefs) ? '|cert:' + P.certKey(d.prefs) : '');
  const keyCert = key => (String(key).split('|cert:')[1] || '');
  /* 심화 질문(10/23)을 골랐으면 객관식 답(자가 진단 문항 순서)과 서술형 답도 열쇠에 넣는다(서버 drafts.diag_key 와 같다) */
  P.deepOn = d => !!(d && d.deepOn && d.quiz && d.quiz.deep);
  P.diagKey = d => {
    let k = (d.quiz ? d.quiz.key : '') + '|' + (d.quiz ? d.quiz.questions.map(q => d.answers[q.id] || '-').join(',') : '');
    if (P.deepOn(d)) {
      const dq = d.quiz.deep;
      k += '|deep:' + d.quiz.questions.filter(q => dq.mcq[q.id]).map(q => (d.deepMcq || {})[q.id] || '-').join(',')
        + '|' + dq.essays.map(e => String((d.deepEssay || {})[e.id] || '').trim()).join('\x1f');
    }
    return k;
  };

  /* ───────── 앞 단계를 고쳤을 때 (10/14) ─────────
     입력하는 동안에는 뒤 단계 결과를 지우지 않는다. 바꾼 채로 앞으로 넘어가려 할 때(다음·단계 표시) 무엇을 다시 만드는지 확인하고,
     '바꾼 내용으로 계속'이면 서버가 그때 지우고(API-17), '원래대로 되돌리기'면 결과를 만들 때의 입력으로 돌려 놓는다(API-18) */
  const ORDER = ['new-goal', 'new-details', 'new-details-check', 'new-quiz', 'new-result', 'new-result-edit', 'new-gen', 'new-options', 'new-review'];
  const DOWN = { quiz: ['new-quiz', 'new-result', 'new-result-edit', 'new-gen', 'new-options', 'new-review'], diag: ['new-result', 'new-result-edit', 'new-gen', 'new-options', 'new-review'], gen: ['new-gen', 'new-options', 'new-review'] };
  /* 지금 입력이 뒤 단계 결과를 만들 때와 다르면 그 단계: quiz(목표·기획서·자격증 계획) > diag(사전 점검 응답) > gen(그 밖의 세부 사항) */
  P.stale = function () {
    const d = S().draft;
    if (d.quiz && d.quiz.key !== P.quizKey(d)) {
      const rest = String(d.quiz.key).split('|cert:')[0] !== P.quizRest(d), cert = keyCert(d.quiz.key) !== P.certKey(d.prefs);
      if (cert && !rest) return { kind: 'quiz', note: 'cert', input: 'new-details', what: '자격증 계획을', back: !!d.quiz.base };
      return { kind: 'quiz', input: 'new-goal', what: cert ? '목표·기획서와 자격증 계획을' : '목표·기획서를', back: !!d.quiz.base };
    }
    if (d.diag && d.diag.key !== P.diagKey(d)) return { kind: 'diag', input: 'new-quiz', what: '사전 점검 응답을', back: !!d.diag.answers };
    if ((d.handoff || d.gen) && d.genPrefs && !sameJ(d.genPrefs, d.prefs)) return { kind: 'gen', input: 'new-details', what: '세부 사항을', back: true };
    return null;
  };
  const lossList = st => {
    const d = S().draft, n = Object.values(d.answers || {}).filter(Boolean).length, out = [];
    if (st.kind === 'quiz') out.push(`사전 점검 문항${n ? `과 응답 ${n}개` : ''}`);
    if (st.kind !== 'gen' && d.diag) out.push(`점검 결과${d.fix || d.startStage ? ' (직접 고친 내용 포함)' : ''}`);
    if (d.gen || d.handoff) out.push(`로드맵 3안${S().draftPlan ? '과 고른 안' : ''}`);
    return out;
  };
  const staleText = st => `<p style="margin:0 0 8px">${st.what} 바꿔서 아래를 새로 만들어요.</p><ul class="plain-list">${lossList(st).map(t => `<li>${t}</li>`).join('')}</ul>
    <p class="small muted" style="margin-top:10px">${st.back ? '원래대로 되돌리면 이미 만든 결과를 그대로 써요. ' : ''}${st.kind === 'gen' ? '사전 점검 문항과 응답은 그대로예요.' : ''}</p>`;
  const staleBtns = (st, target) => `${st.back ? `<button class="btn line" data-act="stale-revert" data-arg="${target}">${icon('history')}원래대로 되돌리기</button>` : ''}<button class="btn pri" data-act="stale-go" data-arg="${target}">바꾼 내용으로 계속</button>`;
  /* 앞으로 넘어갈 때만 묻는다(뒤로 가기·홈으로 가기는 그대로 두고, 나중에 뒤 단계 화면에 들어오면 그 화면에서 묻는다) */
  GP.beforeGo = target => {
    if (!GP.me()) return true;
    const st = P.stale(); if (!st) return true;
    const fi = ORDER.indexOf(String(S().route).split(':')[0]), ti = ORDER.indexOf(String(target).split(':')[0]);
    if (fi < 0 || ti < 0 || ti <= fi || fi < ORDER.indexOf(st.input)) return true;
    GP.sheet(staleText(st), { title: '바꾼 내용으로 계속할까요?', foot: staleBtns(st, target) });
    return false;
  };
  const goOrRender = target => { if (!target || S().route === target) GP.render(false); else GP.go(target, { force: true }); };
  GP.act['stale-go'] = async target => {
    const st = P.stale(); GP.closeSheet();
    if (st) { const r = await draftCall('바꾼 내용을 반영하지 못했어요', id => API.changesApply(id, st.kind)); if (!r) return; }
    goOrRender(target);
  };
  GP.act['stale-revert'] = async target => {
    const st = P.stale(); GP.closeSheet();
    if (st && st.back) {
      const r = await draftCall('원래대로 되돌리지 못했어요', id => API.changesRevert(id, st.kind)); if (!r) return;
      GP.toast('원래대로 되돌렸어요');
    }
    goOrRender(target);
  };
  /* 입력 화면 안내: 바꾼 내용이 있으면 미리 알려 주고 바로 되돌릴 수 있게 한다(입력 중에 보이도록 onRefresh 가 켜고 끔) */
  const staleNote = kind => `<p class="note stale-note" data-stale="${kind}" hidden>${icon('info')}<span>${{ quiz: '목표·기획서를 바꿨어요. 다음으로 넘어갈 때 사전 점검 문항부터 다시 만들지 확인해요.', cert: '자격증 계획을 바꿨어요. 사전 점검 문항에 쓰이는 조건이라, 다음으로 넘어갈 때 사전 점검 문항부터 다시 만들지 확인해요.', diag: '응답을 바꿨어요. 다음으로 넘어갈 때 점검 결과부터 다시 만들지 확인해요.', gen: '세부 사항을 바꿨어요. 다음으로 넘어갈 때 로드맵 3안을 다시 만들지 확인해요.' }[kind]}
    <button type="button" class="link" data-act="stale-revert" data-arg="">원래대로 되돌리기</button></span></p>`;

  /* 입력 연결 뒤처리: 세부 사항을 바꾸면 확인 화면을 다시 거치게 한다. 진행 기록·사후 점검 응답은 바로 서버에 저장한다 */
  let postT = null;
  GP.onBindChange = (path, evt) => {
    const d = S().draft;
    if (path.startsWith('draft.prefs.')) d.detailsOk = false;
    if (d.quizFail && d.quizFail.key !== P.quizKey(d)) d.quizFail = null;
    if (path.startsWith('post.') && path !== 'post.file') {
      const R = P.R(); if (!R) return;
      clearTimeout(postT);
      postT = setTimeout(() => savePost(R), evt === 'input' ? 600 : 50);
    }
  };
  GP.onRefresh = () => {
    const c = document.getElementById('qCount'), d = S().draft;
    if (c && d.quiz) c.textContent = `${d.quiz.questions.filter(q => d.answers[q.id]).length} / ${d.quiz.questions.length}`;
    const dc = document.getElementById('dqCount');
    if (dc) { const ks = P.deepOn(d) ? Object.keys(d.quiz.deep.mcq) : []; dc.textContent = ks.length ? ` · 심화 객관식 ${ks.filter(k => (d.deepMcq || {})[k]).length} / ${ks.length}` : ''; }
    if (d.edit) { const miss = P.editMissing(d.edit); document.querySelectorAll('[data-miss]').forEach(el => { el.hidden = !miss[el.dataset.miss]; }); }
    /* 세부 사항 드롭다운: '알아서'(빈 값)면 흐린 회색 */
    document.querySelectorAll('select.df-sel').forEach(s => s.classList.toggle('empty', !s.value));
    /* 수정 요청: 고른 항목의 값이 맞지 않으면 그 칸 아래에, 수정안을 만들 수 없으면 버튼 아래에 이유를 보여 준다 */
    const rv = S().rev;
    if (rv && rv.v) {
      document.querySelectorAll('[data-rvmiss]').forEach(el => { el.hidden = P.revItemOk(rv, el.dataset.rvmiss); });
      document.querySelectorAll('[data-rvhint]').forEach(el => { el.hidden = P.revBusy() || GP.valid.revOk(); });
    }
    const st = P.stale();
    document.querySelectorAll('[data-stale]').forEach(el => { el.hidden = !st || (st.note || st.kind) !== el.dataset.stale; const b = el.querySelector('[data-act="stale-revert"]'); if (b) b.hidden = !(st && st.back); });
  };

  /* 1. 목표·기획서 */
  P.goalField = () => `<textarea class="textarea" data-bind="draft.goal" maxlength="300" aria-label="키우고 싶은 역량" placeholder="예: 사내 규정 문서로 질의응답 시제품을 만들고 싶어요.">${esc(S().draft.goal)}</textarea>${P.goalSug()}`;

  /* 목표 후보 (FR-05 · 2026-10-21 사용자 요구 1): 서버가 직원 데이터가 바뀔 때(관리자 업로드·내 정보 저장) 미리 만들어
     팀 DB(employee_recommended_prompts)에 둔다. 이 화면은 저장된 후보 3개를 보여 주기만 하고, '목표 후보 다시 만들기'를 누를 때만 다시 만든다.
     실패하면 이전 후보를 그대로 두고 안내한다(자동 재시도 없음). 본인 입력이 없으면 AI 활용 업무 기본 후보 */
  let gs = null, gsTok = 0;
  const gsPaint = () => { const b = document.getElementById('goalSug'); if (b) b.outerHTML = P.goalSug(); };
  async function loadGoals() {
    const tok = ++gsTok, owner = (GP.me() || {}).id;
    let v;
    try { v = await API.goals(); } catch (err) { v = { status: 'loadfail', loadError: AI.cause(err), candidates: [] }; }
    if (tok !== gsTok) return;
    gs = Object.assign(v, { owner, at: Date.now() }); gsPaint();
    if (gs.status === 'running' && gs.jobId) waitGoals(gs.jobId);
  }
  async function waitGoals(jobId) {
    const tok = gsTok;
    try { await API.job(jobId); } catch (e) { /* 실패 상태는 다시 읽어서 보여 준다 */ }
    if (tok === gsTok) loadGoals();
  }
  GP.act['goal-regen'] = async () => {
    if (gs && gs.status === 'running') return;
    gs = Object.assign({ candidates: [] }, gs, { status: 'running', error: null }); gsPaint();
    try {
      const r = await API.goalsRegenerate();
      if (r && r.jobId) { ++gsTok; waitGoals(r.jobId); } else loadGoals();
    } catch (err) { gs = Object.assign({}, gs, { status: 'failed', error: AI.cause(err) }); gsPaint(); }
  };
  GP.act['goal-reload'] = () => loadGoals();
  GP.dropGoals = () => { gs = null; ++gsTok; };
  P.goalSug = () => {
    const g = gs, run = g && g.status === 'running', list = (g && g.candidates) || [];
    const tag = !g || run ? '' : g.source === 'mock' ? '<span class="tag">가데이터</span>' : g.source === 'default' || g.status === 'default' ? '' : g.source ? `<span class="tag acc">${AI.PROV[g.source] || 'API'} 작성</span>` : '';
    const items = () => `<div class="gs-list${run ? ' busy' : ''}">${list.map((c, i) => `<button type="button" class="gs-it" data-act="goal-pick" data-arg="${i}" ${run ? 'disabled' : ''}><b>${esc(c.goal)}</b><small>${esc(c.why)}</small></button>`).join('')}</div>`;
    let body = '';
    if (!g) body = `<div class="agents">${P.agentRow({ st: 'run', name: '목표 후보 불러오기', sub: '서버에 저장해 둔 목표 후보를 불러오고 있어요…' })}</div>`;
    else if (g.status === 'loadfail') body = `<div class="gs-fail">${icon('alert')}<div class="grow"><b>목표 후보를 불러오지 못했어요</b><p class="small">${esc(P.errText(g.loadError))}</p></div><button type="button" class="btn line sm" data-act="goal-reload">${icon('retry')}다시 불러오기</button></div>`;
    else if (run) body = `<div class="agents">${P.agentRow({ st: 'run', name: '진단 에이전트 · 목표 후보 만들기', sub: P.runSub('default', '내 프로필(직급·직무·담당 업무·본인 입력)만 보고 지금과 다른 후보를 만들고 있어요') })}</div>${list.length ? items() : ''}`;
    else if (g.status === 'failed') {
      const c = AI.cause(g.error || {});
      body = `<div class="gs-fail">${icon('alert')}<div class="grow"><b>목표 후보를 ${list.length ? '다시 ' : ''}만들지 못했어요</b><p class="small">${esc(P.errText(c))}${list.length ? ' 이전 후보를 그대로 보여 드려요.' : ''}</p>${P.opsBox([['', c]], 'sm')}</div><button type="button" class="btn line sm" data-act="goal-regen">${icon('retry')}다시 시도</button></div>${list.length ? items() : ''}`;
    } else if (!list.length) body = `<p class="small muted" style="margin:6px 0">아직 만든 목표 후보가 없어요. 아래 ‘목표 후보 만들기’를 누르면 내 프로필로 후보 3개를 만들어요.</p>`;
    else body = `${items()}${g.status === 'default' ? P.note(`프로필에 본인 입력 정보(업무 설명·경험 요약·기술 스택)가 없어 판단 근거가 부족해요. AI 활용 업무 기본 후보를 보여 드려요. 프로필을 채우면 맞춤 후보를 다시 만들어요. <button class="link" data-go="me">${icon('user')}내 정보에서 채우기</button>`) : g.note ? `<p class="small muted gs-note">${icon('info')}${esc(g.note)}</p>` : ''}`;
    const used = g && (g.used || []).length ? `참고한 정보 · ${esc(g.used.join(', '))}${g.who ? ` (${esc(g.who)})` : ''}` : '';
    const when = g && g.updatedAt && !run ? ` · ${esc(g.updatedAt)} 저장` : '';
    const regen = g && g.status !== 'loadfail' && !run ? ` <button type="button" class="link" data-act="goal-regen">${icon('retry')}${list.length ? '목표 후보 다시 만들기' : '목표 후보 만들기'}</button>` : '';
    return `<div class="gsug" id="goalSug"><div class="gs-h"><b>${icon('spark')}목표 후보</b><span class="small muted">${g && g.status === 'default' ? 'AI 활용 업무 기본 후보' : '내 정보가 바뀔 때 미리 만들어 둬요'}</span>${tag}</div>${body}
      ${g && g.stale ? `<p class="small muted gs-note">${icon('info')}내 정보가 바뀐 뒤 아직 다시 만들지 않은 후보예요. 다시 만들면 바뀐 정보로 만들어요.</p>` : ''}
      <p class="small muted gs-f">${used}${when}${used ? ' · ' : ''}적은 목표와 기획서는 보지 않아요. <button class="link quiet" data-go="me">내 정보 보기</button>${regen}</p></div>`;
  };
  GP.act['goal-pick'] = i => {
    const c = gs && (gs.candidates || [])[+i]; if (!c) return;
    S().draft.goal = c.goal; GP.onBindChange('draft.goal'); GP.save();
    const t = document.querySelector('[data-bind="draft.goal"]'); if (t) { t.value = c.goal; t.focus(); }
    GP.refresh(); GP.toast('목표 칸에 넣었어요. 내 말로 고쳐 써도 돼요');
  };

  /* 기획서 읽기 (10/14 → 5차 서버): 파일을 서버에 올리면 서버가 글자를 꺼내고(API-20) 이미지 보기·요약을 작업으로 이어 한다(API-21).
     요약은 화면에서 고칠 수 있고, 요약만 문항·진단·로드맵 에이전트에게 넘긴다. 실패하면 '다시 시도'를 눌러야만 다시 읽는다.
     이미지 내용은 DB에 넣지 않고 서버 메모리에만 잠깐 둔다(서버를 다시 켜면 이미지는 다시 고른 파일로만 볼 수 있음) */
  let docErr = null;   // 글자 꺼내기 실패: 서버에 기획서가 저장되지 않아 화면에만 안내를 둔다
  const DOC_STEP = { extract: '파일을 서버에 올려 글자와 이미지를 꺼내고 있어요', vision: '기획서 이미지를 보고 있어요', summary: '기획서를 요약하고 있어요' };
  async function uploadProject(file) {
    const st = GP.own();
    docErr = null;
    try {
      const id = await GP.ensureDraft();
      const r = await API.projectFile(id, file);
      if (GP.own() !== st) return;
      GP.takeDraft(r, true);
    } catch (err) {
      if (GP.own() !== st) return;
      st.draft.project = null; st.draft.doc = null; docErr = { name: file.name, cause: AI.cause(err) }; GP.save();
    }
    if (S().route === 'new-goal') GP.render(false);
  }
  GP.onFile = (path, f) => {
    if (path === 'draft.project' && f) { S().draft.doc = { name: f.name, status: 'reading', step: 'extract' }; uploadProject(f); }
    if (path === 'post.file' && f) postFile(f);
  };
  GP.valid.docIdle = () => { const doc = S().draft.doc; return !doc || doc.status !== 'reading'; };
  const docAgain = async skipImages => {
    const d = S().draft; if (!d.doc) return;
    d.doc.status = 'reading'; d.doc.fail = null; GP.render(false);
    await draftCall('기획서를 다시 읽지 못했어요', id => API.projectSummary(id, skipImages));
    await P.pullDraft();
    if (S().route === 'new-goal') GP.render(false);
  };
  /* 다시 시도: 이미지 보기·요약은 서버가 꺼내 둔 글자로 다시 한다(이미지를 잃었으면 글자만). 글자 꺼내기 실패는 파일을 다시 골라야 한다 */
  GP.act['doc-retry'] = () => docAgain(false);
  GP.act['doc-skip-images'] = () => docAgain(true);
  const kb = n => `${Math.max(1, Math.round(n / 1024))}KB`;
  /* 이미지 안내: 읽은 이미지 / 읽지 않은 이유 (비전 모델 없음·가데이터·작은 아이콘 등) */
  function imageLine(doc) {
    const sk = doc.imageSkipped || {}, other = (sk.small || 0) + (sk.big || 0) + (sk.format || 0) + (sk.more || 0);
    if (!doc.imageTotal) return '';
    const why = [sk.small && `작은 아이콘 ${sk.small}`, sk.big && `1.5MB가 넘는 이미지 ${sk.big}`, sk.format && `EMF·WMF 같은 형식 ${sk.format}`, sk.more && `4장을 넘는 이미지 ${sk.more}`].filter(Boolean).join(', ');
    if (doc.imagesRead) return `이미지 ${doc.imagesRead}장을 비전 모델이 보고 요약에 합쳤어요.${other ? ` 그 밖의 ${other}개(${why})는 보지 않았어요.` : ''}`;
    const base = { mock: '가데이터 모드라 이미지는 보지 않았어요.', novision: '이미지를 볼 수 있는 AI 모델이 설정되지 않아 이미지는 보지 않았어요.', skip: '이미지는 건너뛰고 글자만 요약했어요.', lost: '서버를 다시 켜 이미지는 보지 못했어요. 이미지까지 보려면 파일을 다시 골라 주세요.', none: '읽을 수 있는 크기·형식의 이미지가 없어 보지 않았어요.' }[doc.visionWhy] || '이미지는 보지 않았어요.';
    return `이미지 ${doc.imageTotal}개 · ${base}${doc.visionWhy === 'none' && why ? ` (${why})` : ''} 그림·도표의 중요한 내용은 요약에 직접 적어 주세요.`;
  }
  const docFailBox = (title, c, actions) => `<div class="docbox fail"><p class="db-h">${icon('alert')}<b>${title}</b></p>
    <p class="small">${esc(P.errText(c))}</p>${P.opsBox([['', c]], 'sm')}<div class="db-act">${actions}</div></div>`;
  P.docBox = function () {
    const d = S().draft, doc = d.doc; if (!doc) return '';
    if (doc.status === 'reading') return `<div class="docbox"><div class="agents">${P.agentRow({ st: 'run', name: '진단 에이전트 · 기획서 읽기', sub: P.runSub(doc.step === 'vision' ? 'vision' : 'default', DOC_STEP[doc.step] || DOC_STEP.extract) })}</div></div>`;
    if (doc.status === 'fail') {
      const c = AI.cause((doc.fail || {}).cause || {}), visionFail = doc.step === 'vision';
      return docFailBox(visionFail ? '기획서 이미지를 보지 못했어요' : doc.step === 'summary' ? '기획서를 요약하지 못했어요' : '기획서를 읽지 못했어요', c,
        `<button type="button" class="btn line sm" data-act="doc-retry">${icon('retry')}다시 시도</button>${visionFail ? '<button type="button" class="btn line sm" data-act="doc-skip-images">이미지 없이 요약</button>' : ''}<span class="small muted">기획서 없이 목표만으로 진행해도 돼요.</span>`);
    }
    const meta = [doc.format, doc.pages ? `${doc.pages}쪽` : '', `글자 ${(doc.chars || 0).toLocaleString('ko-KR')}자`, doc.chars > AI.DOC_CHARS ? `앞 ${AI.DOC_CHARS.toLocaleString('ko-KR')}자로 요약` : ''].filter(Boolean).join(' · ');
    const src = doc.source && doc.source !== 'mock' ? `${AI.PROV[doc.source]} 요약` : '가데이터 요약';
    const warn = (doc.warnings || []).map(w => `<p class="small warn-t">${icon('info')}${esc(w)}</p>`).join('');
    return `<div class="docbox"><div class="db-top"><p class="eyebrow">${icon('spark')}기획서 요약 · 진단 에이전트</p><span class="tag ${doc.source && doc.source !== 'mock' ? 'acc' : ''}">${src}</span></div>
      <p class="small muted db-meta">${esc(meta)}</p>${warn}
      ${doc.summary || doc.text ? `<textarea class="textarea sm" data-bind="draft.doc.summary" maxlength="1500" aria-label="기획서 요약" rows="6">${esc(doc.summary)}</textarea>
      <p class="small muted">틀리거나 빠진 내용은 직접 고쳐 주세요. 이 요약만 사전 점검·진단·로드맵 에이전트에게 넘어가요.</p>` : '<p class="small muted">요약할 글자를 찾지 못했어요. 기획서 없이 목표만으로 진행해요.</p>'}
      ${imageLine(doc) ? `<p class="small db-img">${icon('file')}${esc(imageLine(doc))}</p>${doc.visionWhy === 'novision' ? P.opsBox([['', { text: '비전 모델 설정 없음', hint: '.env에 OLLAMA_VISION_MODEL(RunPod-Ollama) 또는 OPENAI_VISION_MODEL(OpenAI API)을 넣고 서버를 다시 실행하면 이미지도 읽어요' }]], 'sm') : ''}` : ''}</div>`;
  };
  P.projectField = function () {
    const f = S().draft.project;
    if (f) return `<div class="file-on">${icon('file')}<div class="tx"><b>${esc(f.name)}</b><small class="muted">${kb(f.size || 0)}</small></div><button class="link quiet" data-act="clear-project">빼기</button></div>${P.docBox()}`;
    return `${docErr ? docFailBox(`‘${esc(docErr.name)}’을 읽지 못했어요`, docErr.cause, '<span class="small muted">다른 파일을 고르거나, 기획서 없이 목표만으로 진행해도 돼요.</span>') : ''}
      <label class="drop"><input type="file" data-bind-file="draft.project" accept=".pdf,.docx,.hwp,.hwpx,.pptx,.txt,.md"><span class="ico">${icon('file')}</span><span><b>기획서 파일 고르기</b><small>PDF, 한글(HWP·HWPX), 워드(DOCX), 파워포인트(PPTX), TXT · 15MB까지 · 선택</small></span></label>`;
  };
  GP.act['clear-project'] = async () => {
    const d = S().draft; docErr = null;
    d.project = null; d.doc = null; GP.render(false);
    if (draftId()) await draftCall('기획서를 빼지 못했어요', id => API.projectClear(id), { soft: true });
    GP.onBindChange('draft.project'); GP.save(); GP.render(false);
  };
  scr['new-goal'] = {
    nav: 'new', newStep: true, title: '새 로드맵 작성', width: 'wide',
    render: () => GP.stepper('goal') + P.page({
      title: '어떤 역량을 키우고 싶나요?', lead: '목표와, 적용할 프로젝트 기획서가 있으면 함께 알려 주세요. 기획서는 진단 에이전트가 읽고 요약해요. 학습 여건은 다음 단계에서 적어 주세요(모두 선택).',
      body: `<div class="card"><div class="field"><label>키우고 싶은 역량</label>${P.goalField()}</div><hr class="hr">
        <div class="field"><label>적용할 프로젝트 기획서 <span class="muted small">선택</span></label>${P.projectField()}</div></div>
        ${staleNote('quiz')}`,
      foot: `<button class="btn pri" data-go="new-details" data-need="goal,docIdle">다음: 세부 사항</button>`
    }),
    /* 목표 후보는 화면에 들어올 때 서버에 저장된 것을 읽는다(만들지 않음 · 30초 안에 다시 들어오면 읽은 것을 씀).
       기획서를 읽는 중이면 서버 진행 상태를 이어서 본다 */
    after() {
      const me = GP.me();
      if (!gs || gs.owner !== me.id || Date.now() - gs.at > 30000) loadGoals();
      P.watchDraft();
    }
  };

  /* 2. 세부 사항: 학습 선호 5가지 + 기타 고려 사항을 입력 폼으로 받는다(10/13: 대화 대신 폼).
     모두 선택 사항이고, 비워 둔 칸은 흐린 회색 기본값으로 둔다: 자격증 계획은 '계획 없음', 나머지는 '알아서'(진단·로드맵 계획 에이전트가 정함).
     같은 폼을 점검 결과 수정 화면에서도 쓴다(path 만 다름) */
  const fieldLabel = k => (D.detailFields.find(f => f[0] === k) || [])[1] || '';

  /* 자격증 계획 드롭다운: 분야 → 자격 2단계(팀 DB 자격증 · 폐지·폐지 예정·상태 미확인 제외 · 2026-10-21 사용자 결정).
     분야를 누르면 같은 창이 그 분야의 자격 목록으로 바뀌고 '‹ 분야'로 돌아온다(PC·모바일 같은 모양 · 키보드 ↑↓ → ← Esc) */
  const cpName = v => { const c = D.certById[v]; return c ? c.name : '계획 없음'; };
  P.certPick = (path, v) => `<div class="cpick" data-path="${path}">
      <button type="button" class="input cp-btn${D.certById[v] ? '' : ' empty'}" data-act="cp-open" aria-haspopup="true" aria-expanded="false" aria-label="${fieldLabel('cert')}"><span class="cp-v">${esc(cpName(v))}</span></button>
      <div class="cp-pop" hidden></div></div>`;
  function cpLevel(path, g) {
    const v = GP.getP(path) || '', cur = D.certById[v], mark = on => `<span class="cp-ck">${on ? icon('check') : ''}</span>`;
    if (!g) return `<button type="button" class="cp-it${cur ? '' : ' on'}" data-act="cp-pick" data-arg="">${mark(!cur)}<span class="cp-tx">계획 없음<small>자격 준비를 넣지 않아요</small></span></button><div class="cp-sep"></div>`
      + D.certGroups.map(x => `<button type="button" class="cp-it grp${cur && cur.group === x.key ? ' has' : ''}" data-act="cp-group" data-arg="${x.key}">${mark(cur && cur.group === x.key)}<span class="cp-tx">${esc(x.label)}${cur && cur.group === x.key ? `<small>${esc(cur.name)}</small>` : ''}</span><span class="cp-n">${x.certs.length}</span>${icon('right')}</button>`).join('');
    const grp = D.certGroups.find(x => x.key === g);
    let vendor = null;
    /* 시행 기관이 하나인 분야는 기관을 맨 위에 한 번만 쓴다 */
    return `<button type="button" class="cp-back" data-act="cp-group" data-arg="">${icon('left')}<span>${esc(grp.label)}${grp.issuer ? `<small>${esc(grp.issuer)}</small>` : ''}</span></button>`
      + grp.certs.map(c => {
        const head = c.vendor && c.vendor !== vendor ? `<p class="cp-sub">${esc(c.vendor)}</p>` : ''; vendor = c.vendor || vendor;
        const meta = c.vendor ? '' : [c.sub, grp.issuer ? '' : c.issuer].filter(Boolean).join(' · ');
        return `${head}<button type="button" class="cp-it${c.id === v ? ' on' : ''}" data-act="cp-pick" data-arg="${c.id}">${mark(c.id === v)}${P.thumb({ type: 'cert', image: c.image }, 'xs')}<span class="cp-tx">${esc(c.short)}${meta ? `<small>${esc(meta)}</small>` : ''}</span></button>`;
      }).join('');
  }
  const cpItems = box => [...box.querySelectorAll('.cp-pop button')];
  /* 단계 그리기: 고른 항목(또는 고른 자격이 든 분야)에, 없으면 첫 항목에 초점. 분야 목록으로 돌아올 때는 방금 본 분야에 */
  function cpShow(box, g, from) {
    const pop = box.querySelector('.cp-pop');
    pop.innerHTML = cpLevel(box.dataset.path, g); pop.dataset.level = g || ''; pop.scrollTop = 0;
    const t = (from && pop.querySelector(`.cp-it.grp[data-arg="${from}"]`)) || pop.querySelector('.cp-it.on, .cp-it.has') || pop.querySelector('.cp-it');
    if (t) t.focus();
  }
  function cpClose(box, refocus) {
    const pop = box.querySelector('.cp-pop'), btn = box.querySelector('.cp-btn');
    pop.hidden = true; pop.innerHTML = ''; box.classList.remove('open'); btn.setAttribute('aria-expanded', 'false');
    if (refocus) btn.focus();
  }
  GP.act['cp-open'] = (arg, el) => {
    const box = el.closest('.cpick');
    if (box.classList.contains('open')) return cpClose(box);
    document.querySelectorAll('.cpick.open').forEach(b => cpClose(b));
    if (!D.certGroups.length) { GP.toast('자격증 목록을 불러오지 못했어요 · 서버 연결을 확인해 주세요'); return; }
    const cur = D.certById[GP.getP(box.dataset.path)];
    box.classList.add('open'); el.setAttribute('aria-expanded', 'true'); box.querySelector('.cp-pop').hidden = false;
    cpShow(box, cur ? cur.group : '');
  };
  GP.act['cp-group'] = (g, el) => { const box = el.closest('.cpick'); cpShow(box, g, g ? '' : box.querySelector('.cp-pop').dataset.level); };
  GP.act['cp-pick'] = (id, el) => {
    const box = el.closest('.cpick'), path = box.dataset.path, btn = box.querySelector('.cp-btn');
    GP.setP(path, id); GP.save();
    btn.querySelector('.cp-v').textContent = cpName(id); btn.classList.toggle('empty', !D.certById[id]);
    cpClose(box, true);
    if (GP.onBindChange) GP.onBindChange(path);
    GP.refresh();
  };
  /* 바깥을 누르면 닫기 (창 안 버튼은 눌린 뒤 내용이 바뀌므로 눌린 순간의 경로로 판단) */
  document.addEventListener('click', e => { const path = e.composedPath(); document.querySelectorAll('.cpick.open').forEach(b => { if (!path.includes(b)) cpClose(b); }); });
  document.addEventListener('keydown', e => {
    const box = e.target.closest && e.target.closest('.cpick.open'); if (!box) return;
    const items = cpItems(box), i = items.indexOf(e.target), lvl = box.querySelector('.cp-pop').dataset.level;
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cpClose(box, true); }
    else if (e.key === 'Tab') cpClose(box);
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); const n = items.length, j = i < 0 ? 0 : (i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n; items[j].focus(); }
    else if (e.key === 'ArrowRight' && e.target.matches('.cp-it.grp')) { e.preventDefault(); e.target.click(); }
    else if (e.key === 'ArrowLeft' && lvl) { e.preventDefault(); cpShow(box, '', lvl); }
  }, true);

  P.detailsForm = function (path) {
    const p = GP.getP(path) || {};
    const sel = (k, opts) => `<select class="input df-sel ${p[k] ? '' : 'empty'}" data-bind="${path}.${k}" aria-label="${fieldLabel(k)}"><option value="">알아서</option>${opts.map(([v, l]) => `<option value="${esc(v)}" ${String(p[k]) === String(v) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    const num = (k, unit, attrs) => `<div class="unit"><input class="input num" type="number" ${attrs} data-bind="${path}.${k}" value="${esc(p[k])}" placeholder="알아서" aria-label="${fieldLabel(k)}"><span>${unit}</span></div>`;
    const f = (k, ctl, help, wide) => `<div class="field${wide ? ' wide' : ''}"><label>${fieldLabel(k)}</label>${ctl}<small class="muted df-help">${help}</small></div>`;
    return `<div class="dform">
      ${f('format', sel('format', D.formatOpts), '비워 두면 목표와 자료에 맞게 정해요')}
      ${f('cert', P.certPick(`${path}.cert`, p.cert), `분야를 고른 뒤 자격을 골라 주세요(${D.certGroups.reduce((s, g) => s + g.certs.length, 0)}종). 고르지 않으면 자격 준비는 넣지 않아요`)}
      ${f('hours', num('hours', '시간 / 주', 'min="0.5" max="40" step="0.5"'), '비워 두면 로드맵 계획 에이전트가 목표와 기간에 맞게 정해요')}
      ${f('weeks', num('weeks', '주 안에', 'min="1" max="52" step="1"'), '비워 두면 기간을 정하지 않아요')}
      ${f('budget', num('budget', '원', 'min="0" step="10000"'), '0을 넣으면 무료 자료만 써요. 비워 두면 알아서 골라요')}
      ${f('etc', `<textarea class="textarea sm" data-bind="${path}.etc" maxlength="500" aria-label="${fieldLabel('etc')}" placeholder="예: 다음 달 둘째 주는 출장이 많아요. 영상 강의는 사내망에서 열리지 않아요.">${esc(p.etc)}</textarea>`, '로드맵을 만들 때 고려할 상황을 자유롭게 적어 주세요. 로드맵 계획 에이전트에게 그대로 전달해요', true)}
    </div>`;
  };
  scr['new-details'] = {
    nav: 'new', newStep: true, title: '세부 사항', width: 'wide', guard: () => blockedTo('details'),
    render: () => GP.stepper('details') + P.page({
      title: '학습 여건을 알려 주세요',
      lead: '모두 선택 사항이에요. 비워 둔 칸은 ‘알아서’로 두고 로드맵 계획 에이전트가 목표에 맞게 정해요. 자격증 계획은 고르지 않으면 ‘계획 없음’이에요.',
      body: `<div class="card">${P.detailsForm('draft.prefs')}</div>${staleNote('gen')}${staleNote('cert')}${S().draft.quiz ? P.note('사전 점검 문항은 이미 만들었어요. 자격증 계획을 바꾸면 문항부터 다시 만들고, 나머지는 로드맵을 만들 때 반영해요.') : ''}`,
      foot: `<button class="btn line" data-go="new-goal">${icon('left')}이전</button><button class="btn pri" data-go="new-details-check">다음: 입력 내용 확인</button>`
    })
  };

  /* 2-1. 세부 사항 확인: 입력한 내용(빈 칸은 '알아서')과 진단 에이전트 연결 상태를 보여 주고, '다음'을 누르면 사전 점검 문항을 만든다 */
  P.detailsView = p => `<div class="card acc preview">
      <p class="eyebrow">${icon('spark')}진단 에이전트에게 넘길 세부 사항</p>
      <dl class="kv">${D.detailFields.map(([k, l]) => `<dt>${l}</dt><dd class="${AI.prefAuto(k, p) ? 'auto' : ''}${k === 'etc' ? ' etc' : ''}">${esc(AI.prefText(k, p))}</dd>`).join('')}</dl></div>`;
  /* 진단 에이전트 연결 상태: 가데이터 / 확인 중 / 연결됨 / 모델 대기 중(Ollama · 모델이 아직 GPU에 없음) / 연결 안 됨.
     좌측 'AI 모델'에서 고른 모드를 서버가 확인하고(API-12), 이후 호출 결과로 갱신 */
  const via = role => `${AI.PROV[AI.mode()]} · ${esc(AI.modelName(role))}`;
  P.connView = function () {
    if (!AI.live()) return `<span class="conn off"><i></i>${AI.demoMock() ? '가데이터 모드 · LLM에 연결하지 않아요' : `${AI.PROV[AI.choice()]}를 지금 쓸 수 없어요 · 가데이터로 자동 대체하지 않아요`}</span>`;
    const c = AI.connFor('default'), st = c.state === 'idle' ? 'checking' : c.state;
    const lbl = { ok: '연결됨', cold: '모델 준비 중', error: '연결 안 됨', checking: '연결 확인 중…' }[st];
    const ms = st === 'ok' && c.ms ? `<span class="small muted num">${c.via === 'ping' ? '확인' : '최근 응답'} ${(c.ms / 1000).toFixed(1)}초${c.loadMs > 500 ? ` · 모델 불러오기 ${(c.loadMs / 1000).toFixed(1)}초 포함` : ''}</span>` : '';
    const re = st !== 'checking' ? `<button class="link quiet" data-act="conn-check">${icon('retry')}다시 확인</button>` : '';
    return `<span class="conn ${st}"><i></i>${lbl} · ${via('default')}</span>${ms}${re}`;
  };
  /* 연결 안내도 사용자에게는 쉬운 말과 할 일만, 원인·조치·원문은 운영자용으로 접어 둔다(10/14) */
  P.connOps = (c, cls) => P.opsBox([['', { text: c.error, hint: c.hint, raw: c.raw && c.raw !== c.error ? c.raw : '' }]], cls);
  P.coldOps = (c, cls) => P.opsBox([['', { text: `모델이 아직 GPU에 올라가 있지 않음 (${(c.waiting || []).join(', ')})`, hint: '첫 호출 때 GPU에 올려요. 미리 올려 두려면 Pod에서 그 모델을 한 번 호출해 두세요' }]], cls);
  P.connErr = function () {
    /* 고른 모드를 쓸 수 없음(설계서 v1.7 그림 12): 가데이터로 바꾸지 않는다는 것과 할 일을 알린다 */
    if (AI.off()) return `<div class="conn-err" role="alert">${icon('alert')}<div><b>${esc(AI.userText('off'))}.</b> ${esc(AI.userTodo('off').join(' '))}${P.opsBox([['', { text: AI.unavailableWhy(AI.choice()), hint: AI.status.server ? '.env를 고친 뒤 서버(목업_실행.cmd)를 다시 실행해 주세요' : '목업_실행.cmd로 서버를 켜 주세요' }]], 'sm')}</div></div>`;
    if (!AI.live()) return '';
    const c = AI.connFor('default');
    if (c.state === 'cold') return `<div class="conn-err cold">${icon('info')}<div><b>AI 모델을 준비하고 있어요.</b> 첫 문항 생성은 1~2분 걸릴 수 있어요.${P.coldOps(c)}</div></div>`;
    if (c.state !== 'error') return '';
    return `<div class="conn-err" role="alert">${icon('alert')}<div><b>${esc(AI.userText(c.kind))}.</b> ${esc(AI.userTodo(c.kind).join(' '))} 이대로 넘어가면 사전 점검 문항을 만들지 못할 수 있어요.${P.connOps(c)}</div></div>`;
  };
  P.connBox = () => `<div class="connbox"><div class="cb-h">${icon('spark')}진단 에이전트<span class="conn-w" id="dConn" aria-live="polite">${P.connView()}</span></div><div id="dConnErr">${P.connErr()}</div></div>`;
  const baseConn = GP.onConn;
  GP.onConn = () => { if (baseConn) baseConn(); const w = document.getElementById('dConn'); if (w) w.innerHTML = P.connView(); const e = document.getElementById('dConnErr'); if (e) e.innerHTML = P.connErr(); };
  GP.act['conn-check'] = () => AI.ping();
  scr['new-details-check'] = {
    nav: 'new', newStep: true, title: '세부 사항 확인', width: 'wide', guard: () => blockedTo('details'),
    render() {
      const d = S().draft, made = !!(d.quiz && d.quiz.key === P.quizKey(d));
      return GP.stepper('details') + P.page({
        eyebrow: '세부 사항 확인', title: made ? '입력한 세부 사항이에요' : '이 내용으로 사전 점검을 만들까요?',
        lead: made ? '사전 점검 문항은 이미 만들었어요. ‘다음’을 누르면 사전 점검으로 넘어가요. 여기 내용은 로드맵을 만들 때 반영해요.'
          : '‘다음’을 누르면 진단 에이전트가 목표·기획서 요약·자격증 계획으로 사전 점검 문항을 만들어요. 나머지 항목은 로드맵을 만들 때 반영하고, ‘알아서’인 항목은 로드맵 계획 에이전트가 목표에 맞게 정해요.',
        body: `<p class="small muted goal-line">목표 · ${esc(d.goal)}</p>${P.docSummary(d) ? `<div class="card flat doc-line"><p class="eyebrow">${icon('file')}기획서 요약 · ${esc(d.doc.name)}</p><p class="pre small">${esc(P.docSummary(d))}</p></div>` : ''}${P.detailsView(d.prefs)}${P.connBox()}`,
        foot: `<button class="btn line" data-go="new-details">${icon('edit')}수정</button><button class="btn pri" data-act="details-ok">다음: 사전 점검</button>`
      });
    },
    after() { if (AI.live() && (AI.conn.provider !== AI.mode() || AI.conn.state === 'idle' || Date.now() - AI.conn.at > 60000)) AI.ping(); }
  };
  GP.act['details-ok'] = () => { S().draft.detailsOk = true; GP.save(); GP.go('new-quiz'); };

  /* 3. 사전 점검 (5점 척도: 1 전혀 아님 · 2 아님 · 3 보통이다 · 4 그렇다 · 5 매우 그렇다) · 사후 점검도 같은 문항 */
  P.likRow = (q, path, pre) => {
    const cur = String(GP.getP(`${path}.${q.id}`) || '');
    return `<div class="qrow"><p>${esc(q.text)}${pre ? `<small class="muted">사전 응답: ${esc(P.ansLabel(pre))}</small>` : ''}</p><div class="lik" role="radiogroup" aria-label="${esc(q.text)}">${D.answerOpts.map(([v, l]) => `<label><input type="radio" name="${path}.${q.id}" value="${v}" data-bind="${path}.${q.id}" ${cur === v ? 'checked' : ''}><b>${v}</b><span>${l}</span></label>`).join('')}</div></div>`;
  };
  /* 심화 질문(10/23 · 고른 사람만): 자가 진단 문항 바로 아래에 같은 개념의 객관식, 영역 카드 끝에 서술형 하나.
     dq = { quiz: 심화 문항, mcq: 객관식 답 경로, essay: 서술형 답 경로 } (사전은 draft.*, 사후는 post.deep.*) */
  P.mcqRow = (id, m, path) => {
    const cur = String(GP.getP(`${path}.${id}`) || '');
    const opt = (v, t) => `<label class="dq-opt${v === 'dk' ? ' dk' : ''}"><input type="radio" name="${path}.${id}" value="${v}" data-bind="${path}.${id}" ${cur === v ? 'checked' : ''}><span>${esc(t)}</span></label>`;
    return `<div class="dq"><p class="dq-q"><span class="dq-tag">심화 · 객관식</span>${esc(m.q)}</p><div class="dq-opts" role="radiogroup" aria-label="${esc(m.q)}">${m.options.map((o, i) => opt(String(i), o)).join('')}${opt('dk', '잘 모르겠어요')}</div></div>`;
  };
  P.essayBox = (e, path) => `<div class="dq dq-essay"><p class="dq-q"><span class="dq-tag">심화 · 서술형</span>${esc(e.q)}</p><textarea class="textarea sm" data-bind="${path}.${e.id}" maxlength="2000" aria-label="${esc(e.q)}" placeholder="2~3문장으로 써 주세요. 비워 두면 ‘답 없음’으로 봐요.">${esc(GP.getP(`${path}.${e.id}`) || '')}</textarea></div>`;
  P.quizBody = (questions, path, preMap, dq) => {
    const areas = [...new Set(questions.map(q => q.area))];
    return areas.map(a => `<div class="card qcard"><h2 class="st">${esc(a)}</h2>${questions.filter(q => q.area === a).map(q => P.likRow(q, path, preMap && preMap[q.id])
      + (dq && dq.quiz.mcq[q.id] ? P.mcqRow(q.id, dq.quiz.mcq[q.id], dq.mcq) : '')).join('')}${dq ? dq.quiz.essays.filter(e => e.area === a).map(e => P.essayBox(e, dq.essay)).join('') : ''}</div>`).join('');
  };
  P.deepToggle = (on, nm, ne) => `<div class="card deep-opt${on ? ' on' : ''}"><button type="button" class="deep-tg" data-act="deep-toggle" aria-pressed="${on}"><span class="box">${on ? icon('check') : ''}</span><b>심화 질문도 풀어 볼게요</b><span class="muted small">선택</span></button>
    <p class="small muted">자가 진단 문항마다 같은 개념을 묻는 객관식 ${nm}개와 영역마다 서술형 ${ne}개가 더 나와요. 풀면 진단 에이전트가 자기평가와 함께 보고 로드맵을 더 맞춰요. 정답과 모범 답안은 다음 단계(점검 결과)에서 펼쳐 볼 수 있어요.</p></div>`;
  GP.act['deep-toggle'] = () => { const d = S().draft; d.deepOn = !d.deepOn; GP.save(); GP.render(false); };
  /* 정답·해설·모범 답안(접어 둠): 사전은 점검 결과, 사후는 결과 보고서. 문항별 맞음·틀림까지 보여 주고 전체 정답 수는 보여 주지 않는다(10/23) */
  const RES_TAG = { '맞음': 'ok', '틀림': 'bad', '모름': 'mid', '답 안 함': 'mid' }, LV_TAG = { '충분': 'ok', '부분': 'mid', '부족': 'bad' };
  P.deepReveal = (questions, dq, mcqAns, essayAns, grade, judge, title) => {
    if (!dq || !grade) return '';
    const items = questions.filter(q => dq.mcq[q.id]).map(q => {
      const m = dq.mcq[q.id], g = grade[q.id] || {}, v = String((mcqAns || {})[q.id] || '');
      const mine = v === 'dk' ? '잘 모르겠어요' : v !== '' ? m.options[+v] : '답 안 함';
      return `<li class="dr-item"><p class="dr-q"><span class="small muted">${esc(q.area)} · 객관식</span>${esc(m.q)}</p>
        <p class="small">내 답 · ${esc(mine)} <span class="dr-tag ${RES_TAG[g.result] || 'mid'}">${esc(g.result || '')}</span></p>
        <p class="small">정답 · <b>${esc(m.options[m.answer])}</b></p>${m.explain ? `<p class="small muted">${esc(m.explain)}</p>` : ''}</li>`;
    }).join('');
    const es = dq.essays.map(e => {
      const j = (judge || {})[e.id] || {};
      return `<li class="dr-item"><p class="dr-q"><span class="small muted">${esc(e.area)} · 서술형</span>${esc(e.q)}</p>
        <p class="small pre">내 답 · ${esc(String((essayAns || {})[e.id] || '').trim() || '쓰지 않음')}</p>
        <p class="small">판단 · <span class="dr-tag ${LV_TAG[j.level] || 'mid'}">${esc(j.level || '판단 못 함')}</span> ${esc(j.why || '')}</p>
        <p class="small">핵심 요소 · ${esc((e.points || []).join(' / '))}</p>${e.model ? `<p class="small muted">모범 답안 · ${esc(e.model)}</p>` : ''}</li>`;
    }).join('');
    return `<details class="card deep-ans"><summary><b>${esc(title)}</b><span class="small muted">객관식 ${Object.keys(dq.mcq).length} · 서술형 ${dq.essays.length} · 누르면 펼쳐요</span></summary><ol class="plain-list dr-list">${items}${es}</ol></details>`;
  };
  /* 생성 실패 안내 (사전 점검 문항 · 점검 결과 · 로드맵 3안 · 결과 보고서 공통)
     빨간 안내 → 오류 원인(쉬운 말과 할 일) → 에이전트별 상태 → 자세히 보기(운영자용, 접힘) → 버튼. 다시 시도는 버튼을 눌러야만 한다 */
  P.failPage = o => `<section class="fail-card" role="alert"><span class="ico">${icon('alert')}</span><div><h1>${o.title}</h1><p>${o.desc}</p></div></section>
    <div class="cause">${icon('info')}<p><b>오류 원인 안내:</b> ${o.cause}</p></div>
    ${o.body || ''}${o.ops || ''}<div class="actions">${o.foot}</div>${o.hint ? `<p class="small muted fail-hint">${o.hint}</p>` : ''}`;
  /* 에이전트 진행 줄: run 작성 중(회전) / ok 완료(체크) / fail 실패(빨간 X · 원인 · 다시 시도) */
  P.agentRow = o => `<div class="agent ${o.st}${o.warn ? ' warn' : ''}"><span class="sp">${o.st === 'ok' ? icon('check') : o.st === 'fail' ? icon('x') : ''}</span>
    <div class="ag-tx"><b>${o.name}</b>${o.st === 'fail' ? `<span class="fl">${o.failLabel || '생성 실패'}</span>` : ''}${o.sub ? `<small>${o.sub}</small>` : ''}</div>
    ${o.tag ? `<span class="tag ${o.tagCls || ''}">${o.tag}</span>` : ''}${o.retry ? `<button class="btn line sm" data-act="${o.retry[0]}" data-arg="${o.retry[1]}">${icon('retry')}다시 시도</button>` : ''}
    ${o.st === 'fail' && o.detail ? `<div class="detail">${o.detail}</div>` : ''}</div>`;
  /* 생성 중 줄의 설명: 실제 모델이면 모드·모델 이름을, Ollama 모델이 아직 GPU에 없으면 첫 호출이 느리다는 안내를 붙인다 */
  P.runSub = (role, t) => (!AI.live() ? `${t}…` : AI.connFor(role).state === 'cold' ? `AI 모델을 준비하는 중이에요. 첫 생성은 1~2분 걸릴 수 있어요 · ${via(role)}` : `${t} · ${via(role)}`);

  /* 문항 생성(API-23): 서버 작업으로 만들고, 진행 상태(quizRun)·실패(quizFail)는 서버 작성 문서에 남는다.
     실패는 가데이터로 대신하지 않고, '다시 시도하기'를 눌러야만 다시 만든다(10/14) */
  let quizAsk = '';
  async function ensureQuiz(retry) {
    const d = S().draft, key = P.quizKey(d);
    if ((d.quiz && d.quiz.key === key) || (d.quizRun && d.quizRun.key === key)) return P.watchDraft();
    if (quizAsk === key || (!retry && d.quizFail && d.quizFail.key === key)) return;
    quizAsk = key;
    const r = await draftCall('사전 점검 문항을 만들지 못했어요', id => API.assessment(id));
    quizAsk = '';
    if (!r) return;
    await P.pullDraft();
    if (S().route === 'new-quiz') GP.render(false);
  }
  GP.act['quiz-retry'] = () => { S().draft.quizFail = null; GP.render(false); ensureQuiz(true); };
  const QUIZ_AGENT = '진단 에이전트 · 사전 점검 문항 생성';
  scr['new-quiz'] = {
    nav: 'new', newStep: true, title: '사전 점검', width: 'wide', guard: () => blockedTo('quiz'),
    render() {
      const d = S().draft, key = P.quizKey(d), ready = d.quiz && d.quiz.key === key, err = !ready && !d.quizRun && d.quizFail && d.quizFail.key === key ? AI.cause(d.quizFail.cause) : null;
      if (err) return GP.stepper('quiz') + P.failPage({
        title: '사전 점검 문항을 만드는 중 문제가 발생했어요',
        desc: '진단 에이전트가 목표와 세부 사항으로 점검 문항을 만들지 못했어요. 입력한 목표와 세부 사항은 그대로 남아 있어요.',
        cause: esc(P.errText(err)),
        body: `<div class="agents">${P.agentRow({ st: 'fail', name: QUIZ_AGENT, sub: AI.live() ? via('default') : '', tag: '오류 발생', tagCls: 'fail' })}</div>`,
        ops: P.opsBox([['', err]]),
        foot: `<button class="btn line" data-go="new-goal">${icon('left')}목표·기획서 고치기</button><button class="btn pri" data-act="quiz-retry">${icon('retry')}다시 시도하기</button>`
      });
      return GP.stepper('quiz') + P.page({
        title: ready ? `사전 점검 · ${d.quiz.questions.length}문항` : '사전 점검',
        lead: '목표와 세부 사항을 바탕으로 진단 에이전트가 만든 문항이에요. 문장마다 나에게 맞는 정도를 1~5점으로 골라 주세요. 진단 에이전트가 계산한 수준값은 보여드리지 않아요.',
        body: ready ? `${d.quiz.deep ? P.deepToggle(!!d.deepOn, Object.keys(d.quiz.deep.mcq).length, d.quiz.deep.essays.length) : AI.live() ? `<p class="small muted">이번 문항에는 심화 질문이 만들어지지 않았어요. 자가 진단만으로 진행해요.</p>` : ''}
          <p class="small muted" style="margin:${d.quiz.deep ? '0' : '-14px'} 0 16px">답한 문항 <b id="qCount" class="num"></b><span id="dqCount"></span></p>
          <div class="stack">${P.quizBody(d.quiz.questions, 'draft.answers', null, P.deepOn(d) ? { quiz: d.quiz.deep, mcq: 'draft.deepMcq', essay: 'draft.deepEssay' } : null)}</div>${staleNote('diag')}`
          : `<div class="agents">${P.agentRow({ st: 'run', name: QUIZ_AGENT, sub: P.runSub('default', '목표와 세부 사항을 바탕으로 문항을 만들고 있어요') })}</div>`,
        foot: `<button class="btn line" data-go="new-details-check">${icon('left')}이전</button>${P.next('new-result', '다음: 점검 결과', 'quizDone')}`
      });
    },
    after: () => { ensureQuiz(); }
  };

  /* 4. 점검 결과(API-25): 진단 에이전트가 정리한 로드맵 미리보기 + 학습 선호 (보기 전용 · 고치려면 '수정').
     수준 진단도 가데이터로 대신하지 않는다. 실패는 서버(diagFail)에 남고 '다시 시도하기'를 눌러야만 다시 진단한다 */
  let diagAsk = '';
  async function ensureDiag(retry) {
    const d = S().draft, key = P.diagKey(d);
    if ((d.diag && d.diag.key === key) || (d.diagRun && d.diagRun.key === key)) return P.watchDraft();
    if (diagAsk === key || (!retry && d.diagFail && d.diagFail.key === key)) return;
    diagAsk = key;
    const r = await draftCall('점검 결과를 정리하지 못했어요', id => API.diagnosis(id));
    diagAsk = '';
    if (!r) return;
    await P.pullDraft();
    if (S().route === 'new-result') GP.render(false);
  }
  GP.act['diag-retry'] = () => { S().draft.diagFail = null; GP.render(false); ensureDiag(true); };
  const DIAG_AGENT = '진단 에이전트 · 수준 진단·로드맵 미리보기';
  const shownRes = (ids, start) => ids.filter(id => D.res[id] && D.res[id].kind !== '자격' && (D.res[id].stage || 1) >= start);
  const stageLabel = n => `${n}단계 ‘${(D.stages.find(s => s.n === +n) || {}).name || ''}’부터`;
  P.preview = function () {
    const d = S().draft, a = d.diag, start = P.startOf(d);
    /* 수정 화면에서 진단 에이전트 제안과 다르게 고친 항목은 '직접 고침'으로 표시 */
    const dt = (k, l) => `<dt>${l}${P.edited(d, k) ? '<small class="ed">직접 고침</small>' : ''}</dt>`;
    const res = shownRes(P.dv(d, 'resourceIds'), start), known = P.dv(d, 'known');
    return `<div class="card acc preview">
      <p class="eyebrow">${icon('spark')}진단 에이전트가 정리한 로드맵 미리보기</p>
      <dl class="kv">
        ${dt('start', '시작 지점')}<dd><b>${stageLabel(start)}</b><span class="small muted d-sub">${P.edited(d, 'start') ? `진단 에이전트 제안은 ${a.startStage}단계예요 · ${esc(a.startReason)}` : `진단 에이전트 제안 · ${esc(a.startReason)}`}</span></dd>
        ${dt('competencies', '익히게 될 역량')}<dd><div class="chips">${P.dv(d, 'competencies').map(c => `<span class="chip">${esc(c)}</span>`).join('')}</div></dd>
        ${dt('resourceIds', '듣게 될 강좌·자료')}<dd><ul class="plain-list res-list">${res.map(id => { const r = D.res[id]; return `<li>${P.thumb(r, 'xs')}<span><b>${esc(r.title)}</b> <span class="small muted">${r.kind} · ${esc(r.provider)}${r.real ? '' : ' · 가상'}</span></span></li>`; }).join('') || '<li class="muted">로드맵 계획 에이전트가 등록 자료에서 고를 예정이에요</li>'}</ul></dd>
        ${dt('outcome', '만들 결과물')}<dd>${esc(P.dv(d, 'outcome'))}</dd>
        ${known.length || P.edited(d, 'known') ? `${dt('known', '이미 할 수 있는 것')}<dd class="small muted">${esc(known.slice(0, 6).join(', ') || '없음')}${known.length ? ' — 다시 배우지 않도록 줄여요' : ''}</dd>` : ''}
      </dl></div>`;
  };
  scr['new-result'] = {
    nav: 'new', newStep: true, title: '점검 결과', width: 'wide', guard: () => blockedTo('result'),
    render() {
      const d = S().draft, key = P.diagKey(d), ready = d.diag && d.diag.key === key, err = !ready && !d.diagRun && d.diagFail && d.diagFail.key === key ? AI.cause(d.diagFail.cause) : null;
      if (err) return GP.stepper('result') + P.failPage({
        title: '점검 결과를 정리하는 중 문제가 발생했어요',
        desc: '진단 에이전트가 사전 점검 응답을 정리하지 못했어요. 입력한 목표·세부 사항과 사전 점검 응답은 그대로 남아 있어요.',
        cause: esc(P.errText(err)),
        body: `<div class="agents">${P.agentRow({ st: 'fail', name: DIAG_AGENT, sub: AI.live() ? via('default') : '', tag: '오류 발생', tagCls: 'fail' })}</div>`,
        ops: P.opsBox([['', err]]),
        foot: `<button class="btn line" data-go="new-quiz">${icon('left')}사전 점검 응답 고치기</button><button class="btn pri" data-act="diag-retry">${icon('retry')}다시 시도하기</button>`
      });
      return GP.stepper('result') + P.page({
        title: '이런 로드맵이 만들어질 예정이에요',
        lead: '사전 점검 응답과 세부 사항을 진단 에이전트가 정리했어요. 바꿀 내용이 있으면 아래 ‘수정’을 눌러 주세요. 수준 점수는 보여주지 않고 사후 점검 비교용으로만 저장해요.',
        body: ready ? `${P.preview()}${P.deepOn(d) && d.diag.deep ? P.deepReveal(d.quiz.questions, d.quiz.deep, d.deepMcq, d.deepEssay, d.diag.deep.grade, d.diag.deep.judge, '심화 질문 정답·모범 답안 보기') : ''}${P.note('목표·기획서나 사전 점검 응답을 고치려면 위 단계를 눌러 이동하세요. ‘로드맵 생성’을 누를 때 지금 내용이 로드맵 계획 에이전트에게 전달돼요.')}`
          : `<div class="agents">${P.agentRow({ st: 'run', name: DIAG_AGENT, sub: P.runSub('default', '사전 점검 응답과 세부 사항을 정리하고 있어요') })}</div>`,
        foot: `<button class="btn line" data-go="new-quiz">${icon('left')}이전</button><button class="btn line" data-act="result-edit" ${ready ? '' : 'disabled'}>${icon('edit')}수정</button><button class="btn pri" data-act="gen-start" ${ready ? '' : 'disabled'}>로드맵 생성</button>`
      });
    },
    after: () => { ensureDiag(); }
  };
  /* 로드맵 생성(API-27): 서버가 전달 내용을 정리하고 세 안을 병렬로 쓰기 시작한다. 같은 내용으로 세 안을 모두 받은 적이 있으면 그 결과를 쓴다 */
  GP.act['gen-start'] = async () => {
    /* 바꾼 앞 단계가 남아 있으면(홈에서 이어서 들어온 경우 등) 먼저 확인 */
    const st = P.stale(); if (st) { GP.sheet(staleText(st), { title: '바꾼 내용으로 계속할까요?', foot: staleBtns(st, 'new-result') }); return; }
    const r = await draftCall('로드맵 생성을 시작하지 못했어요', id => API.optionsStart(id));
    if (!r) return;
    GP.go(S().draft.gen ? 'new-options' : 'new-gen');
  };

  /* 4-1. 점검 결과 수정: 점검 결과 화면에 보이는 내용을 한곳에서 고친다. 저장해야 반영되고(API-26), 취소하면 그대로 */
  const sameSet = (x, y) => JSON.stringify((x || []).slice().sort()) === JSON.stringify((y || []).slice().sort());
  const editFrom = d => ({ start: P.startOf(d), competencies: P.dv(d, 'competencies').slice(), resourceIds: P.dv(d, 'resourceIds').slice(), outcome: P.dv(d, 'outcome'), known: P.dv(d, 'known').slice(), prefs: clone(d.prefs) });
  /* 학습 선호(세부 사항)는 모두 선택 사항이라 빈 칸 검사는 로드맵 내용에만 */
  P.editMissing = e => ({ competencies: !e.competencies.length, outcome: !String(e.outcome || '').trim() });
  const missTip = (k, t) => `<span class="miss" data-miss="${k}" ${P.editMissing(S().draft.edit)[k] ? '' : 'hidden'}>${icon('info')}${t}</span>`;
  const radios = (path, opts, cur, rer) => `<div class="chips">${opts.map(([v, l]) => `<label class="chip"><input type="radio" name="${path}" value="${esc(v)}" data-bind="${path}" ${rer ? 'data-rerender' : ''} ${String(cur) === String(v) ? 'checked' : ''}>${esc(l)}</label>`).join('')}</div>`;
  const listEdit = (k, ph) => {
    const arr = S().draft.edit[k];
    return `<div class="chips">${arr.map((t, i) => `<span class="chip on">${esc(t)}<button type="button" class="link quiet" data-act="edit-del" data-arg="${k}:${i}" aria-label="${esc(t)} 빼기">${icon('x')}</button></span>`).join('') || '<span class="muted small">없음</span>'}</div>
      <div class="addrow"><input class="input" id="add-${k}" data-add="${k}" placeholder="${ph}" maxlength="60" autocomplete="off"><button type="button" class="btn line sm" data-act="edit-add" data-arg="${k}">${icon('plus')}추가</button></div>`;
  };
  /* 진단 에이전트 제안과 다르게 고친 항목에만 '제안대로 되돌리기'를 보여 준다 */
  const sugBack = k => {
    const d = S().draft, e = d.edit, a = d.diag;
    const same = k === 'start' ? +e.start === a.startStage : k === 'resourceIds' ? sameSet(e.resourceIds, a.resourceIds) : JSON.stringify(e[k]) === JSON.stringify(a[k]);
    return same ? '' : `<button type="button" class="link quiet back-sug" data-act="edit-reset" data-arg="${k}">${icon('history')}제안대로 되돌리기</button>`;
  };
  const ef = (label, body, sub) => `<div class="ef"><div class="ef-l">${label}${sub ? `<small>${sub}</small>` : ''}</div><div class="ef-c">${body}</div></div>`;
  P.editBody = function () {
    const d = S().draft, e = d.edit, a = d.diag, start = +e.start;
    return `<div class="card"><h2 class="st">로드맵 내용 <span class="small muted">진단 에이전트가 정리</span></h2><div class="efs">
        ${ef('시작 지점', `${radios('draft.edit.start', D.stages.map(s => [s.n, `${s.n}단계 ${s.name}`]), start, true)}<p class="small muted ef-n">진단 에이전트 제안: ${stageLabel(a.startStage)} · ${esc(a.startReason)} ${sugBack('start')}</p>`)}
        ${ef('익히게 될 역량', `${listEdit('competencies', '예: 답변 근거 표시하기')}${missTip('competencies', '역량을 하나 이상 넣어 주세요')}${sugBack('competencies')}`)}
        ${ef('듣게 될 강좌·자료', `${P.resPicker('draft.edit.resourceIds', e.resourceIds, { stage: start })}<p class="small muted ef-n">팀 DB 등록 자료에서 검색해 골라요. 시작 지점 이후 단계만 보여요. 자격증은 아래 학습 선호에서 정해요. ${sugBack('resourceIds')}</p>`)}
        ${ef('만들 결과물', `<textarea class="textarea sm" data-bind="draft.edit.outcome" maxlength="200" aria-label="만들 결과물">${esc(e.outcome)}</textarea>${missTip('outcome', '만들 결과물을 적어 주세요')}${sugBack('outcome')}`)}
        ${ef('이미 할 수 있는 것', `${listEdit('known', '예: Python 기초')}<p class="small muted ef-n">여기 있는 내용은 로드맵에서 다시 배우지 않도록 줄여요. ${sugBack('known')}</p>`)}
      </div></div>
      <div class="card" style="margin-top:12px"><h2 class="st">학습 선호 <span class="small muted">세부 사항에서 입력 · 비워 두면 알아서</span></h2>${P.detailsForm('draft.edit.prefs')}</div>`;
  };
  scr['new-result-edit'] = {
    nav: 'new', newStep: true, title: '점검 결과 수정', width: 'wide',
    guard: () => { const d = S().draft; return blockedTo('result') || (d.diag && d.diag.key === P.diagKey(d) ? null : 'new-result'); },
    render() {
      const d = S().draft; if (!d.edit) { d.edit = editFrom(d); GP.save(); }
      return GP.stepper('result') + P.page({
        eyebrow: '점검 결과 수정', title: '바꿀 내용을 고친 뒤 저장해 주세요',
        lead: '점검 결과 화면에 보이는 내용을 여기서 한꺼번에 고쳐요. 저장해야 반영되고, 취소하면 그대로예요. 목표·기획서나 사전 점검 응답은 위 단계를 눌러 고치세요.',
        body: P.editBody(),
        foot: `<button class="btn line" data-act="edit-cancel">취소</button><button class="btn pri" data-act="edit-save" data-need="editOk">저장</button>`
      });
    },
    after(root) {
      root.querySelectorAll('[data-add]').forEach(i => i.addEventListener('keydown', ev => { if (ev.key === 'Enter' && !ev.isComposing) { ev.preventDefault(); GP.act['edit-add'](i.dataset.add); } }));
    }
  };
  GP.act['result-edit'] = () => { const d = S().draft; if (!d.diag) return; d.edit = editFrom(d); GP.save(); GP.go('new-result-edit'); };
  GP.act['edit-add'] = k => {
    const e = S().draft.edit, inp = document.getElementById('add-' + k); if (!e || !inp) return;
    const v = inp.value.trim().replace(/\s+/g, ' '); if (!v) { inp.focus(); return; }
    if (!e[k].includes(v)) e[k].push(v);
    GP.save(); GP.render(false); const n = document.getElementById('add-' + k); if (n) n.focus();
  };
  GP.act['edit-del'] = arg => { const [k, i] = arg.split(':'); S().draft.edit[k].splice(+i, 1); GP.save(); GP.render(false); };
  GP.act['edit-reset'] = k => { const d = S().draft, e = d.edit, a = d.diag; if (k === 'start') e.start = a.startStage; else e[k] = clone(a[k]); GP.save(); GP.render(false); };
  GP.act['edit-cancel'] = () => { S().draft.edit = null; GP.save(); GP.go('new-result'); };
  /* 바뀌었는지는 서버와 같은 규칙(진단 제안과 다른 항목만 fix)으로 미리 본다 — 3안을 버리기 전에 묻기 위해 */
  const editNext = d => {
    const e = d.edit, a = d.diag, start = +e.start;
    const val = { competencies: e.competencies, resourceIds: e.resourceIds, outcome: String(e.outcome).trim(), known: e.known }, fix = {};
    P.FIX.forEach(([k]) => { if (!(k === 'resourceIds' ? sameSet(val[k], a[k]) : JSON.stringify(val[k]) === JSON.stringify(a[k]))) fix[k] = val[k]; });
    return { startStage: start === a.startStage ? null : start, fix: Object.keys(fix).length ? fix : null, prefs: clone(e.prefs) };
  };
  const editChanged = (d, n) => !sameJ([d.startStage || null, d.fix || null, d.prefs], [n.startStage, n.fix, n.prefs]);
  async function editSave() {
    const e = S().draft.edit;
    const r = await draftCall('수정한 내용을 저장하지 못했어요', id => API.overrides(id, { start: +e.start, competencies: e.competencies, resourceIds: e.resourceIds, outcome: e.outcome, known: e.known, prefs: e.prefs }));
    if (!r) return;
    GP.go('new-result'); GP.toast(r.changed ? '수정한 내용을 저장했어요' : '바뀐 내용이 없어요');
  }
  GP.act['edit-save'] = () => {
    const d = S().draft; if (!d.edit || !GP.valid.editOk()) return;
    /* 이미 만든 3안이 있으면, 저장하면 버리고 다시 만든다는 것을 먼저 확인 (10/14) */
    if ((d.handoff || d.gen) && editChanged(d, editNext(d))) {
      GP.sheet(`<p style="margin:0 0 8px">저장하면 바꾼 내용으로 아래를 새로 만들어요.</p><ul class="plain-list"><li>로드맵 3안${S().draftPlan ? '과 고른 안' : ''}</li></ul><p class="small muted" style="margin-top:10px">점검 결과와 사전 점검 응답은 그대로예요.</p>`,
        { title: '바꾼 내용으로 저장할까요?', foot: '<button class="btn line" data-act="sheet-close">계속 고치기</button><button class="btn pri" data-act="edit-save-ok">저장</button>' });
      return;
    }
    editSave();
  };
  GP.act['edit-save-ok'] = () => { GP.closeSheet(); if (S().draft.edit) editSave(); };

  /* 5. 3안 생성 (로드맵 계획 에이전트 · 관점별 병렬 · 서버 작업 셋)
     하위 에이전트마다 따로 실행하고, API 오류를 가데이터로 대신하지 않는다. 실패한 줄은 빨간 X로 바뀌고
     그 안만 '다시 시도'(API-29)하거나, '로드맵 확인하기'(API-30)로 작성된 안만 가지고 다음 단계로 넘어갈 수 있다.
     진행 상태는 서버 작성 문서(genRun)에 있어 새로 고쳐도 이어서 보이고, 지원 조건은 세 안이 정해지면 서버가 규정 에이전트로 확인한다 */
  P.handoffView = (h, open) => `<details class="card flat handoff" id="hoView" ${open ? 'open' : ''}><summary>${icon('right')}진단 에이전트가 넘긴 내용 보기</summary><dl class="kv">
    <dt>목표</dt><dd>${esc(h.goal)}${h.projectFile ? `<br><span class="small muted">기획서: ${esc(h.projectFile)}</span>` : ''}</dd>
    <dt>시작 단계</dt><dd>${h.startStage}단계 · ${esc(h.startReason)}</dd>
    <dt>익힐 역량</dt><dd>${esc(h.focus.join(', '))}</dd>
    <dt>이미 할 수 있는 것</dt><dd>${esc(h.known.join(', ') || '없음')}</dd>
    <dt>학습 선호</dt><dd>방식 ${esc(h.prefs.format)} · 주당 ${h.prefs.weeklyHours ? `${h.prefs.weeklyHours}시간` : '알아서'} · 기간 ${h.prefs.deadlineWeeks ? h.prefs.deadlineWeeks + '주' : '없음'} · 예산 ${h.prefs.budgetLimit != null ? won(h.prefs.budgetLimit) : h.prefs.budgetAuto ? '알아서' : '없음'} · 자격증 ${esc(h.prefs.certPlan)}</dd>
    ${h.projectSummary ? `<dt>기획서 요약</dt><dd class="pre">${esc(h.projectSummary)}</dd>` : ''}
    <dt>메모</dt><dd>${esc(h.userNotes.concat(h.agentNotes).join(' / ') || '없음')}</dd>
    <dt>자료 후보</dt><dd>${esc(h.resourceHints.map(id => D.res[id] ? D.res[id].title : id).join(', ') || '없음')}</dd>
    ${h.userEdited && h.userEdited.length ? `<dt>직접 고친 항목</dt><dd>${esc(h.userEdited.join(', '))}</dd>` : ''}</dl></details>`;
  let hoOpen = false;
  document.addEventListener('toggle', e => { if (e.target.id === 'hoView') hoOpen = e.target.open; }, true);
  const curGen = d => (d.genRun && d.handoff && d.genRun.key === d.handoff.key ? d.genRun : null);
  const curOut = d => (d.gen && d.handoff && d.gen.key === d.handoff.key ? d.gen : null);
  const genState = r => {
    const ps = D.optionOrder.map(id => r.rows[id]);
    return { running: ps.some(x => x.st === 'run'), ok: ps.filter(x => x.st === 'ok').length, fail: ps.filter(x => x.st === 'fail').length };
  };
  GP.act['gen-retry'] = async id => {
    const r = curGen(S().draft); if (!r || !r.rows[id] || r.rows[id].st !== 'fail') return;
    r.rows[id].st = 'run'; GP.render(false);
    await draftCall(`${id} 안을 다시 쓰지 못했어요`, did => API.optionRetry(did, id));
    GP.render(false);
  };
  GP.act['gen-partial'] = async () => {
    const r = curGen(S().draft); if (!r) return;
    const g = genState(r); if (g.running || !g.ok) return;
    if (await draftCall('작성된 안으로 넘어가지 못했어요', id => API.acceptPartial(id))) GP.go('new-options');
  };
  /* 서버를 다시 켜서 끊긴 지원 조건 확인을 이어서 시작한다(실패한 확인은 건드리지 않음 · 화면에 들어올 때 한 번) */
  const supKicked = new Set();
  function kickSupport() {
    const d = S().draft, g = curOut(d); if (!g || !draftId()) return;
    const pid = D.optionOrder.find(x => g.options[x] && !g.options[x].support && !g.options[x].supportFail);
    const k = `${draftId()}|${g.key}|${pid}|${JSON.stringify(g.cur || {})}`;
    if (!pid || supKicked.has(k)) return;
    supKicked.add(k);
    setTimeout(() => { API.supportRetry(draftId(), pid).then(r => { GP.takeDraft(r, true); P.watchDraft(); }).catch(() => {}); }, 4000);
  }

  /* ── 버전: 다시 만든 안은 버전으로 쌓고 ‹ › 로 넘겨 본다. options[관점]은 지금 보고 있는 버전(서버 저장 · genCur) ── */
  const syncGen = g => { if (g && g.hist) Object.keys(g.hist).forEach(pid => { if (g.hist[pid][(g.cur || {})[pid] || 0]) g.options[pid] = g.hist[pid][(g.cur || {})[pid] || 0]; }); };
  const regenBusy = pid => { const g = S().draft.gen; return !!(g && g.regenRun && g.regenRun[pid]); };
  const regenErr = pid => { const g = S().draft.gen; return g && g.regenErr && g.regenErr[pid] ? AI.cause(g.regenErr[pid]) : null; };

  /* ── 지원 조건 (10/14): 3안이 정해진 뒤 서버가 규정 에이전트를 한 번 불러 안별로 확인. 다시 만든 안은 그 안만 확인 ──
     근거는 내 직원 구분의 등록 규정 조항만(팀 DB 규정 · 일반직 규정 묶음 등). 실패하면 '다시 확인'을 눌러야만 다시 묻는다 */
  GP.act['sup-retry'] = async pid => {
    const g = S().draft.gen; if (!g) return;
    syncGen(g);
    D.optionOrder.filter(id => g.options[id] && (pid === 'all' || id === pid)).forEach(id => { delete g.options[id].supportFail; });
    GP.render(false);
    await draftCall('지원 조건을 다시 확인하지 못했어요', id => API.supportRetry(id, pid === 'all' ? null : pid), { soft: true });
    GP.render(false);
  };
  const SUP_LV = { ok: ['근거 확인', 'acc'], unclear: ['일부만 확인', 'warn'], missing: ['관련 자료 미확보', 'warn'], scope: ['적용 대상 아님', 'warn'] };
  /* 확정 뒤 수정안의 지원 조건 (설계서 v1.7 SCR-RM-06 · 10/20): 자료·자격·기간·비용이 바뀐 수정안만 서버가 규정 에이전트로 다시 확인한다.
     확인 전에는 '확인 필요'로 보여 주고, 실패하면 '다시 확인'을 눌러야만 다시 묻는다. 확정하면 그 버전에 결과를 남긴다 */
  GP.act['rev-sup-retry'] = async () => {
    const R = P.R(); if (!R || !R.pending) return;
    delete R.pending.supFail; GP.render(false);
    try { await API.reviseSupportRetry(R.id); } catch (err) { GP.fail(err, '지원 조건을 다시 확인하지 못했어요'); }
    await P.pullPlan(R.id); GP.render(false);
  };
  P.revSupView = function (pd) {
    const o = pd.to.def, head = `<div class="card flat rv-sup"><dl class="kv"><dt>지원 조건 · v${pd.from.version + 1}</dt><dd>`;
    let cell;
    if (o.support) cell = `${P.supCell(o)}${pd.supSame ? '<span class="small muted sup-l">자료·자격·기간·비용이 그대로라 이전 버전의 확인 결과를 그대로 써요.</span>' : '<span class="small muted sup-l">자료·자격·기간·비용이 바뀌어 규정 에이전트가 이 버전을 다시 확인했어요.</span>'}`;
    else if (pd.supFail) { const c = AI.cause(pd.supFail.cause); cell = `<span class="tag warn">확인 필요</span> <span class="small muted">${esc(c.user || AI.userText(c.kind))}. 확인하지 못한 동안은 ‘확인 필요’로 둬요.</span> <button class="link" data-act="rev-sup-retry">${icon('retry')}다시 확인</button>${P.opsBox([['', c]], 'sm')}`; }
    else cell = `<span class="tag warn">확인 필요</span> <span class="small muted">자료·자격·기간·비용이 바뀌어 규정 에이전트가 이 버전의 지원 조건을 다시 확인하고 있어요.</span>`;
    return `${head}${cell}</dd></dl></div>`;
  };
  /* 안 하나의 지원 조건: 수준 태그 · 요약 · 근거 조항 · 미등록 규정 (근거 조항이 없으면 '확인 필요'로만 보여 준다) */
  P.supCell = function (o) {
    if (!o) return '';
    if (o.supportFail) { const c = AI.cause(o.supportFail.cause); return `<span class="tag fail">확인 실패</span> <span class="small muted">${esc(c.user || AI.userText(c.kind))}. 지원 조건은 ‘확인 필요’로 둬요.</span> <button class="link" data-act="sup-retry" data-arg="${o.id}">${icon('retry')}다시 확인</button>`; }
    if (!o.support) return `<span class="tag">확인 중</span> <span class="small muted">규정 에이전트가 확인하고 있어요</span>`;
    const s = o.support, [t, c] = SUP_LV[s.level] || SUP_LV.missing;
    const basis = (s.basis || []).map(id => AI.article(id)).filter(Boolean).map(AI.artName).join(', ');
    return `<span class="tag ${c}">${t}</span> <span class="small">${esc(s.summary)}</span>${basis ? `<span class="small muted sup-l">근거: ${esc(basis)}</span>` : ''}${(s.missing || []).length ? `<span class="small muted sup-l">등록되지 않은 기준: ${s.missing.map(m => esc(AI.missLabel(m))).join(', ')}</span>` : ''}`;
  };
  const supNote = () => (!AI.regApplies() ? P.note(`등록된 규정은 ${esc(Object.keys(AI.REG_SETS).join('·'))} 대상이라 ${esc((GP.me() || {}).empGroup || '')} 직원의 지원 조건은 확인하지 않았어요. ${esc((GP.me() || {}).empGroup || '')} 대상 규정이 등록되면 규정 에이전트가 확인해요. 지원금은 예상 비용에서 빼지 않았어요.`)
    : P.note(`지원 조건은 규정 에이전트가 등록된 ${esc(AI.regSet().label)} 조항만 근거로 확인해요. 조항에 없는 지원 여부·금액은 짐작하지 않고 ‘확인 필요’로 둬요. 지원금은 예상 비용에서 빼지 않았어요. <button class="link" data-act="reg-ask" data-arg="교육비 지원을 받을 수 있나요?">${icon('chat')}사내 생활 도우미에게 묻기</button>`));

  const rowName = id => `${id} ${esc(D.perspectives[id].name)}`;
  function genRow(r, id) {
    const row = r ? r.rows[id] : { st: 'run', tries: 1 }, name = rowName(id);
    if (row.st === 'run') return P.agentRow({ st: 'run', name, sub: P.runSub('roadmap', row.tries > 1 ? '다시 시도하는 중이에요' : '진단 에이전트가 넘긴 내용으로 작성 중이에요') });
    if (row.st === 'ok') return P.agentRow({ st: 'ok', name, sub: esc(row.out.tagline), tag: '작성 완료', tagCls: 'acc' });
    const c = AI.cause(row.err || {});
    return P.agentRow({ st: 'fail', name, sub: AI.live() ? via('roadmap') : '', failLabel: '생성 실패', tag: '오류 발생', tagCls: 'fail', retry: ['gen-retry', id], detail: esc(c.user || AI.userText(c.kind)) });
  }
  /* 규정 에이전트 줄: 3안이 정해지기 전에는 기다림, 확인 중, 안별 결과, 실패(다시 시도는 눌러야만) */
  function supRow(d) {
    const name = '규정 에이전트 · 안별 지원 조건 확인', g = curOut(d);
    if (!g) return P.agentRow({ st: 'wait', name, sub: '세 안이 정해지면 안마다 교육비 지원·근무시간 학습 인정을 확인해요' });
    syncGen(g);
    const os = D.optionOrder.map(pid => g.options[pid]).filter(Boolean), fails = os.filter(o => o.supportFail);
    if (fails.length) { const c = AI.cause(fails[0].supportFail.cause); return P.agentRow({ st: 'fail', name, sub: AI.live() ? via('default') : '', failLabel: '확인 실패', tag: '오류 발생', tagCls: 'fail', retry: ['sup-retry', 'all'], detail: `${esc(c.user || AI.userText(c.kind))} · 지원 조건은 ‘확인 필요’로 두고 넘어갈 수 있어요` }); }
    if (os.some(o => !o.support)) return P.agentRow({ st: 'run', name, sub: P.runSub('default', '안마다 유료 자료·학습 형태로 등록된 규정을 확인하고 있어요') });
    if (os.every(o => o.support.level === 'scope')) return P.agentRow({ st: 'ok', warn: true, name, sub: `등록된 규정은 ${esc(Object.keys(AI.REG_SETS).join('·'))} 대상이라 ${esc((GP.me() || {}).empGroup || '')} 직원은 확인하지 않았어요`, tag: '적용 대상 아님', tagCls: 'warn' });
    const allOk = os.every(o => o.support.level === 'ok');
    return P.agentRow({ st: 'ok', warn: !allOk, name, sub: esc(os.map(o => `${o.id} ${(SUP_LV[o.support.level] || SUP_LV.missing)[0]}`).join(' · ')), tag: allOk ? '근거 확인' : '확인 필요', tagCls: allOk ? 'acc' : 'warn' });
  }
  /* 여러 안이 실패했을 때 할 일은 겹치지 않게 한 번씩만 */
  const todoOf = errs => [...new Set(errs.flatMap(e => AI.userTodo(e.kind)))].join(' ');
  scr['new-gen'] = {
    nav: 'new', title: '로드맵 3안 작성', width: 'wide', guard: () => (S().draft.handoff ? null : blockedTo('options') || 'new-result'),
    render() {
      const d = S().draft, h = d.handoff, r = curGen(d);
      const g = r ? genState(r) : { running: true, ok: 0, fail: 0 };
      const rows = `<div class="agents">${D.optionOrder.map(id => genRow(r, id)).join('')}${supRow(d)}</div>`;
      if (g.fail) {
        const failed = D.optionOrder.filter(id => r.rows[id].st === 'fail'), names = failed.map(id => `${id} ${D.perspectives[id].name}`).join(', '), errs = failed.map(id => AI.cause(r.rows[id].err || {}));
        return GP.stepper('options') + P.failPage({
          title: '로드맵 3안 작성 중 문제가 발생했어요',
          desc: g.ok ? `${esc(names)}을 쓰지 못했어요. 작성된 안만 가지고 다음 단계로 넘어가거나, 실패한 안만 다시 시도할 수 있어요.` : '관점별 하위 에이전트가 로드맵 안을 쓰지 못했어요. 실패한 안을 다시 시도하거나, 조건을 고쳐 다시 만들어 주세요.',
          cause: `${failed.map((id, i) => `${id} ${esc(D.perspectives[id].name)} — ${esc(errs[i].user || AI.userText(errs[i].kind))}`).join(' · ')}. ${esc(todoOf(errs))}`,
          body: `${P.handoffView(h, hoOpen)}${rows}`,
          ops: P.opsBox(failed.map((id, i) => [rowName(id), errs[i]])),
          foot: `<button class="btn line" data-act="result-edit">${icon('left')}조건 수정하고 다시 만들기</button><button class="btn pri" data-act="gen-partial" ${g.running || !g.ok ? 'disabled' : ''}>${icon('map')}로드맵 확인하기</button>`,
          hint: g.running ? '작성 중인 안이 끝나면 ‘로드맵 확인하기’를 누를 수 있어요.' : !g.ok ? '작성된 안이 없어요. 실패한 안을 다시 시도하거나 조건을 고쳐 주세요.' : `‘로드맵 확인하기’를 누르면 작성된 ${g.ok}개 안만 비교해요. 실패한 안은 저장하지 않아요.`
        });
      }
      const done = !!r && !g.running && g.ok === D.optionOrder.length && !!curOut(d);
      return GP.stepper('options') + P.page({
        title: done ? '로드맵 3안을 다 썼어요' : '로드맵 계획 에이전트가 3안을 쓰고 있어요',
        lead: done ? '‘3안 보러 가기’를 눌러 비교해 보세요. 지원 조건 확인이 끝나지 않았어도 넘어갈 수 있어요(비교표에서 이어서 보여 줘요).' : AI.mode() === 'ollama' ? '관점별 하위 에이전트 셋이 진단 에이전트가 넘긴 같은 내용으로 동시에 요청해요. AI 서버 사정에 따라 차례대로 처리돼 시간이 더 걸릴 수 있어요. 화면을 떠나도 서버가 이어서 써요.' : '관점별 하위 에이전트 셋이 진단 에이전트가 넘긴 같은 내용으로 동시에 작성해요. 화면을 떠나도 서버가 이어서 써요.',
        body: `${P.handoffView(h, hoOpen)}${rows}`,
        foot: `<button class="btn line" data-go="new-result">${icon('left')}이전</button><button class="btn pri" data-go="new-options" ${done ? '' : 'disabled'}>3안 보러 가기</button>`
      });
    },
    after() {
      const d = S().draft;
      if (!curGen(d) && curOut(d)) { GP.go('new-options'); return; }
      if (!curGen(d) && !curOut(d)) { GP.act['gen-start'](); return; }
      kickSupport(); P.watchDraft();
    }
  };

  /* 5. 3안 비교표 (10/14): 열 순서는 A1·A2·A3 고정. 마음에 들지 않는 안은 요청을 적어 그 안만 다시 만들고(API-32 · 버전으로 쌓임), ‹ › 로 버전을 넘겨 본다 */
  scr['new-options'] = {
    nav: 'new', newStep: true, title: '로드맵 3안', width: 'xwide',
    guard: () => { const d = S().draft; if (d.gen) return null; return d.handoff ? 'new-gen' : blockedTo('options') || 'new-result'; },
    render() {
      const d = S().draft, g = d.gen; syncGen(g);
      const ps = P.opts(), cur = d.chosen;
      const col = p => `data-col="${p.opt}"${regenBusy(p.opt) ? ' class="busy"' : ''}`;
      const row = (k, f) => `<tr><td class="k">${k}</td>${ps.map(p => `<td ${col(p)}>${f(p, p.def)}</td>`).join('')}</tr>`;
      const src = o => (o.source && o.source !== 'mock' ? `<span class="tag acc">${AI.PROV[o.source] || 'API'} 작성</span>` : '<span class="tag">가데이터</span>');
      const off = ps.some(p => p.def.offDomain), missing = g.missing || [];
      const ver = p => {
        const list = (g.hist || {})[p.opt], i = (g.cur || {})[p.opt] || 0, o = p.def, busy = regenBusy(p.opt);
        const nav = list && list.length > 1 ? `<span class="vnav"><button type="button" data-act="ver" data-arg="${p.opt}:-1" ${i === 0 || busy ? 'disabled' : ''} aria-label="이전 버전">${icon('left')}</button><b class="num">버전 ${i + 1}/${list.length}</b><button type="button" data-act="ver" data-arg="${p.opt}:1" ${i === list.length - 1 || busy ? 'disabled' : ''} aria-label="다음 버전">${icon('right')}</button></span>` : '';
        const info = i > 0 ? `${o.revSummary ? `<span class="small rev">바꾼 점: ${esc(o.revSummary)}</span>` : ''}${o.revRequest ? `<span class="small muted rev">요청: ${esc(o.revRequest)}</span>` : ''}${(o.revNotes || []).length ? `<span class="small muted rev">반영하지 못한 것: ${esc(o.revNotes.join(' '))}</span>` : ''}` : '';
        return nav + info;
      };
      const head = p => { const busy = regenBusy(p.opt), err = regenErr(p.opt); return `<th ${col(p)}><label><input type="radio" name="pick" value="${p.opt}" data-bind="draft.chosen" ${cur === p.opt ? 'checked' : ''}><span><b>${p.opt} ${esc(p.name)}</b><small>${esc(p.tagline)}</small></span></label>
              ${ver(p)}<button class="regen" data-act="regen-one" data-arg="${p.opt}" ${busy ? 'disabled' : ''}>${busy ? '<span class="sp"></span>다시 쓰는 중…' : icon('history') + '이 안만 다시 만들기'}</button>${err && !busy ? `<span class="small rev fail-t">${icon('x')}<span>다시 만들지 못했어요 · ${esc(err.user)}. 이전 안을 그대로 뒀어요. 다시 해 보려면 ‘이 안만 다시 만들기’를 눌러 주세요.</span></span>${P.opsBox([['', err]], 'sm')}` : ''}</th>`; };
      return GP.stepper('options') + P.page({
        title: ps.length === 3 ? '로드맵 3안을 비교하고 골라 주세요' : ps.length === 1 ? '작성된 로드맵을 확인해 주세요' : `작성된 로드맵 ${ps.length}안을 비교하고 골라 주세요`,
        lead: '같은 목표와 학습 여건으로 방법만 달라요. 마음에 들지 않는 안은 바라는 점을 적어 그 안만 다시 만들 수 있고, 다시 만든 안은 버전으로 넘겨 볼 수 있어요.',
        body: `<div class="tblwrap"><table class="cmp"><thead><tr><th></th>${ps.map(head).join('')}</tr></thead><tbody>
            ${row('기간 · 주당', p => `<span class="numv">${p.weeks}주</span> · 주 ${p.hours}시간${d.handoff.prefs.hoursAuto ? '<small class="muted"> (에이전트가 정함)</small>' : ''}`)}
            ${row('예상 비용', p => `<span class="numv">${won(p.cost)}${p.costUnknown ? ' + 확인 필요' : ''}</span>`)}
            ${row('활동', p => `<details class="more" open><summary>${icon('right')}${p.acts.length}개 보기</summary><ul class="cmp-acts">${p.acts.map(a => `<li>${P.actThumb(a, 'xs')}<span>${esc(a.title)} <span class="muted small">${a.task ? '직접 수행' : ''} ${hrs(a.hours)}</span></span></li>`).join('')}</ul></details>`)}
            ${row('지원 조건', (p, x) => P.supCell(x))}
            ${row('단계', p => D.stages.filter(s => s.n >= p.start && P.stageActs(p, s.n).length).map(s => s.name).join(' › '))}
            ${row('추천 이유', (p, x) => esc(x.reason))}
            ${row('좋은 점', (p, x) => `<ul>${x.pros.map(t => `<li>${esc(t)}</li>`).join('')}</ul>`)}
            ${row('아쉬운 점', (p, x) => `<ul>${x.cons.map(t => `<li>${esc(t)}</li>`).join('')}</ul>`)}
            ${row('작성', (p, x) => src(x))}
          </tbody></table></div>
          ${supNote()}
          ${ps.some(p => p.costUnknown) ? P.note('‘확인 필요’는 팀 DB에 가격이 없는 자료(도서 가격·응시료·K-MOOC 수강료 등)가 들어 있다는 뜻이에요. 예상 비용에는 넣지 않았어요.') : ''}
          ${missing.length ? P.note(`${esc(missing.map(id => `${id} ${D.perspectives[id].name}`).join(', '))}은 작성에 실패해 빠졌어요. 세 안을 다시 받으려면 ‘점검 결과’에서 ‘로드맵 생성’을 다시 눌러 주세요.`) : ''}
          ${P.note(ps.length > 1 ? '고른 안(보고 있는 버전)을 쓴 에이전트(관점)만 저장해요. 고르지 않은 안과 다른 버전은 저장하지 않아요.' : '고른 안(보고 있는 버전)을 쓴 에이전트(관점)만 저장해요.')}
          ${off ? P.note('가데이터 모드에는 RAG 시나리오 후보만 있어요. 다른 목표의 후보는 좌측 ‘AI 모델’에서 RunPod-Ollama나 OpenAI API를 쓰면 확인할 수 있어요.') : ''}`,
        foot: `<button class="btn line" data-go="new-result">${icon('left')}이전</button><button class="btn pri" data-act="choose" data-need="draft.chosen">고른 안으로 검토하기</button>`
      });
    },
    after() { kickSupport(); P.watchDraft(); }
  };
  GP.act.choose = () => {
    const id = S().draft.chosen;
    if (regenBusy(id)) { GP.toast('그 안을 다시 쓰는 중이에요. 잠시 뒤에 골라 주세요'); return; }
    P.choose(id);
  };
  GP.act.ver = async arg => {
    const [pid, dir] = arg.split(':'), g = S().draft.gen; if (!g || regenBusy(pid) || !(g.hist || {})[pid]) return;
    const list = g.hist[pid], i = Math.min(list.length - 1, Math.max(0, ((g.cur || {})[pid] || 0) + +dir));
    g.cur = g.cur || {}; g.cur[pid] = i; g.options[pid] = list[i];
    if (S().draftPlan && S().draftPlan.opt === pid) S().draftPlan = null;
    GP.render(false); GP.save(); await GP.flush();
  };

  /* 다시 만들기 요청 창: 바라는 점(문장) + 빠른 칩 + 활동별 그대로/빼기/바꾸기. 아무것도 고르지 않으면 활동 구성이 다른 안을 새로 쓴다 */
  const QUICK = ['더 짧게', '실습 늘리기', '비용 줄이기', '영상 위주', '문서 위주', '업무 과제 늘리기'];
  function regenSheet(pid) {
    const d = S().draft, g = d.gen; if (!g || !g.options[pid] || regenBusy(pid)) return;
    syncGen(g);
    const o = g.options[pid], pl = P.buildPlan(o, P.params(o));
    S().regenReq = { pid, note: '', chips: [], acts: {} }; GP.save();
    GP.sheet(`<div class="rg">
      <div class="field"><label>바라는 점 <span class="muted small">선택</span></label>
        <textarea class="textarea sm" data-bind="regenReq.note" maxlength="300" aria-label="바라는 점" placeholder="예: 평일 저녁에 맞게 짧은 자료로 바꿔 주세요"></textarea>
        <div class="chips rg-chips">${QUICK.map(q => `<button type="button" class="chip" data-act="rg-chip" data-arg="${q}" aria-pressed="false">${q}</button>`).join('')}</div></div>
      <div class="field"><label>빼거나 바꿀 활동 <span class="muted small">선택</span></label><div class="rg-acts">${pl.acts.map(a => `<div class="rg-act">${P.actThumb(a, 'xs')}<span class="tx">${esc(a.title)}<small>${a.stage}단계 · ${a.task ? '직접 수행 과제' : esc((P.resOf(a.res) || {}).kind || '자료')} · ${hrs(a.hours)}</small></span>
        <div class="mini-seg" role="radiogroup" aria-label="${esc(a.title)}">${[['', '그대로'], ['remove', '빼기'], ['replace', '바꾸기']].map(([v, l]) => `<label><input type="radio" name="rg-${a.id}" value="${v}" data-bind="regenReq.acts.${a.id}" ${v ? '' : 'checked'}>${l}</label>`).join('')}</div></div>`).join('')}</div></div>
      <p class="small muted" style="margin:0">아무것도 고르지 않으면 같은 관점으로 활동 구성이 다른 안을 새로 써요. 다시 만든 안은 새 버전으로 쌓이고 ‹ › 로 이전 버전과 넘겨 볼 수 있어요.</p></div>`,
    { title: `${pid} ${D.perspectives[pid].name} 다시 만들기`, wide: true, foot: '<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="regen-go">다시 만들기</button>' });
  }
  GP.act['regen-one'] = pid => regenSheet(pid);
  GP.act['rg-chip'] = (q, el) => {
    const r = S().regenReq; if (!r) return;
    const i = r.chips.indexOf(q); if (i < 0) r.chips.push(q); else r.chips.splice(i, 1);
    el.classList.toggle('on', i < 0); el.setAttribute('aria-pressed', String(i < 0)); GP.save();
  };
  GP.act['regen-go'] = async () => {
    const q = S().regenReq, g = S().draft.gen; if (!q || !g) return;
    GP.closeSheet();
    const o = g.options[q.pid], ref = id => { const a = o.acts.find(x => x.id === id); return a ? { key: a.id, title: a.title } : null; };
    const ids = Object.keys(q.acts || {});
    const req = { wish: String(q.note || '').trim(), quick: q.chips.slice(), removeActs: ids.filter(id => q.acts[id] === 'remove').map(ref).filter(Boolean), replaceActs: ids.filter(id => q.acts[id] === 'replace').map(ref).filter(Boolean) };
    S().regenReq = null; GP.save();
    const has = req.wish || req.quick.length || req.removeActs.length || req.replaceActs.length;
    g.regenRun = Object.assign({}, g.regenRun, { [q.pid]: { req } }); GP.render(false);
    await draftCall(`${D.perspectives[q.pid].name}을 다시 만들지 못했어요`, id => API.regenerate(id, q.pid, has ? req : null), { soft: true });
    GP.render(false);
  };
  /* 다시 만들기가 끝나면 알린다(서버 작성 문서의 버전 수가 늘었을 때) */
  let regenSeen = {};
  GP.onDraftTaken = d => {
    const g = d.gen; if (!g || !g.hist) { regenSeen = {}; return; }
    Object.keys(g.hist).forEach(pid => {
      const n = g.hist[pid].length;
      if (regenSeen[pid] && n > regenSeen[pid] && String(S().route).startsWith('new-options')) GP.toast(`${D.perspectives[pid].name}을 다시 만들었어요 · 버전 ${n}`);
      regenSeen[pid] = n;
    });
  };

  /* 6. 검토·확정 */
  scr['new-review'] = {
    nav: 'new', newStep: true, title: '검토·확정', width: 'wide', guard: () => blockedTo('review'),
    render() {
      const pl = S().draftPlan, g = S().draft.gen; syncGen(g);
      const o = (g && g.options[pl.opt]) || pl.def;
      return GP.stepper('review') + P.page({
        eyebrow: `${pl.opt} ${esc(pl.name)}${g && g.hist && (g.hist[pl.opt] || []).length > 1 ? ` · 버전 ${((g.cur || {})[pl.opt] || 0) + 1}` : ''}`, title: '이 로드맵으로 확정할까요?',
        body: `<div class="card"><p style="font-weight:650">${esc(pl.goal)}</p><div style="margin-top:16px">${P.stats(pl, true)}</div></div>
          ${GP.skillMap.html(pl)}
          <div class="sec">${P.stagesView(pl)}</div>
          <p class="small muted rv-fix">고치고 싶은 활동이 있으면 <button class="link" data-act="review-regen">${icon('history')}3안 비교에서 이 안 다시 만들기</button></p>
          <div class="sec"><div class="card flat"><dl class="kv"><dt>지원 조건</dt><dd>${P.supCell(o)}</dd></dl></div>${supNote()}</div>
          ${P.note(`확정은 내 학습 계획을 정하는 것이에요. 기관의 승인·결재가 아니에요. ${P.mySup() ? `확정하면 내 계획을 보는 부서장 ${esc(P.mySup().name)} 님은 확정한 로드맵, 진행 상태, 결과 보고서를 볼 수 있어요.` : '내 계획을 보는 부서장이 없어 확정한 로드맵은 나만 봐요.'}`)}
          ${P.recs('active').length ? P.note(`지금 진행 중인 로드맵 ${P.recs('active').length}개는 그대로 두고, 이 로드맵을 함께 진행해요.`) : ''}`,
        foot: `<button class="btn line" data-go="new-options">${icon('left')}이전</button><button class="btn pri" data-act="confirm">확정하기</button>`
      });
    },
    // 스킬 지도(10/23 팀 합의 · 요약 박스 바로 아래): 자료를 처음 한 번 읽고 그 칸만 다시 그린다
    after() { kickSupport(); P.watchDraft(); GP.skillMap.load(); }
  };
  GP.act['review-regen'] = () => { const id = S().draftPlan && S().draftPlan.opt; GP.go('new-options'); if (id) regenSheet(id); };

  /* ───────── 홈 ───────── */
  /* 활동 한 줄(홈·내 로드맵 진행 중). 줄 전체가 실행 기록 창을 여는 버튼이고, 상태는 보여 주기만 한다.
     진행 상태는 실행 기록 창 안에서만 바꾼다(10/23 사용자 결정). 홈에 여러 로드맵이 함께 보여서 어느 로드맵의 활동인지 data-arg 에 넣는다 */
  const actRow = (a, R) => {
    const done = P.st(a.id, R.plan) === 'done', memo = (R.progress[a.id] || {}).memo;
    return `<li><button class="act-row" data-act="rec-open" data-arg="${R.id}|${a.id}" aria-label="${esc(`${a.title}, ${done ? '완료' : '진행 중'}${memo ? ', 메모 있음' : ''}, 실행 기록 열기`)}">${P.actThumb(a)}<span class="tx">${esc(a.title)}<small>${P.actMeta(a)} · ${hrs(a.hours)}${memo ? ' · 메모 있음' : ''}</small></span>
      ${done ? `<span class="tag acc">${icon('check')}완료</span>` : '<span class="tag">진행 중</span>'}${icon('right', 'act-go')}</button></li>`;
  };
  const draftBox = () => {
    const d = S().draft, cur = (S().lastNew || 'new-goal').split(':')[0], k = SUB[cur] || (STEPS.find(s => s[2] === cur) || STEPS[0])[0];
    return `<div class="card"><div class="sec-h"><h2 class="st">작성 중인 새 로드맵</h2><button class="link quiet" data-act="discard-draft">지우기</button></div>
      <p class="muted" style="margin:-4px 0 14px">${esc(d.goal || '목표 입력 전')}</p>${GP.stepper(k)}
      <div class="actions" style="margin-top:6px"><button class="btn line" data-go="${GP.newRoute()}">이어서 작성하기</button></div></div>`;
  };
  GP.act['discard-draft'] = async () => {
    const st = GP.own(), id = st.draftId;
    try { if (id) await API.draftDelete(id); } catch (err) { if (err.status !== 404) { GP.fail(err, '작성 중인 로드맵을 지우지 못했어요'); return; } }
    GP.takeDraftInto(st, { draftId: null, draft: null, draftPlan: null, lastNew: null });
    st.lastNew = null; GP.save(); GP.render(true); GP.toast('작성 중인 로드맵을 지웠어요');
  };
  /* 결과 보고서가 나왔는데 아직 확인하지 않은 로드맵 */
  const repAlert = R => { const r = P.planReports(R).find(x => !x.confirmed); return r ? `<button class="alert" data-go="report:${r.id}">${icon('chart')}<span class="grow"><b>결과 보고서가 나왔어요</b><br><span class="small muted">확인하면 이 로드맵을 마친 것으로 기록해요</span></span>${icon('right')}</button>` : ''; };
  const alerts = R => { const h = P.commentAlert(R) + repAlert(R); return h ? `<div class="stack hp-al">${h}</div>` : ''; };
  /* 사후 점검은 언제든 시작할 수 있다(10/14 · 세 화면 같은 규칙). 다 끝냈으면 크게 권하고, 아니면 작은 링크 */
  const postCta = (R, c) => (c.done === c.t
    ? `<div class="actions"><button class="btn pri" data-act="post-start" data-arg="${R.id}">사후 점검 시작</button></div>`
    : `<p class="small muted post-l">계획을 마무리하려면 언제든 <button class="link" data-act="post-start" data-arg="${R.id}">사후 점검</button>을 할 수 있어요.</p>`);
  const stageCard = (R, multi) => {
    const pl = R.plan, cur = P.curStage(pl), acts = P.stageActs(pl, cur);
    return `<div class="card"><div class="sec-h"><h2 class="st">이번 단계 활동${multi ? ` · ${cur}단계 ${P.stageName(cur)}` : ''}</h2><span class="small muted" style="margin-left:auto">${P.range(acts)}</span></div><ul class="acts" style="gap:14px">${acts.map(a => actRow(a, R)).join('')}</ul></div>`;
  };
  /* 로드맵 일정(간트 · WBS 방식: 로드맵 > 단계 > 활동 · 10/22 사용자 결정). 로드맵이 하나면 '전체 진행' 카드 자리에, 여럿이면 하나로 합쳐 맨 위에 둔다.
     계획에는 활동마다 n주차(주당 학습 시간으로 나눈 값)만 있어서, 1주차 = 그 로드맵을 처음 확정한 날(createdAt)이 든 주(월~일)로 놓고 날짜를 셈한다.
     칸 하나는 확정한 요일과 관계없이 늘 월~일 7일이다(10/23 사용자 결정 · 목요일에 확정해도 그 주 월요일부터 1주차).
     하나면 칸 = 그 로드맵의 주차(아래에 그 주 월요일 날짜), 여럿이면 칸 = 달력 주이고 로드맵 줄에 '지금 n주차 / 전체 N주'를 적는다.
     이번 주 칸을 칠한다. 예정 주차가 지나도 늦었다고 표시하지 않는다(스스로 정한 학습 계획). 처음엔 모두 펼치고, 접은 상태는 새로 고칠 때까지만 기억한다 */
  const DAY = 864e5;
  const ymd = s => { const [y, m, d] = String(s || '').split('-').map(Number); return y ? new Date(y, m - 1, d) : null; };
  const today0 = () => { const t = new Date(); return new Date(t.getFullYear(), t.getMonth(), t.getDate()); };
  const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  const dayGap = (a, b) => Math.round((b - a) / DAY);
  const md = d => `${d.getMonth() + 1}/${d.getDate()}`;
  const monday = d => addDays(d, -((d.getDay() + 6) % 7));
  const confirmDay = R => ymd(R.createdAt) || ymd(R.plan.confirmedAt) || today0();
  const planStart = R => monday(confirmDay(R));
  const planWeeks = pl => Math.max(1, pl.weeks || 0, ...pl.acts.map(a => a.wTo));
  const weekNow = R => Math.floor(dayGap(planStart(R), today0()) / 7) + 1;
  const gtFold = new Set();
  const folded = ins => ins.some(k => gtFold.has(k));
  /* 막대 위치: 축 첫날부터 from~to 일(to 는 포함하지 않음). 막대 사이에 2px 틈을 둔다 */
  const gtPos = (from, to, T) => `left:calc(${(from / T) * 100}% + 1px);width:calc(${((to - from) / T) * 100}% - 2px)`;
  const gtTg = (key, name) => { const open = !gtFold.has(key); return `<button class="gt-tg" data-act="gt-fold" data-arg="${esc(key)}" aria-expanded="${open}" aria-label="${esc(name)} ${open ? '접기' : '펼치기'}">${icon(open ? 'minus' : 'plus')}</button>`; };
  /* 한 줄 = 왼쪽 이름 칸 + 오른쪽 막대 칸. tip 은 마우스를 올리거나 이름 칸에 초점이 가면 보이는 설명(날짜가 먼저) */
  const gtRow = (lv, ins, label, bar, tip) => `<div class="gt-row lv${lv}" data-in="${esc(ins.join(' '))}"${folded(ins) ? ' hidden' : ''} data-tv="${esc(tip.v)}" data-tt="${esc(tip.t)}" data-tm="${esc(tip.m)}"><div class="gt-l">${label}</div><div class="gt-tl">${bar}</div></div>`;
  /* 로드맵 하나의 단계·활동 줄. off = 축 첫날부터 이 로드맵 1주차 첫날까지 일 수, T = 축 전체 일 수, up = 위 줄(로드맵)의 접기 열쇠 */
  function gtStages(R, off, T, up) {
    const pl = R.plan, base = planStart(R);
    const when = (f, t) => `${f === t ? f : `${f}~${t}`}주차 · ${md(addDays(base, 7 * (f - 1)))}~${md(addDays(base, 7 * t - 1))}`;
    return D.stages.filter(st => st.n >= pl.start && P.stageActs(pl, st.n).length).map(st => {
      const as = P.stageActs(pl, st.n), dn = as.filter(a => P.st(a.id, pl) === 'done').length, key = `${R.id}:${st.n}`;
      const f = Math.min(...as.map(a => a.wFrom)), t = Math.max(...as.map(a => a.wTo));
      const head = gtRow(1, up, `${gtTg(key, `${st.n}단계 ${st.name}`)}<span class="gt-no">${st.n}</span><span class="gt-name">${esc(st.name)}</span><span class="gt-sub">${dn}/${as.length}</span>`,
        `<span class="gt-bar sum" style="${gtPos(off + 7 * (f - 1), off + 7 * t, T)}"><i style="width:${(dn / as.length) * 100}%"></i></span>`,
        { v: when(f, t), t: `${st.n}단계 ${st.name}`, m: `활동 ${as.length}개 중 ${dn}개 완료` });
      return head + as.map((a, i) => {
        const done = P.st(a.id, pl) === 'done', no = `${st.n}.${i + 1}`, w = when(a.wFrom, a.wTo), m = `${hrs(a.hours)} · ${done ? '완료' : '진행 중'}`;
        return gtRow(2, up.concat(key), `<button class="gt-a" data-act="rec-open" data-arg="${R.id}|${a.id}" aria-label="${esc(`${no} ${a.title}, ${w}, ${m}, 실행 기록 열기`)}"><span class="gt-no">${no}</span><span class="gt-name">${esc(a.title)}</span>${done ? icon('check', 'gt-ok') : ''}</button>`,
          `<span class="gt-bar act${done ? ' done' : ''}" style="${gtPos(off + 7 * (a.wFrom - 1), off + 7 * a.wTo, T)}">${done ? icon('check') : ''}</span>`,
          { v: w, t: a.title, m });
      }).join('');
    }).join('');
  }
  /* 머리 줄(칸 이름 두 줄) + 세로 칸 선·이번 주 칸 + 줄들 + 범례 */
  const gtCard = (title, link, heads, cols, rows, note, cls) => `<div class="card gt-card"><div class="sec-h"><h2 class="st">${title}</h2>${link}</div>
    <div class="gt-scroll"><div class="gt${cls ? ` ${cls}` : ''}" style="--n:${cols.length}">
      <div class="gt-h"><div class="gt-l"><span>${heads[0]}</span><span>${heads[1]}</span></div><div class="gt-tl">${cols.map(c => `<div class="${c.on ? 'on' : ''}"${c.on ? ' aria-current="date"' : ''}><b>${c.top}</b><span>${c.sub}</span></div>`).join('')}</div></div>
      <div class="gt-body"><div class="gt-grid" aria-hidden="true">${cols.map(c => `<i class="${c.on ? 'on' : ''}"></i>`).join('')}</div>${rows}</div>
    </div></div>
    <div class="gt-key"><span><i class="k-done"></i>완료</span><span><i class="k-left"></i>남은 활동</span><span><i class="k-now"></i>이번 주</span><span class="gt-note">${note}</span></div></div>`;
  function ganttOne(R) {
    const pl = R.plan, c = P.count(pl), base = planStart(R), n = planWeeks(pl), now = weekNow(R);
    const cols = Array.from({ length: n }, (_, i) => ({ top: i + 1, sub: md(addDays(base, 7 * i)), on: i + 1 === now }));
    return gtCard(`로드맵 일정 · 활동 ${c.done}/${c.t} 완료`, `<button class="link" data-go="roadmap:${R.id}">로드맵 전체 ${icon('right')}</button>`, ['주차', '시작일(월)'], cols,
      gtStages(R, 0, 7 * n, []), `한 칸은 월~일 1주예요. 1주차는 처음 확정한 날(${md(confirmDay(R))})이 든 주(${md(base)}~${md(addDays(base, 6))})예요.`);
  }
  function ganttAll(list) {
    const starts = list.map(planStart), axis = new Date(Math.min(...starts)), now = dayGap(axis, today0());
    const n = Math.ceil(Math.max(...list.map((R, i) => dayGap(axis, starts[i]) + 7 * planWeeks(R.plan))) / 7), T = 7 * n;
    const cols = Array.from({ length: n }, (_, i) => { const d = addDays(axis, 7 * i); return { top: i === 0 || d.getDate() <= 7 ? `${d.getMonth() + 1}월` : '', sub: d.getDate(), on: now >= 7 * i && now < 7 * (i + 1) }; });
    const rows = list.map((R, i) => {
      const pl = R.plan, c = P.count(pl), off = dayGap(axis, starts[i]), w = planWeeks(pl), wk = weekNow(R);
      const at = `${wk <= w ? `지금 ${wk}주차 / ` : ''}전체 ${w}주`;
      return gtRow(0, [], `${gtTg(R.id, pl.goal)}<button class="gt-r" data-go="roadmap:${R.id}"><span class="gt-name">${esc(pl.goal)}</span><small>${at} · ${esc(pl.opt)} ${esc(pl.name)}</small></button>`,
        `<span class="gt-bar rm" style="${gtPos(off, off + 7 * w, T)}"><i style="width:${(c.done / c.t) * 100}%"></i></span>`,
        { v: `${md(starts[i])}~${md(addDays(starts[i], 7 * w - 1))} · ${at}`, t: pl.goal, m: `${pl.opt} ${pl.name} · v${pl.version} · 활동 ${c.t}개 중 ${c.done}개 완료` })
        + gtStages(R, off, T, [R.id]);
    }).join('');
    return gtCard('전체 일정', '', ['', '주 시작일(월)'], cols, rows, '한 칸은 월~일 1주예요. 로드맵마다 처음 확정한 날이 든 주를 1주차로 세요.', 'all');
  }
  GP.act['gt-fold'] = (key, el) => {
    if (gtFold.has(key)) gtFold.delete(key); else gtFold.add(key);
    const open = !gtFold.has(key), name = el.getAttribute('aria-label').replace(/ (접기|펼치기)$/, '');
    el.closest('.gt').querySelectorAll('.gt-row[data-in]').forEach(r => { r.hidden = folded(r.dataset.in.split(' ').filter(Boolean)); });
    el.setAttribute('aria-expanded', open); el.setAttribute('aria-label', `${name} ${open ? '접기' : '펼치기'}`); el.innerHTML = icon(open ? 'minus' : 'plus');
  };
  /* 설명 상자: 하나만 만들어 body 에 둔다(화면 등장 애니메이션의 transform 이 fixed 위치를 흔들지 않게). 글자는 textContent 로 넣는다 */
  let gtTip = null, gtTipRow = null;
  const tipHide = () => { if (gtTip) gtTip.hidden = true; gtTipRow = null; };
  function tipShow(row) {
    if (row === gtTipRow && gtTip && !gtTip.hidden) return;
    if (!gtTip) { gtTip = document.createElement('div'); gtTip.className = 'gt-tip'; gtTip.setAttribute('role', 'tooltip'); document.body.appendChild(gtTip); }
    gtTip.replaceChildren(...[['b', row.dataset.tv], ['span', row.dataset.tt], ['small', row.dataset.tm]].map(([tag, tx]) => { const e = document.createElement(tag); e.textContent = tx; return e; }));
    gtTip.hidden = false; gtTipRow = row;
    const bar = row.querySelector('.gt-bar') || row, box = row.closest('.gt-scroll').getBoundingClientRect(), r = bar.getBoundingClientRect();
    const tw = gtTip.offsetWidth, th = gtTip.offsetHeight, cx = Math.min(Math.max((Math.max(r.left, box.left) + Math.min(r.right, box.right)) / 2, box.left), box.right);
    const top = r.top - th - 8 < 44 ? r.bottom + 8 : r.top - th - 8;
    gtTip.style.left = `${Math.min(Math.max(cx - tw / 2, 8), window.innerWidth - tw - 8)}px`; gtTip.style.top = `${top}px`;
  }
  const tipAt = e => { const r = e.target.closest && e.target.closest('.gt-row'); if (r) tipShow(r); else if (gtTipRow) tipHide(); };
  document.addEventListener('pointerover', tipAt);
  document.addEventListener('focusin', tipAt);
  /* 마우스로 누르면 닫는다. 손가락으로 누르면 pointerover 가 먼저 와서 설명을 보여 주므로 그대로 둔다(밖을 누르거나 굴리면 닫힘) */
  document.addEventListener('pointerdown', e => { if (e.pointerType === 'mouse') tipHide(); });
  window.addEventListener('scroll', tipHide, true);
  const hello = () => esc(((GP.me() || {}).name || '').slice(1));
  const pastLink = () => { const n = P.recs().filter(R => R.status !== 'active').length; return n ? `<p class="small muted past-l"><button class="link" data-go="roadmap">지난 로드맵 ${n}개 보기 ${icon('right')}</button></p>` : ''; };
  scr.home = {
    nav: 'home', title: '홈', width: 'wide',
    render() {
      const act = P.recs('active'), drafting = GP.draftActive() ? `<div class="sec">${draftBox()}</div>` : '';
      if (!act.length) {
        if (GP.draftActive()) return `<p class="eyebrow">안녕하세요, ${hello()} 님</p><h1 class="t lg">작성 중인 로드맵이 있어요</h1><p class="lead">이어서 작성하면 마지막으로 작성하던 단계부터 이어가요.</p>${draftBox()}${pastLink()}`;
        return `<p class="eyebrow">안녕하세요, ${hello()} 님</p><h1 class="t lg">어떤 역량을 키우고 싶나요?</h1>
          <p class="lead">목표와 학습 여건을 적고 짧은 점검에 답하면, 관점이 다른 로드맵 3안을 만들어 드려요.</p>
          <div class="actions"><button class="btn pri" data-go="new-goal">새 로드맵 작성</button></div>${pastLink()}
          <div class="pstrip five" style="margin-top:40px">${[['목표 적기', '기획서는 선택'], ['세부 사항', '비워 두면 알아서'], ['사전 점검', '1~5점 척도'], ['3안 비교', '관점별 작성'], ['확정', '고친 뒤']].map(([a, b], i) => `<div><b>${i + 1}. ${a}</b>${b}</div>`).join('')}</div>`;
      }
      /* 진행 중인 로드맵이 하나면 지금까지의 홈 그대로, 여럿이면 로드맵마다 묶어서 보여 준다(개수 제한 없음 · 10/14) */
      if (act.length === 1) {
        const R = act[0], pl = R.plan, c = P.count(pl), cur = P.curStage(pl);
        return `<p class="eyebrow">${esc(pl.name)} · v${pl.version}</p><h1 class="t">이번 단계: ${cur}단계 ${P.stageName(cur)}</h1>
          <p class="lead">${esc(pl.goal)}</p>${alerts(R)}${stageCard(R)}${ganttOne(R)}${postCta(R, c)}${drafting}${pastLink()}`;
      }
      return `<p class="eyebrow">안녕하세요, ${hello()} 님</p><h1 class="t">진행 중인 로드맵 ${act.length}개</h1><p class="lead">전체 일정을 먼저 보여 드리고, 로드맵마다 이번 단계 활동을 보여 드려요.</p>
        ${ganttAll(act)}
        ${act.map(R => { const pl = R.plan, c = P.count(pl); return `<section class="hp"><div class="hp-h"><p class="eyebrow">${esc(pl.name)} · v${pl.version}</p><h2 class="hp-t">${esc(pl.goal)}</h2></div>${alerts(R)}${stageCard(R, true)}${postCta(R, c)}</section>`; }).join('')}
        ${drafting}${pastLink()}`;
    },
    /* 일정이 칸보다 넓어 옆으로 밀리면 이번 주 칸이 이름 칸 바로 옆(한 칸 띄움)에 오게 맞춘다 */
    after(view) {
      tipHide();
      view.querySelectorAll('.gt-scroll').forEach(sc => {
        const on = sc.querySelector('.gt-h .on'); if (!on || sc.scrollWidth <= sc.clientWidth) return;
        sc.scrollLeft += on.getBoundingClientRect().left - sc.getBoundingClientRect().left - sc.querySelector('.gt-h .gt-l').offsetWidth - on.offsetWidth;
      });
    }
  };

  /* ───────── 내 로드맵: 목록(진행 중 · 지난 로드맵) → 로드맵 하나 ───────── */
  const roadLi = R => {
    const pl = R.plan, c = P.count(pl), n = P.newComments(R).length;
    const tag = R.status === 'done' ? `<span class="tag line">마침 ${esc(R.doneAt || '')}</span>` : R.status === 'archived' ? `<span class="tag line">보관 ${esc(R.archivedAt || '')}</span>` : '';
    return `<button class="li" data-go="roadmap:${R.id}"><span class="idx">${icon('map')}</span><div class="tx"><b>${esc(pl.goal)}</b><small>${esc(pl.opt)} ${esc(pl.name)} · v${pl.version} · ${pl.weeks}주 · 주 ${pl.hours}시간 · 활동 ${c.done}/${c.t} 완료</small></div><span class="end">${tag}${n ? `<span class="tag acc">새 코멘트 ${n}</span>` : ''}${icon('right')}</span></button>`;
  };
  const newBtn = () => `<button class="btn line sm" data-go="${GP.draftActive() ? GP.newRoute() : 'new-goal'}">${icon('pen')}${GP.draftActive() ? '작성 중인 새 로드맵 이어서' : '새 로드맵 작성'}</button>`;
  function roadList() {
    const act = P.recs('active'), past = P.recs().filter(R => R.status !== 'active');
    if (!act.length && !past.length) return P.page({ title: '내 로드맵', body: P.noPlan() });
    return P.page({
      title: '내 로드맵', lead: act.length > 1 ? `로드맵 ${act.length}개를 함께 진행하고 있어요. 눌러서 활동을 보고 기록해요.` : '확정한 로드맵이에요. 눌러서 활동을 보고 기록해요.',
      body: `<div class="sec"><div class="sec-h"><h2 class="st">진행 중 ${act.length}</h2></div>${act.length ? `<div class="list">${act.map(roadLi).join('')}</div>` : '<p class="muted small">진행 중인 로드맵이 없어요. 새 로드맵을 작성하거나, 보관한 로드맵을 다시 진행할 수 있어요.</p>'}</div>
        ${past.length ? `<div class="sec"><div class="sec-h"><h2 class="st">지난 로드맵 ${past.length}</h2><span class="small muted" style="margin-left:auto">마친 로드맵 · 보관한 로드맵</span></div><div class="list">${past.map(roadLi).join('')}</div></div>` : ''}`,
      foot: newBtn()
    });
  }
  /* 진행 중이면 기록할 수 있고, 마쳤거나 보관한 로드맵은 읽기 전용(활동·완료·메모·버전·보고서·받은 코멘트) */
  function roadView(R) {
    const pl = R.plan, live = R.status === 'active', cs = R.comments || [], reps = P.planReports(R);
    const stTag = live ? '' : R.status === 'done' ? ` · 마침 ${esc(R.doneAt || '')}` : ` · 보관 ${esc(R.archivedAt || '')}`;
    const stages = live
      ? D.stages.filter(st => st.n >= pl.start).map(st => { const acts = P.stageActs(pl, st.n); if (!acts.length) return ''; return `<div class="stage"><div class="stage-h"><span class="no">${st.n}</span><b>${st.name}</b><span class="end">${P.range(acts)} · ${acts.filter(a => P.st(a.id, pl) === 'done').length}/${acts.length} 완료</span></div><ul class="acts" style="gap:12px;margin-top:14px">${acts.map(a => actRow(a, R)).join('')}</ul></div>`; }).join('')
      : P.stagesView(pl, { status: true, memo: true });
    const repList = reps.length ? `<div class="sec"><div class="sec-h"><h2 class="st">결과 보고서</h2></div><div class="list">${reps.map(r => `<button class="li" data-go="report:${r.id}"><span class="idx">${icon('chart')}</span><div class="tx"><b>결과 보고서 · v${r.version}</b><small>${esc(r.createdAt)} · ${r.confirmed ? '확인함' : '확인 전'}</small></div><span class="end">${icon('right')}</span></button>`).join('')}</div></div>` : '';
    const cmBtn = cs.length ? `<button class="btn ghost sm" data-go="comment:${R.id}">${icon('chat')}받은 코멘트 ${cs.length}</button>` : '';
    const foot = live
      ? `<button class="btn line sm" data-act="rev-start" data-arg="${R.id}">수정 요청</button><button class="btn ghost sm" data-act="versions" data-arg="${R.id}">${icon('history')}버전 이력</button><button class="btn ghost sm" data-act="post-start" data-arg="${R.id}">사후 점검</button>${cmBtn}<button class="btn ghost sm rm-arch" data-act="plan-archive" data-arg="${R.id}">보관하기</button>`
      : `${R.status === 'archived' ? `<button class="btn pri sm" data-act="plan-resume" data-arg="${R.id}">다시 진행하기</button>` : ''}<button class="btn ghost sm" data-act="versions" data-arg="${R.id}">${icon('history')}버전 이력</button><button class="btn ghost sm" data-act="pre-answers" data-arg="${R.id}">사전 점검 응답</button>${cmBtn}`;
    return P.page({
      back: 'roadmap', eyebrow: `${esc(pl.opt)} ${esc(pl.name)} · v${pl.version}${stTag}`, title: '내 로드맵', lead: esc(pl.goal),
      body: `${live ? alerts(R) : P.note(R.status === 'done' ? '마친 로드맵이에요. 기록은 읽기만 할 수 있어요.' : '보관한 로드맵이에요. 기록은 읽기만 할 수 있고, ‘다시 진행하기’를 누르면 이어서 기록할 수 있어요.')}${P.stats(pl)}${GP.skillMap.html(pl)}<div class="sec">${stages}</div>${repList}`,
      foot
    });
  }
  scr.roadmap = {
    nav: 'roadmap', title: '내 로드맵', width: 'wide',
    guard: param => { if (!param) return null; if (S().plans[param]) { S().cur = param; return null; } return 'roadmap'; },
    render: param => (param ? roadView(P.R(param)) : roadList()),
    // 확정한 로드맵에도 스킬 지도(10/23 사용자 요청 · 요약 박스 바로 아래)
    after: (v, param) => { if (param) GP.skillMap.load(); }
  };
  /* 보관(API-41): 진행을 멈추고 지난 로드맵으로 옮긴다. 기록은 그대로이고 언제든 다시 진행할 수 있다(API-42) */
  GP.act['plan-archive'] = pid => {
    const R = P.R(pid); if (!R || R.status !== 'active') return;
    GP.sheet(`<p style="margin-top:0">진행 기록·메모·버전·받은 코멘트는 그대로 남고, 내 로드맵의 ‘지난 로드맵’에서 볼 수 있어요.</p>
      <ul class="plain-list small"><li>홈과 진행 중 목록에서 빠져요.</li><li>부서장 화면에는 ‘보관’으로 보이고, 보관한 로드맵에는 새 코멘트를 받지 않아요.</li><li>언제든 ‘다시 진행하기’로 이어서 할 수 있어요.</li></ul>
      ${R.pending ? P.note('만들어 둔 수정안은 보관할 때 버려요.') : ''}`,
      { title: '이 로드맵을 보관할까요?', sub: R.plan.goal, foot: `<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="plan-archive-ok" data-arg="${R.id}">보관하기</button>` });
  };
  GP.act['plan-archive-ok'] = async pid => {
    GP.closeSheet();
    try { const R = P.takePlan(await API.archive(pid)); R.rev = null; GP.save(); GP.go('roadmap'); GP.toast('로드맵을 보관했어요 · 지난 로드맵에서 볼 수 있어요'); } catch (err) { GP.fail(err, '로드맵을 보관하지 못했어요'); }
  };
  GP.act['plan-resume'] = async pid => {
    try { const R = P.takePlan(await API.resume(pid)); GP.save(); GP.go('roadmap:' + R.id); GP.toast('로드맵을 다시 진행해요. 기록은 그대로 이어져요'); } catch (err) { GP.fail(err, '로드맵을 다시 진행하지 못했어요'); }
  };

  /* ───────── 사후 점검·결과 보고서 ───────── */
  /* 사후 점검 시작 (홈·내 로드맵·점검·보고서 모두 같은 규칙 · 10/14): 언제든 시작할 수 있고,
     '진행 중'인 활동이 남아 있으면 한 번 확인한다(이미 답하기 시작했으면 묻지 않음) */
  GP.act['post-start'] = pid => {
    const R = P.R(pid); if (!R || R.status !== 'active') return;
    const left = R.plan.acts.filter(a => P.st(a.id, R.plan) !== 'done').length;
    const begun = !!(R.post.goalSelf || Object.keys(R.post.answers || {}).length || R.post.fail);
    if (!left || begun) { GP.closeSheet(); GP.go('post:' + R.id); return; }
    GP.sheet(`<p style="margin-top:0">아직 ‘진행 중’인 활동이 <b>${left}개</b> 있어요.</p><p class="small muted">지금 사후 점검을 하면 결과 보고서에 그 활동은 ‘진행 중’으로 남아요. 보고서를 확인하면 이 로드맵을 마친 것으로 기록해요.</p>`,
      { title: '사후 점검을 시작할까요?', sub: R.plan.goal, foot: `<button class="btn line" data-act="sheet-close">활동 더 하기</button><button class="btn pri" data-go="post:${R.id}">사후 점검 시작</button>` });
  };
  /* 사후 점검 응답은 고칠 때마다 서버에 저장한다(API-49 · 팀 DB 응답 표 POST). 결과물 파일은 서버 폴더에 올린 뒤 이름만 붙인다 */
  let postQ = Promise.resolve();
  /* 사후 심화 답(10/23)은 문항이 준비되고 보고서를 만들기 전까지만 보낸다(보고서를 만든 뒤에는 서버가 고정) */
  const deepOpen = dp => !!(dp && dp.status === 'ready' && !dp.judge);
  function savePost(R, extra) {
    postQ = postQ.then(async () => {
      const cur = P.R(R.id) || R, dp = cur.post.deep;
      const body = Object.assign({ answers: cur.post.answers, goalSelf: cur.post.goalSelf }, deepOpen(dp) ? { deepMcq: dp.mcq || {}, deepEssay: dp.essay || {} } : {}, extra || {});
      try {
        const res = await API.savePost(R.id, body);
        /* 보내는 사이 서술형을 더 썼으면 서버 응답이 덮지 않게 화면의 심화 답을 그대로 둔다 */
        const mine = (P.R(R.id) || {}).post, nr = P.takePlan(res);
        if (nr && mine && deepOpen(mine.deep) && deepOpen(nr.post.deep)) Object.assign(nr.post.deep, { mcq: mine.deep.mcq, essay: mine.deep.essay });
      } catch (err) { GP.fail(err, '사후 점검 응답을 저장하지 못했어요'); }
    });
    return postQ;
  }
  /* 사후 심화 질문(10/23): 사전에 심화를 고른 로드맵이면 사후 점검 화면에 들어올 때 서버가 같은 개념의 새 문제를 만든다.
     실패는 가데이터로 대신하지 않고 '다시 시도'를 눌러야만 다시 만든다 */
  const POST_DEEP_AGENT = '진단 에이전트 · 사후 심화 질문 생성', pdAsk = new Set(), pdStop = new Set();
  async function ensurePostDeep(R) {
    const dp = R.post.deep; if (!dp || dp.status === 'ready' || dp.status === 'fail' || pdAsk.has(R.id) || pdStop.has(R.id)) return;
    pdAsk.add(R.id);
    try {
      const j = dp.status === 'run' && dp.jobId ? { jobId: dp.jobId } : await API.postDeep(R.id);
      if (j && j.jobId) { try { await API.job(j.jobId); } catch (err) { /* 실패 원인은 서버(post.deep.fail)에 남아 있다 */ } }
    } catch (err) { pdStop.add(R.id); GP.fail(err, '사후 심화 질문을 만들지 못했어요'); }  // 요청 자체가 거절되면 자동으로 다시 부르지 않는다
    pdAsk.delete(R.id);
    await P.pullPlan(R.id);
    if (S().route === 'post:' + R.id) GP.render(false);
  }
  GP.act['post-deep-retry'] = id => { const R = P.R(id); if (!R || !R.post.deep) return; pdStop.delete(id); R.post.deep = Object.assign({}, R.post.deep, { status: 'none', fail: null }); GP.render(false); ensurePostDeep(R); };
  P.postDeepCard = R => {
    const dp = R.post.deep; if (!dp) return '';
    if (dp.status === 'ready' && dp.quiz) {
      return `<div class="card deep-opt on"><p class="eyebrow">${icon('spark')}심화 질문 · 사후</p><p class="small muted">사전 점검에서 심화 질문을 골라, 같은 개념을 묻는 새 문제를 냈어요. 객관식은 모두 골라 주세요(‘잘 모르겠어요’도 돼요). 서술형은 비워 둬도 돼요. ${dp.judge ? '보고서를 만들어 답이 고정됐어요. 정답과 모범 답안은 결과 보고서에서 펼쳐 볼 수 있어요.' : '정답과 모범 답안은 결과 보고서에서 펼쳐 볼 수 있어요.'}</p>${(dp.notes || []).map(n => `<p class="small muted">${esc(n)}</p>`).join('')}</div>`;
    }
    if (dp.status === 'fail') {
      const c = AI.cause((dp.fail || {}).cause || {});
      return `<div class="agents">${P.agentRow({ st: 'fail', name: POST_DEEP_AGENT, sub: esc(P.errText(c)), tag: '오류 발생', tagCls: 'fail', retry: ['post-deep-retry', R.id] })}</div>`;
    }
    return `<div class="agents">${P.agentRow({ st: 'run', name: POST_DEEP_AGENT, sub: P.runSub('default', '같은 개념을 묻는 새 심화 질문을 만들고 있어요') })}</div>`;
  };
  async function postFile(f) {
    const R = P.R(); if (!R) return;
    try { const up = await API.attach(R.id, 'post', f); await savePost(R, { file: { fileId: up.fileId, name: up.name, size: up.size } }); }
    catch (err) { R.post.file = null; GP.fail(err, '결과물을 올리지 못했어요'); }
    GP.render(false);
  }
  scr.post = {
    nav: 'checks', title: '사후 점검', width: 'wide', guard: P.planGuard('post', 'checks', true),
    render() {
      const R = P.R(), pl = R.plan;
      /* 보고서 작성 실패: 가데이터로 대신하지 않고 안내한다. 응답은 그대로 두고, '다시 시도하기'를 눌러야만 다시 쓴다(10/14) */
      const f = R.post.fail;
      if (f && !R.post.running) {
        const c = AI.cause(f.cause || {});
        return P.failPage({
          title: '결과 보고서를 만드는 중 문제가 발생했어요',
          desc: '진단 에이전트가 결과 보고서를 쓰지 못했어요. 사후 점검 응답과 목표 달성도, 결과물은 그대로 남아 있어요.',
          cause: esc(P.errText(c)),
          body: `<div class="agents">${P.agentRow({ st: 'fail', name: '진단 에이전트 · 결과 보고서 작성', sub: AI.live() ? via('default') : '', tag: '오류 발생', tagCls: 'fail' })}</div>`,
          ops: P.opsBox([['', c]]),
          foot: `<button class="btn line" data-act="post-fail-back">${icon('left')}사후 점검 응답 보기</button><button class="btn pri" data-act="make-report">${icon('retry')}다시 시도하기</button>`
        });
      }
      const left = pl.acts.filter(a => P.st(a.id, pl) !== 'done').length;
      return P.page({
        back: 'checks', eyebrow: `${esc(pl.name)} · v${pl.version} · ${esc(pl.goal)}`, title: '사후 점검', lead: '사전 점검과 같은 문항이에요. 지금 기준으로 1~5점을 골라 주세요. 진단 에이전트가 계산한 수준값은 보여드리지 않아요.',
        body: `${left ? P.note(`아직 ‘진행 중’인 활동이 ${left}개 있어요. 결과 보고서에는 ‘진행 중’으로 남아요. 답한 내용은 서버에 저장되니 활동을 더 한 뒤 이어서 답해도 돼요.`) : ''}${P.postDeepCard(R)}<div class="stack">${P.quizBody(pl.assess.questions, 'post.answers', pl.assess.answers, deepOpen(R.post.deep) ? { quiz: R.post.deep.quiz, mcq: 'post.deep.mcq', essay: 'post.deep.essay' } : null)}
          <div class="card"><h2 class="st">처음 목표를 얼마나 이뤘나요?</h2><div class="chips">${D.goalSelf.map((l, i) => `<label class="chip"><input type="radio" name="goalSelf" value="${i + 1}" data-bind="post.goalSelf" ${String(R.post.goalSelf) === String(i + 1) ? 'checked' : ''}>${l}</label>`).join('')}</div></div>
          <div class="card"><h2 class="st">결과물·수료증 <span class="muted small" style="font-weight:400">선택</span></h2>${R.post.file ? `<div class="file-on">${icon('file')}<div class="tx"><b>${esc(R.post.file.name)}</b><small class="muted">서버에 보관 · 내용은 검증하지 않아요</small></div></div>` : `<label class="drop"><input type="file" data-bind-file="post.file"><span class="ico">${icon('file')}</span><span><b>결과물·수료증 고르기</b><small>내지 않아도 기록은 그대로예요</small></span></label>`}</div></div>`,
        foot: R.post.running ? '<button class="btn pri" disabled><span class="sp"></span>진단 에이전트가 보고서를 쓰고 있어요…</button>' : '<button class="btn pri" data-act="make-report" data-need="post">결과 보고서 만들기</button>'
      });
    },
    /* 새로 고침·재접속: 쓰던 보고서는 서버 작업을 이어서 기다린다(새 작업을 만들지 않음 · 10/20) */
    after() { const R = P.R(); if (R && R.post.running && R.post.jobId) waitReport(R, R.post.jobId); if (R) ensurePostDeep(R); }
  };
  /* 보고서 작성(API-50): 서버 작업. 끝나면 보고서 목록을 다시 읽고 보고서 화면으로 간다 */
  const repWait = new Set();
  async function waitReport(R, jobId) {
    if (repWait.has(jobId)) return;
    repWait.add(jobId);
    const here = () => S().route === 'post:' + R.id;
    let out = null;
    try { out = await API.job(jobId); } catch (err) { /* 실패 원인은 서버(post.fail)에 남아 있다 */ }
    repWait.delete(jobId);
    if (!GP.me()) return;
    if (out && out.reportId) {
      await GP.reload();
      if (here()) GP.go('report:' + out.reportId); else GP.toast('결과 보고서가 나왔어요 · 점검·보고서에서 볼 수 있어요');
    } else { await P.pullPlan(R.id); if (here()) GP.render(false); }
  }
  GP.act['make-report'] = async () => {
    const R = P.R(); if (!R || R.post.running) return;
    clearTimeout(postT); await savePost(R, R.post.fail ? { clearFail: true } : null);
    R.post.running = true; R.post.fail = null; GP.render(false);
    try { const j = await API.makeReport(R.id); R.post.jobId = j.jobId; waitReport(R, j.jobId); }
    catch (err) { R.post.running = false; GP.fail(err, '결과 보고서를 만들지 못했어요'); await P.pullPlan(R.id); GP.render(false); }
  };
  GP.act['post-fail-back'] = async () => { const R = P.R(); if (!R) return; await savePost(R, { clearFail: true }); R.post.fail = null; GP.render(false); };
  const lst = (arr, f) => (arr.length ? `<ul class="plain-list">${arr.map(f).join('')}</ul>` : '<p class="muted small">없음</p>');
  /* 보고서 본문: 직원 화면과 부서장 화면(소속 직원 보고서 · 10/15 전체 공개)이 함께 쓴다 */
  P.reportBody = r => `<div class="grid2">
            <div class="card"><h2 class="st">응답이 오른 것</h2>${lst(r.gained, x => `<li><b>${esc(x.skill)}</b> <span class="small muted">${esc(P.ansLabel(x.from))} → ${esc(P.ansLabel(x.to))}</span></li>`)}</div>
            <div class="card"><h2 class="st">그대로이거나 내려간 것</h2>${lst(r.still, x => `<li>${esc(x.skill)} <span class="small muted">${esc(P.ansLabel(x.from))} → ${esc(P.ansLabel(x.to))}</span></li>`)}</div></div>
          <div class="card" style="margin-top:12px"><h2 class="st">실행 기록</h2><dl class="kv"><dt>완료로 기록</dt><dd>${esc(r.doneTitles.join(', ') || '없음')}</dd><dt>진행 중</dt><dd class="muted">${esc(r.restTitles.join(', ') || '없음')}</dd>
            <dt>목표 달성</dt><dd>${esc(r.goalSelf)}</dd><dt>결과물</dt><dd>${r.file ? esc(r.file.name) + ' <span class="small muted">· 내용 미검증</span>' : '붙이지 않음'}</dd></dl></div>
          <div class="sec"><h2 class="st">잘된 점</h2><div class="card"><ul class="plain-list">${r.good.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div></div>
          <div class="sec"><h2 class="st">보완할 점</h2><div class="card"><ul class="plain-list">${r.improve.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div></div>
          <div class="sec"><h2 class="st">다음 로드맵 제안</h2><div class="card acc"><p style="font-weight:650">${esc(r.next.goal)}</p><p class="small muted" style="margin-top:4px">${esc(r.next.why)}</p></div>
            <p class="small muted" style="margin-top:8px">참고용 제안이에요. 새 로드맵은 ‘새 로드맵 작성’에서 목표를 직접 적어 시작해요.</p></div>
          ${P.note('자기보고 응답의 변화예요. 실제 개발 역량이나 인사평가 결과로 보지 않아요. 진단 에이전트가 계산한 수준값은 저장만 하고 보여주지 않아요.')}`;
  /* 보고서의 심화 질문 결과(10/23 · 본인 화면만 · 부서장 화면에는 서버가 빼고 보냄): 개념별 사전→사후 객관식 결과, 영역별 서술형 판단,
     그리고 사후 정답·모범 답안(접어 둠) */
  P.reportDeep = (r, R) => {
    if (!r.deep) return '';
    const pd = R && R.post && R.post.deep;
    return `<div class="card" style="margin-top:12px"><h2 class="st">심화 질문 결과 <span class="muted small" style="font-weight:400">나만 봐요 · 사전 → 사후</span></h2>
      <ul class="plain-list">${r.deep.concepts.map(c => `<li>${esc(c.concept)} <span class="small"><span class="dr-tag ${RES_TAG[c.pre] || 'mid'}">${esc(c.pre)}</span> → <span class="dr-tag ${RES_TAG[c.post] || 'mid'}">${esc(c.post)}</span></span></li>`).join('')}</ul>
      ${r.deep.essays.map(e => `<p class="small" style="margin-top:8px"><b>${esc(e.area)} 서술형</b> ${esc(e.pre || '-')} → <span class="dr-tag ${LV_TAG[e.post] || 'mid'}">${esc(e.post || '판단 못 함')}</span> <span class="muted">${esc(e.why || '')}</span></p>`).join('')}
      <p class="small muted" style="margin-top:8px">심화 질문은 학습 확인용이에요. 역량 판정이나 인사평가에 쓰지 않아요.</p></div>
      ${pd && pd.judge ? P.deepReveal(R.plan.assess.questions, pd.quiz, pd.mcq, pd.essay, pd.grade, pd.judge, '사후 심화 질문 정답·모범 답안 보기') : ''}`;
  };
  scr.report = {
    nav: 'checks', title: '결과 보고서', width: 'wide',
    render(id) {
      const r = P.report(id); if (!r) return P.page({ back: 'checks', title: '결과 보고서가 없어요' });
      const R = S().plans[r.planId], sup = P.mySup();
      return P.page({
        back: 'checks', eyebrow: `결과 보고서 · ${esc(r.opt)} v${r.version} · ${esc(r.createdAt)}`, title: '학습 결과 보고서', lead: esc(r.goal),
        body: `${P.reportBody(r)}${P.reportDeep(r, R)}
          ${sup ? P.note(`이 보고서는 내 계획을 보는 부서장 ${esc(sup.name)} 님도 볼 수 있어요.`) : ''}
          ${r.confirmed ? '' : P.note(`‘확인했어요’를 누르면 이 로드맵을 마친 것으로 기록하고 내 로드맵의 ‘지난 로드맵’으로 옮겨요. 확인하기 전에는 사후 점검을 다시 작성해 새 보고서를 만들 수 있고, 확인한 뒤에는 읽기 전용이라 다시 점검하려면 새 로드맵에서 시작해요.${R && R.status === 'active' ? ` <button class="link" data-go="post:${R.id}">사후 점검 다시 작성하기</button>` : ''}`)}`,
        foot: r.confirmed ? (R ? `<button class="btn line" data-go="roadmap:${R.id}">로드맵 보기</button>` : '') : `<button class="btn pri" data-act="report-ok" data-arg="${r.id}">확인했어요</button>`
      });
    }
  };
  GP.act['report-ok'] = async id => {
    try { await API.confirmReport(id); await GP.reload(); GP.go('home'); GP.toast('결과 보고서를 확인했어요 · 이 로드맵은 지난 로드맵으로 옮겼어요'); } catch (err) { GP.fail(err, '보고서 확인을 저장하지 못했어요'); }
  };

  /* ───────── 로그인 (서버 · API-01) ─────────
     팀 DB 직원(사번)과 관리자 전용 계정(직원과 별개 · 2026-10-21 사용자 결정)이 같은 칸으로 로그인한다. 비밀번호는 서버가 argon2 로 확인한다.
     시연 환경은 모든 계정의 초기 비밀번호가 같다(.env GP5_DEMO_PASSWORD · 로컬 사본만). 계정은 로그아웃한 뒤 다시 로그인해야만 바뀐다.
     '직원 고르기'(시연용)는 부서별로 묶고, 팀이 넣은 테스트 계정은 따로 묶는다 */
  const feat = (ic, t, d) => `<div class="feat"><span class="ico">${icon(ic)}</span><span><b>${t}</b><small>${d}</small></span></div>`;
  const deptGroups = () => {
    const out = [], team = [];
    GP.ACCTS.forEach(e => {
      if (e.team) { team.push(e); return; }
      let g = out.find(x => x.dept === e.dept); if (!g) out.push(g = { dept: e.dept || '부서 없음', list: [] }); g.list.push(e);
    });
    out.forEach(g => g.list.sort((a, b) => (b.supervisor ? 1 : 0) - (a.supervisor ? 1 : 0)));
    if (team.length) out.push({ dept: '팀 DB 테스트 계정', list: team });
    return out;
  };
  const demoPw = () => (GP.DEMO && GP.DEMO.demoPassword) || '';
  scr.login = {
    title: '로그인',
    render: () => `<div class="login-wrap">
      <section class="login-card" aria-labelledby="lgTitle">
        <span class="tag acc">${icon('lock')}한국수자원공사 임직원 로그인 · 시연용</span>
        <h1 class="t lg" id="lgTitle">다시 오신 걸 환영해요</h1>
        <p class="lead">AI 활용·개발 역량 성장 로드맵을 이어서 만들어 보세요.</p>
        <form id="loginForm" novalidate>
          <div class="field lg-pick"><label for="lgPick">직원 고르기 <span class="muted small">시연용 · 고르면 사번을 채워요</span></label>
            <select class="input" id="lgPick"><option value="">팀 DB 직원 ${GP.ACCTS.length}명 중 고르기</option>${deptGroups().map(g => `<optgroup label="${esc(g.dept)}">${g.list.map(e => `<option value="${esc(e.code)}">${esc(e.name)}${e.supervisor ? ' (부서장)' : ''}${e.team ? ` · ${esc(e.dept)}` : ''}</option>`).join('')}</optgroup>`).join('')}
              ${GP.DEMO && GP.DEMO.adminLogin ? `<optgroup label="관리자"><option value="${esc(GP.DEMO.adminLogin)}">관리자 전용 계정 (${esc(GP.DEMO.adminLogin)})</option></optgroup>` : ''}</select></div>
          <div class="field"><label for="lgId">사번 또는 관리자 아이디</label><input class="input" id="lgId" maxlength="40" autocomplete="username" placeholder="8자리 사번 (예: 20200001)"></div>
          <div class="field"><label for="lgPw">비밀번호</label><div class="pw"><input class="input" id="lgPw" type="password" autocomplete="current-password" placeholder="비밀번호를 입력해 주세요"><button type="button" class="eye" data-act="pw-toggle" aria-label="비밀번호 보기">${icon('eye')}</button></div></div>
          <div class="row" style="margin-top:14px"><label class="check"><input type="checkbox" id="lgKeep" checked>로그인 상태 유지</label><span class="grow"></span><button type="button" class="link quiet" data-act="login-help" data-arg="pw">비밀번호 찾기</button></div>
          <p class="err" id="lgErr" role="alert" hidden></p>
          <button class="btn pri block" type="submit" style="margin-top:18px">로그인 ${icon('arrow')}</button>
        </form>
        <div class="or">또는</div>
        <button class="btn line block" data-act="login-help" data-arg="sso">${icon('users')}기관 통합인증(SSO)으로 로그인</button>
        ${GP.ACCTS.length ? '' : P.note('직원 목록을 불러오지 못했어요. 서버(목업_실행.cmd)와 DB가 켜져 있는지 확인해 주세요.')}
        ${P.note(`시연용 화면이에요. 기관 통합인증은 연결하지 않았어요. 팀 DB(PostgreSQL) 직원의 사번으로 들어올 수 있고, 시연 환경의 초기 비밀번호는 모두 ${esc(demoPw() || '.env에 정한 값')}이에요. 비밀번호는 서버가 해시로만 확인해요. 관리자 화면은 관리자 전용 계정으로 들어가요. 다른 계정으로 바꾸려면 로그아웃한 뒤 다시 로그인해 주세요.`)}
      </section>
      <aside class="login-side">
        <span class="pill">${icon('spark')}개발·운영 직원 AI 역량 성장지원</span>
        <h2>목표만 적으면,<br>나에게 맞는 로드맵 3안을</h2>
        <p>목표와 학습 여건을 적고 짧은 점검에 답하면, 관점이 다른 로드맵 3안을 비교해 고를 수 있어요.</p>
        <div class="feats">
          ${feat('edit', '학습 여건은 간단한 입력으로', '학습 방식·자격증·시간·기간·예산을 적거나, 비워 두면 알아서 정해요.')}
          ${feat('map', '관점별 로드맵 3안', '비용·시간·업무 적용 관점의 에이전트가 동시에 쓰고, 마음에 들지 않는 안은 그 안만 다시 만들어요.')}
          ${feat('chat', '사내 생활 도우미', '업무·사내 생활 질문에 답하고, 규정 질문은 기관 규정 원문의 근거 조항과 함께 답해요.')}
        </div>
        <p class="small" style="margin-top:auto;opacity:.82">부서장은 자기 부서 직원과 바로 아래 부서의 부서장이 확정한 로드맵·진행 상태·결과 보고서를 보고 코멘트만 남겨요.</p>
      </aside>
    </div>`,
    after(root) {
      const f = root.querySelector('#loginForm'); if (!f) return;
      const pick = root.querySelector('#lgPick'), idIn = root.querySelector('#lgId'), pw = root.querySelector('#lgPw'), err = root.querySelector('#lgErr');
      const fail = t => { err.textContent = t; err.hidden = false; };
      /* 직원을 고르면 사번을 채우고 비밀번호 칸으로. 사번을 직접 적으면 맞는 직원을 골라 둔다 */
      pick.addEventListener('change', () => { if (pick.value) { idIn.value = pick.value; err.hidden = true; pw.focus(); } });
      idIn.addEventListener('input', () => { const v = idIn.value.trim(); pick.value = [...pick.options].some(o => o.value === v) ? v : ''; });
      f.addEventListener('submit', async e => {
        e.preventDefault();
        const code = idIn.value.trim(), p = pw.value;
        if (!code || !p) return fail('사번과 비밀번호를 입력해 주세요.');
        const keep = !!(root.querySelector('#lgKeep') || {}).checked, btn = f.querySelector('[type="submit"]');
        btn.disabled = true; err.hidden = true;
        let acct;
        try { acct = await API.login(code, p, keep); } catch (x) {
          btn.disabled = false; pw.value = '';
          const c = (x && x.payload) || {};
          return fail(c.code === 'ACCOUNT_INACTIVE' ? '지금은 쓸 수 없는 계정이에요. 인사 담당 부서(인재경영실 · 가상)에 문의해 주세요.' : x.status === 401 ? '사번 또는 비밀번호가 맞지 않아요.' : AI.cause(x).user);
        }
        pw.value = '';
        try { await GP.setAccount(acct); } catch (x) { btn.disabled = false; return fail(`로그인했지만 기록을 불러오지 못했어요 · ${AI.cause(x).user}`); }
        const r = GP.S.route;
        GP.go(GP.isAdmin() ? 'admin' : r && r !== 'login' && r !== 'admin' && (!/^m-/.test(r) || GP.isSup(GP.me())) ? r : 'home', { force: true });
        GP.toast(GP.isAdmin() ? `관리자 ${acct.admin.name} 님, 반가워요` : `${acct.user.name} 님, 반가워요`);
        if (GP.me() && AI.live()) AI.ping();
      });
    }
  };
  GP.act['pw-toggle'] = (a, el) => { const i = document.getElementById('lgPw'); i.type = i.type === 'password' ? 'text' : 'password'; el.setAttribute('aria-label', i.type === 'password' ? '비밀번호 보기' : '비밀번호 숨기기'); };
  GP.act['login-help'] = k => GP.toast(k === 'sso' ? '시연에서는 기관 통합인증을 연결하지 않았어요. 사번과 비밀번호로 로그인해 주세요' : `시연에서는 비밀번호 찾기를 연결하지 않았어요. 초기 비밀번호는 ${demoPw() || '.env에 정한 값'}이에요`);

  /* ───────── 앞 단계를 바꾼 채로 뒤 단계 화면에 들어오면 (10/14) ─────────
     '다음'을 누를 때 묻지 못한 경우(홈에서 이어서 작성, 브라우저 뒤로·앞으로, 새로 고침)에도 결과를 몰래 다시 만들지 않도록
     그 화면 대신 확인 카드를 보여 준다. 고르기 전에는 아무것도 지우거나 다시 만들지 않는다 */
  const stepOf = id => (STEPS.find(x => x[2] === id) || [SUB[id]])[0];
  Object.keys(DOWN).reduce((a, k) => a.concat(DOWN[k]), []).filter((x, i, a) => a.indexOf(x) === i).forEach(id => {
    const sc = scr[id], r0 = sc.render, a0 = sc.after;
    const hit = () => { const st = P.stale(); return st && DOWN[st.kind].includes(id) ? st : null; };
    sc.render = function (arg) {
      const st = hit(); if (!st) return r0.call(this, arg);
      return GP.stepper(stepOf(id)) + P.page({ eyebrow: '앞 단계를 바꿨어요', title: '바꾼 내용으로 계속할까요?', body: `<div class="card">${staleText(st)}</div>`, foot: staleBtns(st, id) });
    };
    sc.after = function (root, arg) { if (!hit() && a0) return a0.call(this, root, arg); };
  });

  /* 초기화·단계 이동·로그아웃 뒤: 화면에만 둔 값을 비운다 */
  const prevReset = GP.onDataReset;
  GP.onDataReset = () => { if (prevReset) prevReset(); gs = null; ++gsTok; docErr = null; regenSeen = {}; supKicked.clear(); };

  /* ───────── 시연 단계 이동 (서버 /demo/jump · 로그인한 계정의 기록만) ─────────
     다른 계정의 기록이 필요한 '부서장 코멘트 작성' 단계는 뺐다: 직원 계정으로 '로드맵 실행 중'까지 옮긴 뒤 로그아웃하고 그 직원의 부서장으로 로그인한다.
     '코멘트 받은 뒤'는 DB 의 '내 계획을 보는 부서장' 이름으로 예시 코멘트를 넣는다(부서장이 없는 계정은 쓸 수 없음) */
  GP.JUMPS = [['start', '처음부터'], ['details', '세부 사항부터'], ['quiz', '사전 점검부터'], ['result', '점검 결과부터'], ['options', '로드맵 3안부터'], ['review', '확정 직전'],
    ['active', '로드맵 실행 중'], ['multi', '로드맵 2개 함께 진행'], ['comment', '코멘트 받은 뒤'], ['post', '사후 점검부터'], ['report', '결과 보고서']];
})();

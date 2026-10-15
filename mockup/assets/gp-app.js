/* GrowPath 4차 목업 (Claude) · 화면
   로그인 / 홈 / 새 로드맵 작성(목표·기획서 → 세부 사항 → 사전 점검 → 점검 결과 → 3안 → 검토·확정) / 내 로드맵 / 점검·보고서 */
(function () {
  'use strict';
  const GP = window.GP, D = GP.D, AI = GP.AI, P = GP.P, { esc, won, hrs, icon } = GP;
  const S = () => GP.S, scr = GP.screens;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  /* ───────── 새 로드맵 작성 단계 ───────── */
  const STEPS = [['goal', '목표·기획서', 'new-goal'], ['details', '세부 사항', 'new-details'], ['quiz', '사전 점검', 'new-quiz'], ['result', '점검 결과', 'new-result'], ['options', '로드맵 3안', 'new-options'], ['review', '검토·확정', 'new-review']];
  const stepDone = k => {
    const d = S().draft;
    /* 세부 사항은 모두 선택 사항이라, 확인 화면에서 '다음'을 눌렀거나 사전 점검 문항이 있으면 지난 것으로 본다 */
    return { goal: GP.valid.goal(), details: !!(d.detailsOk || d.quiz), quiz: GP.valid.quizDone(), result: !!(d.handoff || d.gen), options: !!S().draftPlan, review: false }[k];
  };
  const stepPassed = stepDone;
  const blockedTo = k => { const i = STEPS.findIndex(s => s[0] === k); const b = STEPS.slice(0, i).find(([kk]) => !stepPassed(kk)); return b ? b[2] : null; };
  GP.stepper = cur => `<nav class="stepper" aria-label="새 로드맵 작성 단계"><ol>${STEPS.map(([k, l, r], i) => {
    const st = k === cur ? 'cur' : stepDone(k) ? 'done' : !blockedTo(k) ? 'open' : 'lock';
    return `<li class="${st}"><button data-go="${r}" ${st === 'lock' ? 'disabled' : ''} ${k === cur ? 'aria-current="step"' : ''}><span class="sn">${st === 'done' ? icon('check') : i + 1}</span><span class="sl">${l}</span></button></li>`;
  }).join('')}</ol></nav>`;
  GP.draftActive = () => { const d = S().draft; return !!(d.goal.trim() || d.detailsOk); };
  /* 단계 표시에 따로 없는 하위 화면은 속한 단계로 보여 준다 */
  const SUB = { 'new-details-check': 'details', 'new-result-edit': 'result', 'new-gen': 'options' };
  GP.newRoute = () => S().lastNew || 'new-goal';

  /* 사전 점검 문항은 목표·기획서(파일과 요약)로 만든다. 요약을 고쳐도 문항을 다시 만든다 */
  P.docSummary = d => (d.doc && d.doc.status === 'ok' ? String(d.doc.summary || '').trim() : '');
  P.quizKey = d => d.goal.trim() + '|' + (d.project ? d.project.name : '') + '|' + P.docSummary(d);
  P.diagKey = d => (d.quiz ? d.quiz.key : '') + '|' + (d.quiz ? d.quiz.questions.map(q => d.answers[q.id] || '-').join(',') : '');
  P.genKey = h => JSON.stringify(h);
  const clone = o => JSON.parse(JSON.stringify(o));
  function clearFrom(stage) {
    const d = S().draft;
    if (stage === 'quiz') { d.quiz = null; d.answers = {}; d.quizFail = null; }
    if (stage === 'quiz' || stage === 'diag') { d.diag = null; d.diagFail = null; d.startStage = null; d.fix = null; d.edit = null; }
    d.handoff = null; d.gen = null; d.chosen = null; S().draftPlan = null; d.genRun = null;
    Object.keys(regenErr).forEach(k => { delete regenErr[k]; });
  }

  /* ───────── 앞 단계를 고쳤을 때 (10/14) ─────────
     입력하는 동안에는 뒤 단계 결과를 지우지 않는다. 바꾼 채로 앞으로 넘어가려 할 때(다음·단계 표시) 무엇을 다시 만드는지 확인하고,
     '바꾼 내용으로 계속'이면 그때 지우고, '원래대로 되돌리기'면 결과를 만들 때의 입력으로 돌려 놓는다 */
  const ORDER = ['new-goal', 'new-details', 'new-details-check', 'new-quiz', 'new-result', 'new-result-edit', 'new-gen', 'new-options', 'new-review'];
  const DOWN = { quiz: ['new-quiz', 'new-result', 'new-result-edit', 'new-gen', 'new-options', 'new-review'], diag: ['new-result', 'new-result-edit', 'new-gen', 'new-options', 'new-review'], gen: ['new-gen', 'new-options', 'new-review'] };
  /* 지금 입력이 뒤 단계 결과를 만들 때와 다르면 그 단계: quiz(목표·기획서) > diag(사전 점검 응답) > gen(세부 사항) */
  P.stale = function () {
    const d = S().draft;
    if (d.quiz && d.quiz.key !== P.quizKey(d)) return { kind: 'quiz', input: 'new-goal', what: '목표·기획서를', back: !!d.quiz.base };
    if (d.diag && d.diag.key !== P.diagKey(d)) return { kind: 'diag', input: 'new-quiz', what: '사전 점검 응답을', back: !!d.diag.answers };
    if ((d.handoff || d.gen) && d.genPrefs && JSON.stringify(d.genPrefs) !== JSON.stringify(d.prefs)) return { kind: 'gen', input: 'new-details', what: '세부 사항을', back: true };
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
  P.applyStale = st => { clearFrom(st.kind === 'gen' ? 'gen' : st.kind); GP.save(); };
  P.revertStale = st => {
    const d = S().draft;
    if (st.kind === 'quiz') { const b = d.quiz.base; d.goal = b.goal; d.project = b.project ? clone(b.project) : null; d.doc = b.doc ? clone(b.doc) : null; d.quizFail = null; }
    else if (st.kind === 'diag') d.answers = clone(d.diag.answers);
    else { d.prefs = clone(d.genPrefs); d.detailsOk = true; }
    GP.save();
  };
  /* 앞으로 넘어갈 때만 묻는다(뒤로 가기·홈으로 가기는 그대로 두고, 나중에 뒤 단계 화면에 들어오면 그 화면에서 묻는다) */
  GP.beforeGo = target => {
    const st = P.stale(); if (!st) return true;
    const fi = ORDER.indexOf(String(S().route).split(':')[0]), ti = ORDER.indexOf(String(target).split(':')[0]);
    if (fi < 0 || ti < 0 || ti <= fi || fi < ORDER.indexOf(st.input)) return true;
    GP.sheet(staleText(st), { title: '바꾼 내용으로 계속할까요?', foot: staleBtns(st, target) });
    return false;
  };
  GP.act['stale-go'] = target => { const st = P.stale(); if (st) P.applyStale(st); GP.closeSheet(); if (S().route === target) GP.render(false); else GP.go(target, { force: true }); };
  GP.act['stale-revert'] = target => {
    const st = P.stale(); if (st && st.back) P.revertStale(st);
    GP.closeSheet(); GP.toast('원래대로 되돌렸어요');
    if (!target || S().route === target) GP.render(false); else GP.go(target, { force: true });
  };
  /* 입력 화면 안내: 바꾼 내용이 있으면 미리 알려 주고 바로 되돌릴 수 있게 한다(입력 중에 보이도록 onRefresh 가 켜고 끔) */
  const staleNote = kind => `<p class="note stale-note" data-stale="${kind}" hidden>${icon('info')}<span>${{ quiz: '목표·기획서를 바꿨어요. 다음으로 넘어갈 때 사전 점검 문항부터 다시 만들지 확인해요.', diag: '응답을 바꿨어요. 다음으로 넘어갈 때 점검 결과부터 다시 만들지 확인해요.', gen: '세부 사항을 바꿨어요. 다음으로 넘어갈 때 로드맵 3안을 다시 만들지 확인해요.' }[kind]}
    <button type="button" class="link" data-act="stale-revert" data-arg="">원래대로 되돌리기</button></span></p>`;

  GP.onBindChange = path => {
    const d = S().draft;
    /* 결과는 지우지 않는다(위 '앞 단계를 고쳤을 때'). 세부 사항을 바꾸면 확인 화면을 다시 거치게만 한다 */
    if (path.startsWith('draft.prefs.')) d.detailsOk = false;
    if (d.quizFail && d.quizFail.key !== P.quizKey(d)) d.quizFail = null;
  };
  GP.onRefresh = () => {
    const c = document.getElementById('qCount'), d = S().draft;
    if (c && d.quiz) c.textContent = `${d.quiz.questions.filter(q => d.answers[q.id]).length} / ${d.quiz.questions.length}`;
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
    document.querySelectorAll('[data-stale]').forEach(el => { el.hidden = !st || st.kind !== el.dataset.stale; const b = el.querySelector('[data-act="stale-revert"]'); if (b) b.hidden = !(st && st.back); });
  };

  /* 1. 목표·기획서 */
  P.goalField = () => `<textarea class="textarea" data-bind="draft.goal" maxlength="300" aria-label="키우고 싶은 역량" placeholder="예: 사내 규정 문서로 질의응답 시제품을 만들고 싶어요.">${esc(S().draft.goal)}</textarea>${P.goalSug()}`;

  /* 목표 후보 (4차 묶음 7 · FR-05): 목표를 적기 전에 진단 에이전트가 사용자 프로필만 보고 후보 3개를 제안한다.
     프로필이 같으면 한 번 만든 후보를 그대로 둔다(적은 목표·기획서를 보지 않아 나중 입력에 따라 바뀌지 않음).
     본인 입력이 없어 근거가 부족하면 에이전트를 부르지 않고 AI 활용 업무 기본 후보 3개. 실패하면 '다시 시도'를 눌러야만 다시 받는다 */
  const hashStr = t => { let h = 5381; for (let i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) | 0; return (h >>> 0).toString(36); };
  const gsKey = () => { const e = AI.profileOf(); return `${e.id}|${AI.mode()}|${hashStr(JSON.stringify(AI.goalInput(e).profile))}`; };
  let gsTok = 0, gsBusy = false;
  const gsPaint = () => { const b = document.getElementById('goalSug'); if (b) b.outerHTML = P.goalSug(); };
  async function startGoalSug(avoid) {
    const e = AI.profileOf(), key = gsKey(), tok = ++gsTok, inp = AI.goalInput(e);
    const who = [e.name, e.dept, e.grade].filter(Boolean).join(' · ');
    if (!AI.profileEnough(e)) {
      gsBusy = false;
      S().goalSug = { key, status: 'default', items: D.goalDefaults.map(x => ({ goal: x.goal, why: x.why, basis: [] })), used: inp.used, who, source: 'default', avoid: [] };
      GP.save(); gsPaint(); return;
    }
    S().goalSug = { key, status: 'run', items: [], used: inp.used, who, avoid: avoid || [] }; GP.save(); gsPaint();
    gsBusy = true;
    const sim = AI.simOnce('goal', key + '|' + (avoid || []).join('|'));
    if (!AI.live() || sim) await sleep(sim ? 900 : 500);
    let out = null, err = null;
    try { out = await AI.goalCandidates(Object.assign({}, inp, { avoid: avoid || [] }), { simFail: sim }); } catch (x) { err = x; }
    if (tok !== gsTok) return;
    gsBusy = false;
    const g = S().goalSug; if (!g || g.key !== key) return;
    if (err) Object.assign(g, { status: 'fail', cause: AI.cause(err) });
    else Object.assign(g, { status: 'ok', items: out.candidates, note: out.note, source: AI.mode() });
    GP.save(); gsPaint();
  }
  P.goalSug = () => {
    const g = S().goalSug, run = !g || g.status === 'run';
    const tag = !g || run ? '' : g.status === 'default' ? '' : g.source === 'mock' ? '<span class="tag">가데이터</span>' : g.status === 'ok' ? `<span class="tag acc">${AI.PROV[g.source] || 'API'} 작성</span>` : '';
    let body = '';
    if (run) body = `<div class="agents">${P.agentRow({ st: 'run', name: '진단 에이전트 · 목표 후보 제안', sub: '내 프로필(직급·직무·담당 업무·본인 입력)만 보고 있어요' })}</div>`;
    else if (g.status === 'fail') body = `<div class="gs-fail">${icon('alert')}<div class="grow"><b>목표 후보를 받지 못했어요</b><p class="small">${esc(P.errText(g.cause))}</p>${P.opsBox([['', g.cause]], 'sm')}</div><button type="button" class="btn line sm" data-act="goal-retry">${icon('retry')}다시 시도</button></div>`;
    else body = `<div class="gs-list">${g.items.map((c, i) => `<button type="button" class="gs-it" data-act="goal-pick" data-arg="${i}"><b>${esc(c.goal)}</b><small>${esc(c.why)}</small></button>`).join('')}</div>
      ${g.status === 'default' ? P.note(`프로필에 본인 입력 정보(업무 설명·경험 요약·기술 스택)가 없어 판단 근거가 부족해요. AI 활용 업무 기본 후보를 보여 드려요. 프로필을 채우면 맞춤 후보를 받을 수 있어요. <button class="link" data-go="me">${icon('user')}내 정보에서 채우기</button>`) : g.note ? `<p class="small muted gs-note">${icon('info')}${esc(g.note)}</p>` : ''}`;
    const used = g && g.used ? `참고한 정보 · ${esc(g.used.join(', '))}${g.who ? ` (${esc(g.who)})` : ''}` : '';
    return `<div class="gsug" id="goalSug"><div class="gs-h"><b>${icon('spark')}목표 후보</b><span class="small muted">${g && g.status === 'default' ? 'AI 활용 업무 기본 후보' : '진단 에이전트가 내 프로필로 제안해요'}</span>${tag}</div>${body}
      <p class="small muted gs-f">${used}${used ? ' · ' : ''}적은 목표와 기획서는 보지 않아요. <button class="link quiet" data-go="me">내 정보 보기</button>${g && g.status === 'ok' ? ` <button type="button" class="link" data-act="goal-more">다른 후보 받기</button>` : ''}</p></div>`;
  };
  GP.act['goal-pick'] = i => {
    const g = S().goalSug, c = g && g.items[+i]; if (!c) return;
    S().draft.goal = c.goal; GP.onBindChange('draft.goal'); GP.save();
    const t = document.querySelector('[data-bind="draft.goal"]'); if (t) { t.value = c.goal; t.focus(); }
    GP.refresh(); GP.toast('목표 칸에 넣었어요. 내 말로 고쳐 써도 돼요');
  };
  GP.act['goal-retry'] = () => { const g = S().goalSug; startGoalSug(g ? g.avoid : []); };
  GP.act['goal-more'] = () => { const g = S().goalSug; if (!g || g.status !== 'ok') return; startGoalSug((g.avoid || []).concat(g.items.map(c => c.goal)).slice(-9)); };

  /* 기획서 읽기 (10/14): 글자 꺼내기(server.py) → 이미지 보기(비전 모델이 있을 때) → 요약(진단 에이전트).
     요약은 화면에서 고칠 수 있고, 요약만 문항·진단·로드맵 에이전트에게 넘긴다. 실패하면 '다시 시도'를 눌러야만 다시 읽는다.
     이미지 내용(base64)은 브라우저 저장소에 넣지 않고 이 화면이 열려 있는 동안만 갖고 있는다 */
  let docTok = 0, docActive = false, docImages = [], docFile = null;
  const DOC_STEP = { extract: '파일에서 글자와 이미지를 꺼내고 있어요', vision: '기획서 이미지를 보고 있어요', summary: '기획서를 요약하고 있어요' };
  async function readProject(file, from) {
    const d = S().draft, tok = ++docTok;
    docActive = true; docFile = file;
    const doc = d.doc = Object.assign(from && d.doc ? d.doc : { name: file.name }, { status: 'reading', fail: null });
    const stop = () => tok !== docTok || S().draft !== d;
    const failAt = (step, err) => { if (stop()) return; docActive = false; Object.assign(doc, { status: 'fail', step, fail: { cause: AI.cause(err) } }); GP.save(); if (S().route === 'new-goal') GP.render(false); };
    const show = step => { doc.step = step; GP.save(); if (S().route === 'new-goal') GP.render(false); };
    if (!from || from === 'extract') {
      show('extract');
      let ex;
      try { ex = await AI.docRead(file); } catch (err) { return failAt('extract', err); }
      if (stop()) return;
      docImages = ex.images || [];
      Object.assign(doc, { format: ex.format, chars: ex.chars, truncated: ex.truncated, pages: ex.pages || null, text: ex.text || '', imageTotal: ex.imageTotal || 0, imageSkipped: ex.imageSkipped || {}, imagePicked: docImages.length, warnings: ex.warnings || [], imageNotes: [], imagesRead: 0, visionWhy: '' });
      from = 'vision';
    }
    if (from === 'vision') {
      /* 비전 모델이 있으면 큰 이미지 최대 4장을 본다. 없으면 이유만 남긴다 */
      if (docImages.length && AI.live() && AI.visionModel()) {
        show('vision');
        const sim = AI.simOnce('doc', 'vision|' + file.name);
        if (sim) await sleep(900);
        try { const v = await AI.docVision({ name: file.name, images: docImages }, { simFail: sim }); doc.imageNotes = v.images; doc.imagesRead = v.images.length; } catch (err) { return failAt('vision', err); }
        if (stop()) return;
      } else doc.visionWhy = !doc.imageTotal ? '' : !AI.live() ? 'mock' : !docImages.length ? 'none' : 'novision';
      from = 'summary';
    }
    if (!doc.text && !(doc.imageNotes || []).length) { docActive = false; Object.assign(doc, { status: 'ok', summary: '', step: 'done' }); GP.save(); if (S().route === 'new-goal') GP.render(false); return; }
    show('summary');
    const sim = AI.simOnce('doc', 'summary|' + file.name + '|' + (doc.chars || 0));
    if (!AI.live() || sim) await sleep(sim ? 900 : 600);
    let s;
    try { s = await AI.docSummary({ goal: d.goal, name: doc.name, text: doc.text, imageNotes: (doc.imageNotes || []).map(x => `${x.n}번 이미지: ${x.desc}`) }, { simFail: sim }); } catch (err) { return failAt('summary', err); }
    if (stop()) return;
    docActive = false;
    Object.assign(doc, { status: 'ok', step: 'done', summary: s.text, source: AI.mode() });
    GP.save(); if (S().route === 'new-goal') GP.render(false);
  }
  GP.onFile = (path, f) => { if (path === 'draft.project') { if (f) readProject(f); else { S().draft.doc = null; docImages = []; docFile = null; docTok++; } } };
  GP.valid.docIdle = () => { const doc = S().draft.doc; return !doc || doc.status !== 'reading' || !docActive; };
  /* 다시 시도: 글자 꺼내기·이미지 보기는 파일이 필요하다(새로 고치면 파일을 다시 골라야 함). 요약은 꺼낸 글자로 다시 한다 */
  GP.act['doc-retry'] = () => {
    const d = S().draft, doc = d.doc; if (!doc || docActive) return;
    const step = doc.status === 'reading' ? doc.step : (doc.step || 'extract');
    if (step === 'summary' || (step === 'vision' && !docFile)) { if (step === 'vision') doc.visionWhy = 'lost'; readProject(docFile || { name: doc.name }, 'summary'); return; }
    if (!docFile) { GP.toast('파일을 다시 골라 주세요'); return; }
    readProject(docFile, step === 'vision' ? 'vision' : 'extract');
  };
  GP.act['doc-skip-images'] = () => { const doc = S().draft.doc; if (!doc || docActive) return; doc.visionWhy = 'skip'; readProject(docFile || { name: doc.name }, 'summary'); };
  const kb = n => `${Math.max(1, Math.round(n / 1024))}KB`;
  /* 이미지 안내: 읽은 이미지 / 읽지 않은 이유 (비전 모델 없음·가데이터·작은 아이콘 등) */
  function imageLine(doc) {
    const sk = doc.imageSkipped || {}, other = (sk.small || 0) + (sk.big || 0) + (sk.format || 0) + (sk.more || 0);
    if (!doc.imageTotal) return '';
    const why = [sk.small && `작은 아이콘 ${sk.small}`, sk.big && `1.5MB가 넘는 이미지 ${sk.big}`, sk.format && `EMF·WMF 같은 형식 ${sk.format}`, sk.more && `4장을 넘는 이미지 ${sk.more}`].filter(Boolean).join(', ');
    if (doc.imagesRead) return `이미지 ${doc.imagesRead}장을 비전 모델이 보고 요약에 합쳤어요.${other ? ` 그 밖의 ${other}개(${why})는 보지 않았어요.` : ''}`;
    const base = { mock: '가데이터 모드라 이미지는 보지 않았어요.', novision: '이미지를 볼 수 있는 AI 모델이 설정되지 않아 이미지는 보지 않았어요.', skip: '이미지는 건너뛰고 글자만 요약했어요.', lost: '화면을 새로 고쳐 이미지는 보지 못했어요. 이미지까지 보려면 파일을 다시 골라 주세요.', none: '읽을 수 있는 크기·형식의 이미지가 없어 보지 않았어요.' }[doc.visionWhy] || '이미지는 보지 않았어요.';
    return `이미지 ${doc.imageTotal}개 · ${base}${doc.visionWhy === 'none' && why ? ` (${why})` : ''} 그림·도표의 중요한 내용은 요약에 직접 적어 주세요.`;
  }
  P.docBox = function () {
    const d = S().draft, doc = d.doc; if (!doc) return '';
    const live = doc.status === 'reading' && docActive;
    if (live) return `<div class="docbox"><div class="agents">${P.agentRow({ st: 'run', name: '진단 에이전트 · 기획서 읽기', sub: P.runSub(doc.step === 'vision' ? 'vision' : 'default', DOC_STEP[doc.step] || DOC_STEP.extract) })}</div></div>`;
    if (doc.status === 'reading' || doc.status === 'fail') {
      const c = doc.fail ? doc.fail.cause : { kind: 'other', user: '화면을 새로 고쳐 기획서 읽기가 멈췄어요', text: '읽는 도중 화면을 새로 고침', hint: '다시 시도하거나 파일을 다시 골라 주세요' };
      const docKind = /^doc/.test(c.kind), visionFail = doc.step === 'vision', needFile = !docFile && doc.step !== 'summary';
      return `<div class="docbox fail"><p class="db-h">${icon('alert')}<b>${visionFail ? '기획서 이미지를 보지 못했어요' : doc.step === 'summary' ? '기획서를 요약하지 못했어요' : '기획서를 읽지 못했어요'}</b></p>
        <p class="small">${doc.fail ? esc(P.errText(c)) : '화면을 새로 고쳐 기획서 읽기가 멈췄어요. 아래에서 이어서 진행해 주세요.'}</p>${doc.fail ? P.opsBox([['', c]], 'sm') : ''}
        <div class="db-act">${docKind ? `<button type="button" class="btn line sm" data-act="clear-project">${icon('file')}다른 파일 고르기</button>` : needFile ? `<button type="button" class="btn line sm" data-act="clear-project">${icon('file')}파일 다시 고르기</button>` : `<button type="button" class="btn line sm" data-act="doc-retry">${icon('retry')}다시 시도</button>`}${visionFail ? `<button type="button" class="btn line sm" data-act="doc-skip-images">이미지 없이 요약</button>` : ''}${docKind ? '' : '<span class="small muted">기획서 없이 목표만으로 진행해도 돼요.</span>'}</div></div>`;
    }
    const meta = [doc.format, doc.pages ? `${doc.pages}쪽` : '', `글자 ${(doc.chars || 0).toLocaleString('ko-KR')}자`, doc.chars > AI.DOC_CHARS ? `앞 ${AI.DOC_CHARS.toLocaleString('ko-KR')}자로 요약` : ''].filter(Boolean).join(' · ');
    const src = doc.source && doc.source !== 'mock' ? `${AI.PROV[doc.source]} 요약` : '가데이터 요약';
    const warn = (doc.warnings || []).map(w => `<p class="small warn-t">${icon('info')}${esc(w)}</p>`).join('');
    return `<div class="docbox"><div class="db-top"><p class="eyebrow">${icon('spark')}기획서 요약 · 진단 에이전트</p><span class="tag ${doc.source && doc.source !== 'mock' ? 'acc' : ''}">${src}</span></div>
      <p class="small muted db-meta">${esc(meta)}</p>${warn}
      ${doc.summary || doc.text ? `<textarea class="textarea sm" data-bind="draft.doc.summary" maxlength="1500" aria-label="기획서 요약" rows="6">${esc(doc.summary)}</textarea>
      <p class="small muted">틀리거나 빠진 내용은 직접 고쳐 주세요. 이 요약만 사전 점검·진단·로드맵 에이전트에게 넘어가요.</p>` : '<p class="small muted">요약할 글자를 찾지 못했어요. 기획서 없이 목표만으로 진행해요.</p>'}
      ${imageLine(doc) ? `<p class="small db-img">${icon('file')}${esc(imageLine(doc))}</p>${doc.visionWhy === 'novision' ? P.opsBox([['', { text: '비전 모델 설정 없음', hint: '.env에 OLLAMA_VISION_MODEL(RunPod-Ollama) 또는 OPENAI_VISION_MODEL(OpenAI API)을 넣고 server.py를 다시 실행하면 이미지도 읽어요' }]], 'sm') : ''}` : ''}</div>`;
  };
  P.projectField = function () {
    const f = S().draft.project;
    return f ? `<div class="file-on">${icon('file')}<div class="tx"><b>${esc(f.name)}</b><small class="muted">${kb(f.size)}</small></div><button class="link quiet" data-act="clear-project">빼기</button></div>${P.docBox()}`
      : `<label class="drop"><input type="file" data-bind-file="draft.project" accept=".pdf,.docx,.hwp,.hwpx,.pptx,.txt,.md"><span class="ico">${icon('file')}</span><span><b>기획서 파일 고르기</b><small>PDF, 한글(HWP·HWPX), 워드(DOCX), 파워포인트(PPTX), TXT · 15MB까지 · 선택</small></span></label>`;
  };
  GP.act['clear-project'] = () => { const d = S().draft; d.project = null; d.doc = null; docImages = []; docFile = null; docTok++; docActive = false; GP.onBindChange('draft.project'); GP.save(); GP.render(false); };
  scr['new-goal'] = {
    nav: 'new', newStep: true, title: '새 로드맵 작성', width: 'wide',
    render: () => GP.stepper('goal') + P.page({
      title: '어떤 역량을 키우고 싶나요?', lead: '목표와, 적용할 프로젝트 기획서가 있으면 함께 알려 주세요. 기획서는 진단 에이전트가 읽고 요약해요. 학습 여건은 다음 단계에서 적어 주세요(모두 선택).',
      body: `<div class="card"><div class="field"><label>키우고 싶은 역량</label>${P.goalField()}</div><hr class="hr">
        <div class="field"><label>적용할 프로젝트 기획서 <span class="muted small">선택</span></label>${P.projectField()}</div></div>
        ${staleNote('quiz')}`,
      foot: `<button class="btn pri" data-go="new-details" data-need="goal,docIdle">다음: 세부 사항</button>`
    }),
    /* 목표 후보: 프로필(또는 모드)이 바뀌었으면 새로 받고, 새로 고침으로 끊긴 요청은 다시 보낸다(실패는 '다시 시도'를 눌러야만) */
    after() { const g = S().goalSug; if (!g || g.key !== gsKey()) startGoalSug(); else if (g.status === 'run' && !gsBusy) startGoalSug(g.avoid); }
  };

  /* 2. 세부 사항: 학습 선호 5가지 + 기타 고려 사항을 입력 폼으로 받는다(10/13: 대화 대신 폼).
     모두 선택 사항이고, 비워 둔 칸은 흐린 회색 기본값으로 둔다: 자격증 계획은 '계획 없음', 나머지는 '알아서'(진단·로드맵 계획 에이전트가 정함).
     같은 폼을 점검 결과 수정 화면에서도 쓴다(path 만 다름) */
  const fieldLabel = k => (D.detailFields.find(f => f[0] === k) || [])[1] || '';

  /* 자격증 계획 드롭다운: 분야 → 자격 2단계. 분야를 누르면 같은 창이 그 분야의 자격 목록으로 바뀌고 '‹ 분야'로 돌아온다.
     (PC·모바일 같은 모양 · 키보드 ↑↓ 이동, → 들어가기, ← 돌아가기, Esc 닫기) */
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
        return `${head}<button type="button" class="cp-it${c.id === v ? ' on' : ''}" data-act="cp-pick" data-arg="${c.id}">${mark(c.id === v)}<span class="cp-tx">${esc(c.short)}${meta ? `<small>${esc(meta)}</small>` : ''}</span></button>`;
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
      lead: '모두 선택 사항이에요. 비워 둔 칸은 ‘알아서’로 두고 진단 에이전트와 로드맵 계획 에이전트가 목표에 맞게 정해요. 자격증 계획은 고르지 않으면 ‘계획 없음’이에요.',
      body: `<div class="card">${P.detailsForm('draft.prefs')}</div>${staleNote('gen')}${S().draft.quiz ? P.note('사전 점검 문항은 이미 만들었어요. 여기서 바꾼 내용은 로드맵을 만들 때 반영해요.') : ''}`,
      foot: `<button class="btn line" data-go="new-goal">${icon('left')}이전</button><button class="btn pri" data-go="new-details-check">다음: 입력 내용 확인</button>`
    })
  };

  /* 2-1. 세부 사항 확인: 입력한 내용(빈 칸은 '알아서')과 진단 에이전트 연결 상태를 보여 주고, '다음'을 누르면 사전 점검 문항을 만든다 */
  P.detailsView = p => `<div class="card acc preview">
      <p class="eyebrow">${icon('spark')}진단 에이전트에게 넘길 세부 사항</p>
      <dl class="kv">${D.detailFields.map(([k, l]) => `<dt>${l}</dt><dd class="${AI.prefAuto(k, p) ? 'auto' : ''}${k === 'etc' ? ' etc' : ''}">${esc(AI.prefText(k, p))}</dd>`).join('')}</dl></div>`;
  /* 진단 에이전트 연결 상태: 가데이터 / 확인 중 / 연결됨 / 모델 대기 중(Ollama · 모델이 아직 GPU에 없음) / 연결 안 됨.
     좌측 'AI 모델'에서 고른 모드(RunPod-Ollama·OpenAI API)를 server.py 가 확인하고(/api/ping), 이후 호출 결과로 갱신 */
  const via = role => `${AI.PROV[AI.mode()]} · ${esc(AI.modelName(role))}`;
  P.connView = function () {
    if (!AI.live()) return `<span class="conn off"><i></i>${AI.demoMock() ? '가데이터 모드 · LLM에 연결하지 않아요' : `${AI.PROV[AI.choice()]}를 쓸 수 없어 가데이터로 만들어요`}</span>`;
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
          : '‘다음’을 누르면 진단 에이전트가 목표와 아래 내용으로 사전 점검 문항을 만들어요. ‘알아서’인 항목은 에이전트가 목표에 맞게 정해요.',
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
  P.quizBody = (questions, path, preMap) => {
    const areas = [...new Set(questions.map(q => q.area))];
    return areas.map(a => `<div class="card qcard"><h2 class="st">${esc(a)}</h2>${questions.filter(q => q.area === a).map(q => P.likRow(q, path, preMap && preMap[q.id])).join('')}</div>`).join('');
  };
  /* 생성 실패 안내 (사전 점검 문항 · 점검 결과 · 로드맵 3안 · 결과 보고서 공통)
     빨간 안내 → 오류 원인(쉬운 말과 할 일) → 에이전트별 상태 → 자세히 보기(운영자용, 접힘) → 버튼. 다시 시도는 버튼을 눌러야만 한다
     10/14: 아래 '사내 생활 도우미에게 문의하기' 링크는 없앴다(도우미도 같은 모델을 써서 함께 실패하고, 오류 내용도 넘겨받지 못하는 막다른 길) */
  P.failPage = o => `<section class="fail-card" role="alert"><span class="ico">${icon('alert')}</span><div><h1>${o.title}</h1><p>${o.desc}</p></div></section>
    <div class="cause">${icon('info')}<p><b>오류 원인 안내:</b> ${o.cause}</p></div>
    ${o.body || ''}${o.ops || ''}<div class="actions">${o.foot}</div>${o.hint ? `<p class="small muted fail-hint">${o.hint}</p>` : ''}`;
  /* 에이전트 진행 줄: run 작성 중(회전) / ok 완료(체크) / fail 실패(빨간 X · 원인 · 다시 시도) */
  P.agentRow = o => `<div class="agent ${o.st}${o.warn ? ' warn' : ''}"><span class="sp">${o.st === 'ok' ? icon('check') : o.st === 'fail' ? icon('x') : ''}</span>
    <div class="ag-tx"><b>${o.name}</b>${o.st === 'fail' ? `<span class="fl">${o.failLabel || '생성 실패'}</span>` : ''}${o.sub ? `<small>${o.sub}</small>` : ''}</div>
    ${o.tag ? `<span class="tag ${o.tagCls || ''}">${o.tag}</span>` : ''}${o.retry ? `<button class="btn line sm" data-act="${o.retry[0]}" data-arg="${o.retry[1]}">${icon('retry')}다시 시도</button>` : ''}
    ${o.st === 'fail' && o.detail ? `<div class="detail">${o.detail}</div>` : ''}</div>`;

  /* 문항 생성: 오류를 가데이터로 대신하지 않고 실패 화면을 보여 준다.
     실패는 draft.quizFail 에 저장해 새로 고쳐도 다시 돌지 않고, '다시 시도하기'를 눌러야만 다시 만든다(10/14) */
  let quizBusy = false, quizRetry = false;
  /* '원래대로 되돌리기'에 쓰려고 문항을 만들 때의 목표·기획서를 같이 둔다(이미지 내용은 빼고) */
  const quizBase = d => ({ goal: d.goal, project: d.project ? clone(d.project) : null, doc: d.doc && d.doc.status === 'ok' ? clone(d.doc) : null });
  async function ensureQuiz() {
    const d = S().draft, key = P.quizKey(d);
    if ((d.quiz && d.quiz.key === key) || quizBusy || (d.quizFail && d.quizFail.key === key)) return;
    quizBusy = true;
    const sim = AI.simOnce('quiz', key);
    if (!AI.live() || sim) await sleep(sim ? 1400 : 500);
    let r = null, err = null;
    try { r = await AI.diagQuestions({ goal: d.goal, project: d.project ? d.project.name : null, projectSummary: P.docSummary(d) || null, prefs: JSON.parse(JSON.stringify(d.prefs)) }, { simFail: sim }); } catch (e) { err = e; }
    quizBusy = false; quizRetry = false;
    if (S().draft !== d) return;
    if (err) d.quizFail = { key, cause: AI.cause(err) };
    else { clearFrom('quiz'); d.quiz = { key, questions: r.questions, domain: r.domain, base: quizBase(d) }; }
    GP.save();
    if (S().route === 'new-quiz') GP.render(false);
  }
  GP.act['quiz-retry'] = () => { S().draft.quizFail = null; quizRetry = true; GP.save(); GP.render(false); };
  const QUIZ_AGENT = '진단 에이전트 · 사전 점검 문항 생성';
  /* 생성 중 줄의 설명: 실제 모델이면 모드·모델 이름을, Ollama 모델이 아직 GPU에 없으면 첫 호출이 느리다는 안내를 붙인다 */
  P.runSub = (role, t) => (!AI.live() ? `${t}…` : AI.connFor(role).state === 'cold' ? `AI 모델을 준비하는 중이에요. 첫 생성은 1~2분 걸릴 수 있어요 · ${via(role)}` : `${t} · ${via(role)}`);
  scr['new-quiz'] = {
    nav: 'new', newStep: true, title: '사전 점검', width: 'wide', guard: () => blockedTo('quiz'),
    render() {
      const d = S().draft, ready = d.quiz && d.quiz.key === P.quizKey(d), err = !ready && !quizBusy && d.quizFail && d.quizFail.key === P.quizKey(d) ? d.quizFail.cause : null;
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
        body: ready ? `<p class="small muted" style="margin:-14px 0 16px">답한 문항 <b id="qCount" class="num"></b></p><div class="stack">${P.quizBody(d.quiz.questions, 'draft.answers')}</div>${staleNote('diag')}`
          : `<div class="agents">${P.agentRow({ st: 'run', name: QUIZ_AGENT, sub: P.runSub('default', quizRetry ? '다시 시도하는 중이에요' : '목표와 세부 사항을 바탕으로 문항을 만들고 있어요') })}</div>`,
        foot: `<button class="btn line" data-go="new-details-check">${icon('left')}이전</button>${P.next('new-result', '다음: 점검 결과', 'quizDone')}`
      });
    },
    after: () => { ensureQuiz(); }
  };

  /* 4. 점검 결과: 진단 에이전트가 정리한 로드맵 미리보기 + 학습 선호 (보기 전용 · 고치려면 '수정') */
  /* 수준 진단도 가데이터로 대신하지 않는다. 실패는 draft.diagFail 에 저장하고 '다시 시도하기'를 눌러야만 다시 진단한다(10/14) */
  let diagBusy = false, diagRetry = false;
  async function ensureDiag() {
    const d = S().draft, key = P.diagKey(d);
    if ((d.diag && d.diag.key === key) || diagBusy || (d.diagFail && d.diagFail.key === key)) return;
    diagBusy = true;
    const sim = AI.simOnce('diag', key);
    if (!AI.live() || sim) await sleep(sim ? 1200 : 500);
    let r = null, err = null;
    try { r = await AI.diagAssess({ goal: d.goal, project: d.project ? d.project.name : null, projectSummary: P.docSummary(d) || null, prefs: JSON.parse(JSON.stringify(d.prefs)), questions: d.quiz.questions, answers: d.answers }, { simFail: sim }); } catch (e) { err = e; }
    diagBusy = false; diagRetry = false;
    if (S().draft !== d) return;
    if (err) d.diagFail = { key, cause: AI.cause(err) };
    else { d.diagFail = null; d.diag = Object.assign({ key, answers: clone(d.answers) }, r); }
    GP.save();
    if (S().route === 'new-result') GP.render(false);
  }
  GP.act['diag-retry'] = () => { S().draft.diagFail = null; diagRetry = true; GP.save(); GP.render(false); };
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
        ${dt('resourceIds', '듣게 될 강좌·자료')}<dd><ul class="plain-list">${res.map(id => { const r = D.res[id]; return `<li><b>${esc(r.title)}</b> <span class="small muted">${r.kind} · ${esc(r.provider)}${r.real ? '' : ' · 가상'}</span></li>`; }).join('') || '<li class="muted">로드맵 계획 에이전트가 등록 자료에서 고를 예정이에요</li>'}</ul></dd>
        ${dt('outcome', '만들 결과물')}<dd>${esc(P.dv(d, 'outcome'))}</dd>
        ${known.length || P.edited(d, 'known') ? `${dt('known', '이미 할 수 있는 것')}<dd class="small muted">${esc(known.slice(0, 6).join(', ') || '없음')}${known.length ? ' — 다시 배우지 않도록 줄여요' : ''}</dd>` : ''}
      </dl></div>`;
  };
  scr['new-result'] = {
    nav: 'new', newStep: true, title: '점검 결과', width: 'wide', guard: () => blockedTo('result'),
    render() {
      const d = S().draft, key = P.diagKey(d), ready = d.diag && d.diag.key === key, err = !ready && !diagBusy && d.diagFail && d.diagFail.key === key ? d.diagFail.cause : null;
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
        body: ready ? `${P.preview()}${P.note('목표·기획서나 사전 점검 응답을 고치려면 위 단계를 눌러 이동하세요. ‘로드맵 생성’을 누를 때 지금 내용이 로드맵 계획 에이전트에게 전달돼요.')}`
          : `<div class="agents">${P.agentRow({ st: 'run', name: DIAG_AGENT, sub: P.runSub('default', diagRetry ? '다시 시도하는 중이에요' : '사전 점검 응답과 세부 사항을 정리하고 있어요') })}</div>`,
        foot: `<button class="btn line" data-go="new-quiz">${icon('left')}이전</button><button class="btn line" data-act="result-edit" ${ready ? '' : 'disabled'}>${icon('edit')}수정</button><button class="btn pri" data-act="gen-start" ${ready ? '' : 'disabled'}>로드맵 생성</button>`
      });
    },
    after: () => { ensureDiag(); }
  };
  GP.act['gen-start'] = () => {
    /* 바꾼 앞 단계가 남아 있으면(홈에서 이어서 들어온 경우 등) 먼저 확인 */
    const st = P.stale(); if (st) { GP.sheet(staleText(st), { title: '바꾼 내용으로 계속할까요?', foot: staleBtns(st, 'new-result') }); return; }
    const d = S().draft, h = P.buildHandoff();
    /* 같은 내용으로 세 안을 모두 받은 적이 있으면 그 결과를 쓰고, 일부만 받았거나 내용이 바뀌었으면 새로 만든다 */
    if (!d.gen || d.gen.key !== P.genKey(h) || (d.gen.missing || []).length) { d.gen = null; d.chosen = null; S().draftPlan = null; d.genRun = null; }
    d.handoff = h; d.genPrefs = clone(d.prefs); GP.save(); GP.go(d.gen ? 'new-options' : 'new-gen');
  };

  /* 4-1. 점검 결과 수정: 점검 결과 화면에 보이는 내용을 한곳에서 고친다. 저장해야 반영되고, 취소하면 그대로 */
  const cloneJ = o => JSON.parse(JSON.stringify(o));
  const sameSet = (x, y) => JSON.stringify((x || []).slice().sort()) === JSON.stringify((y || []).slice().sort());
  const editFrom = d => ({ start: P.startOf(d), competencies: P.dv(d, 'competencies').slice(), resourceIds: P.dv(d, 'resourceIds').slice(), outcome: P.dv(d, 'outcome'), known: P.dv(d, 'known').slice(), prefs: cloneJ(d.prefs) });
  /* 학습 선호(세부 사항)는 모두 선택 사항이라 빈 칸 검사는 로드맵 내용에만 */
  P.editMissing = e => ({ competencies: !e.competencies.length, outcome: !String(e.outcome || '').trim() });
  const missTip = (k, t) => `<span class="miss" data-miss="${k}" ${P.editMissing(S().draft.edit)[k] ? '' : 'hidden'}>${icon('info')}${t}</span>`;
  const radios = (path, opts, cur, rer) => `<div class="chips">${opts.map(([v, l]) => `<label class="chip"><input type="radio" name="${path}" value="${esc(v)}" data-bind="${path}" ${rer ? 'data-rerender' : ''} ${String(cur) === String(v) ? 'checked' : ''}>${esc(l)}</label>`).join('')}</div>`;
  const editArr = (e, k) => e[k];
  const listEdit = (k, ph) => {
    const arr = editArr(S().draft.edit, k);
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
    const resList = Object.entries(D.res).filter(([, r]) => r.kind !== '자격' && (r.stage || 1) >= start);
    return `<div class="card"><h2 class="st">로드맵 내용 <span class="small muted">진단 에이전트가 정리</span></h2><div class="efs">
        ${ef('시작 지점', `${radios('draft.edit.start', D.stages.map(s => [s.n, `${s.n}단계 ${s.name}`]), start, true)}<p class="small muted ef-n">진단 에이전트 제안: ${stageLabel(a.startStage)} · ${esc(a.startReason)} ${sugBack('start')}</p>`)}
        ${ef('익히게 될 역량', `${listEdit('competencies', '예: 답변 근거 표시하기')}${missTip('competencies', '역량을 하나 이상 넣어 주세요')}${sugBack('competencies')}`)}
        ${ef('듣게 될 강좌·자료', `<div class="choices">${resList.map(([id, r]) => `<label class="choice"><input type="checkbox" value="${id}" data-bind-arr="draft.edit.resourceIds" ${e.resourceIds.includes(id) ? 'checked' : ''}><span class="tx">${esc(r.title)}<small>${r.stage}단계 · ${r.kind} · ${esc(r.provider)} · ${hrs(r.hours)} · ${r.cost ? won(r.cost) : '무료'}${r.real ? '' : ' · 가상'}</small></span><span class="ck">${icon('check')}</span></label>`).join('')}</div><p class="small muted ef-n">등록된 자료 중 시작 지점 이후 단계만 보여요. 자격증은 아래 학습 선호에서 정해요. ${sugBack('resourceIds')}</p>`)}
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
    const arr = editArr(e, k); if (!arr.includes(v)) arr.push(v);
    GP.save(); GP.render(false); const n = document.getElementById('add-' + k); if (n) n.focus();
  };
  GP.act['edit-del'] = arg => { const [k, i] = arg.split(':'); editArr(S().draft.edit, k).splice(+i, 1); GP.save(); GP.render(false); };
  GP.act['edit-reset'] = k => { const d = S().draft, e = d.edit, a = d.diag; if (k === 'start') e.start = a.startStage; else e[k] = cloneJ(a[k]); GP.save(); GP.render(false); };
  GP.act['edit-cancel'] = () => { S().draft.edit = null; GP.save(); GP.go('new-result'); };
  /* 저장할 값: 진단 제안과 다른 항목만 fix 에 둔다 */
  const editNext = d => {
    const e = d.edit, a = d.diag, start = +e.start;
    const val = { competencies: e.competencies, resourceIds: e.resourceIds, outcome: String(e.outcome).trim(), known: e.known }, fix = {};
    P.FIX.forEach(([k]) => { if (!(k === 'resourceIds' ? sameSet(val[k], a[k]) : JSON.stringify(val[k]) === JSON.stringify(a[k]))) fix[k] = val[k]; });
    return { startStage: start === a.startStage ? null : start, fix: Object.keys(fix).length ? fix : null, prefs: cloneJ(e.prefs) };
  };
  const editChanged = (d, n) => JSON.stringify([d.startStage || null, d.fix || null, d.prefs]) !== JSON.stringify([n.startStage, n.fix, n.prefs]);
  function editSave() {
    const d = S().draft, n = editNext(d), changed = editChanged(d, n);
    d.startStage = n.startStage; d.fix = n.fix; d.prefs = n.prefs; d.edit = null;
    if (changed && (d.handoff || d.gen)) clearFrom('gen');
    GP.save(); GP.go('new-result'); GP.toast(changed ? '수정한 내용을 저장했어요' : '바뀐 내용이 없어요');
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

  /* 5. 3안 생성 (로드맵 계획 에이전트 · 관점별 병렬)
     하위 에이전트마다 따로 실행하고, API 오류를 가데이터로 대신하지 않는다. 실패한 줄은 빨간 X로 바뀌고
     그 안만 '다시 시도'하거나, '로드맵 확인하기'로 작성된 안만 가지고 다음 단계로 넘어갈 수 있다 */
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
  const GEN_ROWS = () => D.optionOrder;
  let hoOpen = false;
  document.addEventListener('toggle', e => { if (e.target.id === 'hoView') hoOpen = e.target.open; }, true);
  /* 진행 상태는 draft.genRun 에 저장한다(10/14). 새로 고쳐도 작성된 안은 남고, 실패한 안은 '다시 시도'를 눌러야만 다시 쓴다.
     새로 고칠 때 작성 중이던 안은 응답을 받을 수 없으므로, 이 화면에 다시 들어오면 그 안만 처음 요청처럼 다시 보낸다(실패 재시도가 아님).
     지원 조건은 3안이 정해진 뒤 규정 에이전트가 안별로 한 번에 확인한다(아래 ensureSupport) */
  const running = new Set();
  const curGen = d => (d.genRun && d.handoff && d.genRun.key === P.genKey(d.handoff) ? d.genRun : null);
  function startGen(key) {
    S().draft.genRun = { key, rows: Object.fromEntries(GEN_ROWS().map(id => [id, { st: 'run', tries: 0, out: null, err: null }])) };
    GP.save();
    GEN_ROWS().forEach(id => runRow(id));
  }
  async function runRow(id) {
    const d = S().draft, r = d.genRun, row = r.rows[id], h = d.handoff, tag = r.key + '|' + id;
    running.add(tag);
    row.st = 'run'; row.err = null; row.tries++; GP.save();
    const sim = AI.failSim().gen && (id === 'A2' || id === 'A3') && row.tries === 1 ? AI.simError(id) : null;
    if (!AI.live() || sim) await sleep(700 + D.optionOrder.indexOf(id) * 260 + (sim ? 600 : 0));
    try { row.out = await AI.roadmapOption({ pid: id, handoff: h }, { simFail: sim }); row.st = 'ok'; } catch (err) { row.st = 'fail'; row.err = AI.cause(err); }
    running.delete(tag);
    if (S().draft !== d || d.genRun !== r) return;
    GP.save();
    settleGen();
  }
  const genState = r => {
    const ps = D.optionOrder.map(id => r.rows[id]);
    return { running: ps.some(x => x.st === 'run'), ok: ps.filter(x => x.st === 'ok').length, fail: ps.filter(x => x.st === 'fail').length };
  };
  const genOut = r => ({ key: r.key, options: Object.fromEntries(D.optionOrder.filter(id => r.rows[id].st === 'ok').map(id => [id, r.rows[id].out])), missing: D.optionOrder.filter(id => r.rows[id].st !== 'ok') });
  function settleGen() {
    const d = S().draft, r = d.genRun, g = genState(r);
    /* 세 안이 모두 작성되면 바로 저장하고 지원 조건 확인을 시작. 일부만 작성되면 '로드맵 확인하기'를 누를 때 저장 */
    if (!g.running && g.ok === D.optionOrder.length && (!d.gen || d.gen.key !== r.key)) { d.gen = genOut(r); GP.save(); ensureSupport(); }
    if (S().route === 'new-gen') GP.render(false);
  }
  GP.act['gen-retry'] = id => { const r = curGen(S().draft); if (!r || !r.rows[id] || r.rows[id].st !== 'fail') return; runRow(id); GP.render(false); };
  GP.act['gen-partial'] = () => {
    const d = S().draft, r = curGen(d); if (!r) return;
    const g = genState(r); if (g.running || !g.ok) return;
    d.gen = genOut(r); d.chosen = null; S().draftPlan = null; GP.save(); GP.go('new-options'); ensureSupport();
  };

  /* ── 버전: 다시 만든 안은 버전으로 쌓고 ‹ › 로 넘겨 본다. options[관점]은 지금 보고 있는 버전 ── */
  const hist = (g, pid) => {
    g.hist = g.hist || {}; g.cur = g.cur || {};
    if (!g.hist[pid]) { g.hist[pid] = [g.options[pid]]; g.cur[pid] = 0; }
    return g.hist[pid];
  };
  /* 저장소에서 읽은 뒤에는 options 와 hist 가 서로 다른 사본이 되므로, 지금 버전을 다시 가리키게 한다 */
  const syncGen = g => { if (g && g.hist) Object.keys(g.hist).forEach(pid => { if (g.hist[pid][g.cur[pid] || 0]) g.options[pid] = g.hist[pid][g.cur[pid] || 0]; }); };
  const setCur = (g, pid, i) => { hist(g, pid); g.cur[pid] = i; g.options[pid] = g.hist[pid][i]; };

  /* ── 지원 조건 (10/14): 3안이 정해진 뒤 규정 에이전트를 한 번 불러 안별로 확인. 다시 만든 안은 그 안만 확인 ──
     근거는 내 직원 구분의 등록 규정 조항만(일반직 규정 16건 / 실무직 관리규정 · 10/15). 확인 결과(support)·실패(supportFail)는 안(버전)마다 저장하고, 실패하면 '다시 확인'을 눌러야만 다시 묻는다 */
  let supBusy = false;
  const supInput = (pid, o) => {
    const pl = P.buildPlan(o, P.params(o)), paid = [...new Set(pl.acts.filter(a => a.res && D.res[a.res].cost > 0).map(a => a.res))];
    const cert = pl.acts.find(a => a.res && D.res[a.res].kind === '자격');
    return { pid, name: `${pid} ${o.name}`, weeks: pl.weeks, weeklyHours: pl.hours, totalCostWon: pl.cost,
      paidResources: paid.map(id => ({ title: D.res[id].title, provider: D.res[id].provider, costWon: D.res[id].cost, kind: D.res[id].kind })),
      certification: cert ? D.res[cert.res].title : null, onlineOnly: true };
  };
  async function ensureSupport() {
    const d = S().draft, g = d.gen; if (!g || supBusy) return;
    syncGen(g);
    const need = D.optionOrder.filter(pid => g.options[pid] && !g.options[pid].support && !g.options[pid].supportFail);
    if (!need.length) return;
    supBusy = true; supRender();
    const items = need.map(pid => ({ pid, o: g.options[pid] }));
    /* 실패 시연: 이 3안 묶음의 첫 확인만 실패 → '다시 확인'은 성공 */
    const sim = AI.simOnce('sup', g.key);
    if (!AI.live() || sim) await sleep(sim ? 900 : 800);
    let out = null, err = null;
    try { out = await AI.supportCheck({ plans: items.map(x => supInput(x.pid, x.o)) }, { simFail: sim }); } catch (e) { err = e; }
    supBusy = false;
    if (S().draft !== d || d.gen !== g) return;
    items.forEach(x => {
      if (err) x.o.supportFail = { cause: AI.cause(err) };
      else x.o.support = out[x.pid] || { level: 'missing', summary: '이 안은 확인 결과를 받지 못했어요. 담당 부서에 확인해 주세요.', basis: [], missing: [] };
    });
    GP.save(); supRender();
  }
  const supRender = () => { if (['new-gen', 'new-options', 'new-review'].includes(String(S().route).split(':')[0])) GP.render(false); };
  GP.act['sup-retry'] = pid => {
    const g = S().draft.gen; if (!g || supBusy) return; syncGen(g);
    D.optionOrder.filter(id => g.options[id] && (pid === 'all' || id === pid)).forEach(id => { delete g.options[id].supportFail; });
    GP.save(); ensureSupport();
  };
  const SUP_LV = { ok: ['근거 확인', 'acc'], unclear: ['일부만 확인', 'warn'], missing: ['관련 자료 미확보', 'warn'], scope: ['적용 대상 아님', 'warn'] };
  /* 안 하나의 지원 조건: 수준 태그 · 요약 · 근거 조항 · 미등록 규정 (근거 조항이 없으면 '확인 필요'로만 보여 준다) */
  P.supCell = function (o) {
    if (!o) return '';
    if (o.supportFail) return `<span class="tag fail">확인 실패</span> <span class="small muted">${esc(o.supportFail.cause.user || AI.userText(o.supportFail.cause.kind))}. 지원 조건은 ‘확인 필요’로 둬요.</span> <button class="link" data-act="sup-retry" data-arg="${o.id}">${icon('retry')}다시 확인</button>`;
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
    return P.agentRow({ st: 'fail', name, sub: AI.live() ? via('roadmap') : '', failLabel: '생성 실패', tag: '오류 발생', tagCls: 'fail', retry: ['gen-retry', id], detail: esc(row.err.user || AI.userText(row.err.kind)) });
  }
  /* 규정 에이전트 줄: 3안이 정해지기 전에는 기다림, 확인 중, 안별 결과, 실패(다시 시도는 눌러야만) */
  function supRow(d) {
    const name = '규정 에이전트 · 안별 지원 조건 확인', g = d.gen && d.handoff && d.gen.key === P.genKey(d.handoff) ? d.gen : null;
    if (!g) return P.agentRow({ st: 'wait', name, sub: '세 안이 정해지면 안마다 교육비 지원·근무시간 학습 인정을 확인해요' });
    syncGen(g);
    const os = D.optionOrder.map(pid => g.options[pid]).filter(Boolean), fails = os.filter(o => o.supportFail);
    if (fails.length) return P.agentRow({ st: 'fail', name, sub: AI.live() ? via('default') : '', failLabel: '확인 실패', tag: '오류 발생', tagCls: 'fail', retry: ['sup-retry', 'all'], detail: `${esc(fails[0].supportFail.cause.user || AI.userText(fails[0].supportFail.cause.kind))} · 지원 조건은 ‘확인 필요’로 두고 넘어갈 수 있어요` });
    if (supBusy || os.some(o => !o.support)) return P.agentRow({ st: 'run', name, sub: P.runSub('default', '안마다 유료 자료·학습 형태로 등록된 규정을 확인하고 있어요') });
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
      const rows = `<div class="agents">${GEN_ROWS().map(id => genRow(r, id)).join('')}${supRow(d)}</div>`;
      if (g.fail) {
        const failed = D.optionOrder.filter(id => r.rows[id].st === 'fail'), names = failed.map(id => `${id} ${D.perspectives[id].name}`).join(', ');
        return GP.stepper('options') + P.failPage({
          title: '로드맵 3안 작성 중 문제가 발생했어요',
          desc: g.ok ? `${esc(names)}을 쓰지 못했어요. 작성된 안만 가지고 다음 단계로 넘어가거나, 실패한 안만 다시 시도할 수 있어요.` : '관점별 하위 에이전트가 로드맵 안을 쓰지 못했어요. 실패한 안을 다시 시도하거나, 조건을 고쳐 다시 만들어 주세요.',
          cause: `${failed.map(id => `${id} ${esc(D.perspectives[id].name)} — ${esc(r.rows[id].err.user || AI.userText(r.rows[id].err.kind))}`).join(' · ')}. ${esc(todoOf(failed.map(id => r.rows[id].err)))}`,
          body: `${P.handoffView(h, hoOpen)}${rows}`,
          ops: P.opsBox(failed.map(id => [rowName(id), r.rows[id].err])),
          foot: `<button class="btn line" data-act="result-edit">${icon('left')}조건 수정하고 다시 만들기</button><button class="btn pri" data-act="gen-partial" ${g.running || !g.ok ? 'disabled' : ''}>${icon('map')}로드맵 확인하기</button>`,
          hint: g.running ? '작성 중인 안이 끝나면 ‘로드맵 확인하기’를 누를 수 있어요.' : !g.ok ? '작성된 안이 없어요. 실패한 안을 다시 시도하거나 조건을 고쳐 주세요.' : `‘로드맵 확인하기’를 누르면 작성된 ${g.ok}개 안만 비교해요. 실패한 안은 저장하지 않아요.`
        });
      }
      const done = !!r && !g.running && g.ok === D.optionOrder.length && !!d.gen;
      return GP.stepper('options') + P.page({
        title: done ? '로드맵 3안을 다 썼어요' : '로드맵 계획 에이전트가 3안을 쓰고 있어요',
        lead: done ? '‘3안 보러 가기’를 눌러 비교해 보세요. 지원 조건 확인이 끝나지 않았어도 넘어갈 수 있어요(비교표에서 이어서 보여 줘요).' : AI.mode() === 'ollama' ? '관점별 하위 에이전트 셋이 진단 에이전트가 넘긴 같은 내용으로 동시에 요청해요. AI 서버 사정에 따라 차례대로 처리돼 시간이 더 걸릴 수 있어요.' : '관점별 하위 에이전트 셋이 진단 에이전트가 넘긴 같은 내용으로 동시에 작성해요.',
        body: `${P.handoffView(h, hoOpen)}${rows}`,
        foot: `<button class="btn line" data-go="new-result">${icon('left')}이전</button><button class="btn pri" data-go="new-options" ${done ? '' : 'disabled'}>3안 보러 가기</button>`
      });
    },
    after() {
      const d = S().draft, key = P.genKey(d.handoff), r = curGen(d);
      /* 저장된 진행 상태가 있으면 이어서 보여 준다. 실패한 안은 그대로 두고(자동 재시도 없음), 새로 고침으로 끊긴 안만 다시 요청한다 */
      if (r) { GEN_ROWS().filter(id => r.rows[id].st === 'run' && !running.has(key + '|' + id)).forEach(id => runRow(id)); ensureSupport(); return; }
      if (d.gen && d.gen.key === key) { GP.go('new-options'); return; }
      startGen(key);
    }
  };

  /* 5. 3안 비교표 (10/14): 열 순서는 A1·A2·A3 고정. 마음에 들지 않는 안은 요청을 적어 그 안만 다시 만들고(버전으로 쌓임), ‹ › 로 버전을 넘겨 본다 */
  const regenBusy = {}, regenErr = {};
  const reqText = q => [q.wish, (q.quick || []).join(', '), (q.removeActs || []).length && `빼기: ${q.removeActs.map(x => x.title).join(', ')}`, (q.replaceActs || []).length && `바꾸기: ${q.replaceActs.map(x => x.title).join(', ')}`].filter(Boolean).join(' · ');
  scr['new-options'] = {
    nav: 'new', newStep: true, title: '로드맵 3안', width: 'xwide',
    guard: () => { const d = S().draft; if (d.gen) return null; return d.handoff ? 'new-gen' : blockedTo('options') || 'new-result'; },
    render() {
      const d = S().draft, g = d.gen; syncGen(g);
      const ps = P.opts(), cur = d.chosen;
      const col = p => `data-col="${p.opt}"${regenBusy[p.opt] ? ' class="busy"' : ''}`;
      const row = (k, f) => `<tr><td class="k">${k}</td>${ps.map(p => `<td ${col(p)}>${f(p, p.def)}</td>`).join('')}</tr>`;
      const src = o => (o.source && o.source !== 'mock' ? `<span class="tag acc">${AI.PROV[o.source] || 'API'} 작성</span>` : '<span class="tag">가데이터</span>');
      const off = ps.some(p => p.def.offDomain), missing = g.missing || [];
      const ver = p => {
        const list = (g.hist || {})[p.opt], i = (g.cur || {})[p.opt] || 0, o = p.def;
        const nav = list && list.length > 1 ? `<span class="vnav"><button type="button" data-act="ver" data-arg="${p.opt}:-1" ${i === 0 || regenBusy[p.opt] ? 'disabled' : ''} aria-label="이전 버전">${icon('left')}</button><b class="num">버전 ${i + 1}/${list.length}</b><button type="button" data-act="ver" data-arg="${p.opt}:1" ${i === list.length - 1 || regenBusy[p.opt] ? 'disabled' : ''} aria-label="다음 버전">${icon('right')}</button></span>` : '';
        const info = i > 0 ? `${o.revSummary ? `<span class="small rev">바꾼 점: ${esc(o.revSummary)}</span>` : ''}${o.revRequest ? `<span class="small muted rev">요청: ${esc(o.revRequest)}</span>` : ''}${(o.revNotes || []).length ? `<span class="small muted rev">반영하지 못한 것: ${esc(o.revNotes.join(' '))}</span>` : ''}` : '';
        return nav + info;
      };
      return GP.stepper('options') + P.page({
        title: ps.length === 3 ? '로드맵 3안을 비교하고 골라 주세요' : ps.length === 1 ? '작성된 로드맵을 확인해 주세요' : `작성된 로드맵 ${ps.length}안을 비교하고 골라 주세요`,
        lead: '같은 목표와 학습 여건으로 방법만 달라요. 마음에 들지 않는 안은 바라는 점을 적어 그 안만 다시 만들 수 있고, 다시 만든 안은 버전으로 넘겨 볼 수 있어요.',
        body: `<div class="tblwrap"><table class="cmp"><thead><tr><th></th>${ps.map(p => `<th ${col(p)}><label><input type="radio" name="pick" value="${p.opt}" data-bind="draft.chosen" ${cur === p.opt ? 'checked' : ''}><span><b>${p.opt} ${esc(p.name)}</b><small>${esc(p.tagline)}</small></span></label>
              ${ver(p)}<button class="regen" data-act="regen-one" data-arg="${p.opt}" ${regenBusy[p.opt] ? 'disabled' : ''}>${regenBusy[p.opt] ? '<span class="sp"></span>다시 쓰는 중…' : icon('history') + '이 안만 다시 만들기'}</button>${regenErr[p.opt] && !regenBusy[p.opt] ? `<span class="small rev fail-t">${icon('x')}<span>다시 만들지 못했어요 · ${esc(regenErr[p.opt].user)}. 이전 안을 그대로 뒀어요. 다시 해 보려면 ‘이 안만 다시 만들기’를 눌러 주세요.</span></span>${P.opsBox([['', regenErr[p.opt]]], 'sm')}` : ''}</th>`).join('')}</tr></thead><tbody>
            ${row('기간 · 주당', p => `<span class="numv">${p.weeks}주</span> · 주 ${p.hours}시간${d.handoff.prefs.hoursAuto ? '<small class="muted"> (에이전트가 정함)</small>' : ''}`)}
            ${row('예상 비용', p => `<span class="numv">${won(p.cost)}${p.costUnknown ? ' + 응시료' : ''}</span>`)}
            ${row('지원 조건', (p, x) => P.supCell(x))}
            ${row('단계', p => D.stages.filter(s => s.n >= p.start && P.stageActs(p, s.n).length).map(s => s.name).join(' › '))}
            ${row('추천 이유', (p, x) => esc(x.reason))}
            ${row('좋은 점', (p, x) => `<ul>${x.pros.map(t => `<li>${esc(t)}</li>`).join('')}</ul>`)}
            ${row('아쉬운 점', (p, x) => `<ul>${x.cons.map(t => `<li>${esc(t)}</li>`).join('')}</ul>`)}
            ${row('활동', p => `<details class="more"><summary>${icon('right')}${p.acts.length}개 보기</summary><ul>${p.acts.map(a => `<li>${esc(a.title)} <span class="muted small">${a.task ? '직접 수행' : ''} ${hrs(a.hours)}</span></li>`).join('')}</ul></details>`)}
            ${row('작성', (p, x) => src(x))}
          </tbody></table></div>
          ${supNote()}
          ${missing.length ? P.note(`${esc(missing.map(id => `${id} ${D.perspectives[id].name}`).join(', '))}은 작성에 실패해 빠졌어요. 세 안을 다시 받으려면 ‘점검 결과’에서 ‘로드맵 생성’을 다시 눌러 주세요.`) : ''}
          ${P.note(ps.length > 1 ? '고른 안(보고 있는 버전)을 쓴 에이전트(관점)만 저장해요. 고르지 않은 안과 다른 버전은 저장하지 않아요.' : '고른 안(보고 있는 버전)을 쓴 에이전트(관점)만 저장해요.')}
          ${off ? P.note('가데이터 모드에는 RAG 시나리오 후보만 있어요. 다른 목표의 후보는 좌측 ‘AI 모델’에서 RunPod-Ollama나 OpenAI API를 쓰면 확인할 수 있어요.') : ''}`,
        foot: `<button class="btn line" data-go="new-result">${icon('left')}이전</button><button class="btn pri" data-act="choose" data-need="draft.chosen">고른 안으로 검토하기</button>`
      });
    },
    after() { ensureSupport(); }
  };
  GP.act.choose = () => {
    const id = S().draft.chosen;
    if (regenBusy[id]) { GP.toast('그 안을 다시 쓰는 중이에요. 잠시 뒤에 골라 주세요'); return; }
    syncGen(S().draft.gen); P.choose(id);
  };
  GP.act.ver = arg => {
    const [pid, dir] = arg.split(':'), g = S().draft.gen; if (!g || regenBusy[pid]) return;
    const list = hist(g, pid), i = Math.min(list.length - 1, Math.max(0, (g.cur[pid] || 0) + +dir));
    setCur(g, pid, i); delete regenErr[pid];
    if (S().draftPlan && S().draftPlan.opt === pid) S().draftPlan = null;
    GP.save(); GP.render(false); ensureSupport();
  };

  /* 다시 만들기 요청 창: 바라는 점(문장) + 빠른 칩 + 활동별 그대로/빼기/바꾸기. 아무것도 고르지 않으면 활동 구성이 다른 안을 새로 쓴다 */
  const QUICK = ['더 짧게', '실습 늘리기', '비용 줄이기', '영상 위주', '문서 위주', '업무 과제 늘리기'];
  function regenSheet(pid) {
    const d = S().draft, g = d.gen; if (!g || !g.options[pid] || regenBusy[pid]) return;
    syncGen(g);
    const o = g.options[pid], pl = P.buildPlan(o, P.params(o));
    S().regenReq = { pid, note: '', chips: [], acts: {} }; GP.save();
    GP.sheet(`<div class="rg">
      <div class="field"><label>바라는 점 <span class="muted small">선택</span></label>
        <textarea class="textarea sm" data-bind="regenReq.note" maxlength="300" aria-label="바라는 점" placeholder="예: 평일 저녁에 맞게 짧은 자료로 바꿔 주세요"></textarea>
        <div class="chips rg-chips">${QUICK.map(q => `<button type="button" class="chip" data-act="rg-chip" data-arg="${q}" aria-pressed="false">${q}</button>`).join('')}</div></div>
      <div class="field"><label>빼거나 바꿀 활동 <span class="muted small">선택</span></label><div class="rg-acts">${pl.acts.map(a => `<div class="rg-act"><span class="tx">${esc(a.title)}<small>${a.stage}단계 · ${a.task ? '직접 수행 과제' : esc(D.res[a.res].kind)} · ${hrs(a.hours)}</small></span>
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
  GP.act['regen-go'] = () => {
    const q = S().regenReq, g = S().draft.gen; if (!q || !g) return;
    GP.closeSheet();
    const o = g.options[q.pid], ref = id => { const a = o.acts.find(x => x.id === id); return a ? { key: a.id, title: a.title } : null; };
    const ids = Object.keys(q.acts || {});
    const req = { wish: String(q.note || '').trim(), quick: q.chips.slice(), removeActs: ids.filter(id => q.acts[id] === 'remove').map(ref).filter(Boolean), replaceActs: ids.filter(id => q.acts[id] === 'replace').map(ref).filter(Boolean) };
    S().regenReq = null; GP.save();
    regenRun(q.pid, req.wish || req.quick.length || req.removeActs.length || req.replaceActs.length ? req : null);
  };
  async function regenRun(pid, req) {
    const d = S().draft, g = d.gen; if (!g || regenBusy[pid]) return;
    syncGen(g);
    const list = hist(g, pid), prev = g.options[pid];
    regenBusy[pid] = true; delete regenErr[pid]; GP.render(false);
    if (!AI.live()) await sleep(1100);
    let o = null;
    try {
      o = await AI.roadmapOption({ pid, handoff: d.handoff, variant: list.length, request: req, previousDef: prev,
        previous: { tagline: prev.tagline, acts: prev.acts.map(a => ({ key: a.id, stage: a.stage, title: a.title, res: a.res, hours: a.hours })) } });
    } catch (err) { regenErr[pid] = AI.cause(err); }
    regenBusy[pid] = false;
    if (S().draft !== d || d.gen !== g) return;
    if (!o) { if (S().route === 'new-options') GP.render(false); GP.toast(`${D.perspectives[pid].name}을 다시 만들지 못했어요. 이전 안을 그대로 둬요`); return; }
    o.revRequest = req ? reqText(req) : ''; o.revSummary = o.summary || (req ? '' : '같은 관점으로 활동 구성을 바꿔 새로 썼어요'); o.revNotes = o.notes || [];
    delete o.summary; delete o.notes;
    list.push(o);
    if (list.length > 6) list.splice(1, 1); /* 처음 안과 최근 다섯 버전만 둔다 */
    setCur(g, pid, list.length - 1);
    if (S().draftPlan && S().draftPlan.opt === pid) S().draftPlan = null;
    GP.save();
    if (S().route === 'new-options') GP.render(false);
    GP.toast(`${D.perspectives[pid].name}을 다시 만들었어요 · 버전 ${list.length}`);
    ensureSupport();
  }

  /* 6. 검토·확정 */
  scr['new-review'] = {
    nav: 'new', newStep: true, title: '검토·확정', width: 'wide', guard: () => blockedTo('review'),
    render() {
      const pl = S().draftPlan, g = S().draft.gen; syncGen(g);
      const o = (g && g.options[pl.opt]) || pl.def;
      return GP.stepper('review') + P.page({
        eyebrow: `${pl.opt} ${esc(pl.name)}${g && g.hist && (g.hist[pl.opt] || []).length > 1 ? ` · 버전 ${(g.cur[pl.opt] || 0) + 1}` : ''}`, title: '이 로드맵으로 확정할까요?',
        body: `<div class="card"><p style="font-weight:650">${esc(pl.goal)}</p><div style="margin-top:16px">${P.stats(pl, true)}</div></div>
          <div class="sec">${P.stagesView(pl)}</div>
          <p class="small muted rv-fix">고치고 싶은 활동이 있으면 <button class="link" data-act="review-regen">${icon('history')}3안 비교에서 이 안 다시 만들기</button></p>
          <div class="sec"><div class="card flat"><dl class="kv"><dt>지원 조건</dt><dd>${P.supCell(o)}</dd></dl></div>${supNote()}</div>
          ${P.note(`확정은 내 학습 계획을 정하는 것이에요. 기관의 승인·결재가 아니에요. ${P.mySup() ? `확정하면 내 계획을 보는 부서장 ${esc(P.mySup().name)} 님은 확정한 로드맵, 진행 상태, 결과 보고서를 볼 수 있어요.` : '내 계획을 보는 부서장이 없어 확정한 로드맵은 나만 봐요.'}`)}
          ${P.recs('active').length ? P.note(`지금 진행 중인 로드맵 ${P.recs('active').length}개는 그대로 두고, 이 로드맵을 함께 진행해요.`) : ''}`,
        foot: `<button class="btn line" data-go="new-options">${icon('left')}이전</button><button class="btn pri" data-act="confirm">확정하기</button>`
      });
    },
    after() { ensureSupport(); }
  };
  GP.act['review-regen'] = () => { const id = S().draftPlan && S().draftPlan.opt; GP.go('new-options'); if (id) regenSheet(id); };

  /* ───────── 홈 ───────── */
  /* 활동 한 줄. 홈에 여러 로드맵이 함께 보여서 어느 로드맵의 기록인지 입력 주소(plans.{id}.progress…)에 넣는다 */
  const actRow = (a, R) => `<li style="align-items:center"><div class="tx">${esc(a.title)}<small>${P.actMeta(a)} · ${hrs(a.hours)}${(R.progress[a.id] || {}).memo ? ' · 메모 있음' : ''}</small></div>
    <div class="mini-seg" role="radiogroup" aria-label="${esc(a.title)} 진행 상태">${[['doing', '진행 중'], ['done', '완료']].map(([v, l]) => `<label><input type="radio" name="st-${R.id}-${a.id}" value="${v}" data-bind="plans.${R.id}.progress.${a.id}.status" data-rerender ${P.st(a.id, R.plan) === v ? 'checked' : ''}>${l}</label>`).join('')}</div>
    <button class="link quiet" data-act="rec-open" data-arg="${R.id}|${a.id}" aria-label="메모와 첨부">${icon('edit')}</button></li>`;
  const draftBox = () => {
    const d = S().draft, cur = (S().lastNew || 'new-goal').split(':')[0], k = SUB[cur] || (STEPS.find(s => s[2] === cur) || STEPS[0])[0];
    return `<div class="card"><div class="sec-h"><h2 class="st">작성 중인 새 로드맵</h2><button class="link quiet" data-act="discard-draft">지우기</button></div>
      <p class="muted" style="margin:-4px 0 14px">${esc(d.goal || '목표 입력 전')}</p>${GP.stepper(k)}
      <div class="actions" style="margin-top:6px"><button class="btn line" data-go="${GP.newRoute()}">이어서 작성하기</button></div></div>`;
  };
  GP.act['discard-draft'] = () => { S().draft = GP.freshDraft(); S().draftPlan = null; S().lastNew = null; GP.save(); GP.render(true); GP.toast('작성 중인 로드맵을 지웠어요'); };
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
  const progCard = (R, c) => {
    const pl = R.plan;
    return `<div class="card" style="margin-top:12px"><div class="sec-h"><h2 class="st">전체 진행 · ${c.done}/${c.t}</h2><button class="link" data-go="roadmap:${R.id}">로드맵 전체 ${icon('right')}</button></div>
      <div class="pstrip">${D.stages.filter(st => st.n >= pl.start && P.stageActs(pl, st.n).length).map(st => { const as = P.stageActs(pl, st.n), dn = as.filter(a => P.st(a.id, pl) === 'done').length; return `<div><b>${st.n}. ${st.name}</b><div class="bar"><i style="width:${(dn / as.length) * 100}%"></i></div><span class="small">${dn}/${as.length}</span></div>`; }).join('')}</div></div>`;
  };
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
          <p class="lead">${esc(pl.goal)}</p>${alerts(R)}${stageCard(R)}${progCard(R, c)}${postCta(R, c)}${drafting}${pastLink()}`;
      }
      return `<p class="eyebrow">안녕하세요, ${hello()} 님</p><h1 class="t">진행 중인 로드맵 ${act.length}개</h1><p class="lead">로드맵마다 이번 단계 활동을 보여 드려요.</p>
        ${act.map(R => { const pl = R.plan, c = P.count(pl); return `<section class="hp"><div class="hp-h"><p class="eyebrow">${esc(pl.name)} · v${pl.version}</p><h2 class="hp-t">${esc(pl.goal)}</h2></div>${alerts(R)}${stageCard(R, true)}${progCard(R, c)}${postCta(R, c)}</section>`; }).join('')}
        ${drafting}${pastLink()}`;
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
      body: `${live ? alerts(R) : P.note(R.status === 'done' ? '마친 로드맵이에요. 기록은 읽기만 할 수 있어요.' : '보관한 로드맵이에요. 기록은 읽기만 할 수 있고, ‘다시 진행하기’를 누르면 이어서 기록할 수 있어요.')}${P.stats(pl)}<div class="sec">${stages}</div>${repList}`,
      foot
    });
  }
  scr.roadmap = {
    nav: 'roadmap', title: '내 로드맵', width: 'wide',
    guard: param => { if (!param) return null; if (S().plans[param]) { S().cur = param; return null; } return 'roadmap'; },
    render: param => (param ? roadView(P.R(param)) : roadList())
  };
  /* 보관: 진행을 멈추고 지난 로드맵으로 옮긴다. 기록은 그대로이고 언제든 다시 진행할 수 있다 */
  GP.act['plan-archive'] = pid => {
    const R = P.R(pid); if (!R || R.status !== 'active') return;
    GP.sheet(`<p style="margin-top:0">진행 기록·메모·버전·받은 코멘트는 그대로 남고, 내 로드맵의 ‘지난 로드맵’에서 볼 수 있어요.</p>
      <ul class="plain-list small"><li>홈과 진행 중 목록에서 빠져요.</li><li>부서장 화면에는 ‘보관’으로 보이고, 보관한 로드맵에는 새 코멘트를 받지 않아요.</li><li>언제든 ‘다시 진행하기’로 이어서 할 수 있어요.</li></ul>
      ${R.pending ? P.note('만들어 둔 수정안은 보관할 때 버려요.') : ''}`,
      { title: '이 로드맵을 보관할까요?', sub: R.plan.goal, foot: `<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="plan-archive-ok" data-arg="${R.id}">보관하기</button>` });
  };
  GP.act['plan-archive-ok'] = pid => {
    const R = P.R(pid); if (!R || R.status !== 'active') return;
    Object.assign(R, { status: 'archived', archivedAt: D.today, pending: null, rev: null });
    GP.closeSheet(); GP.save(); GP.go('roadmap'); GP.toast('로드맵을 보관했어요 · 지난 로드맵에서 볼 수 있어요');
  };
  GP.act['plan-resume'] = pid => {
    const R = P.R(pid); if (!R || R.status !== 'archived') return;
    R.status = 'active'; R.resumedAt = D.today; delete R.archivedAt;
    GP.save(); GP.go('roadmap:' + R.id); GP.toast('로드맵을 다시 진행해요. 기록은 그대로 이어져요');
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
  scr.post = {
    nav: 'checks', title: '사후 점검', width: 'wide', guard: P.planGuard('post', 'checks', true),
    render() {
      const R = P.R(), pl = R.plan;
      /* 보고서 작성 실패: 가데이터로 대신하지 않고 안내한다. 응답은 그대로 두고, '다시 시도하기'를 눌러야만 다시 쓴다(10/14) */
      const f = R.post.fail;
      if (f) return P.failPage({
        title: '결과 보고서를 만드는 중 문제가 발생했어요',
        desc: '진단 에이전트가 결과 보고서를 쓰지 못했어요. 사후 점검 응답과 목표 달성도, 결과물은 그대로 남아 있어요.',
        cause: esc(P.errText(f.cause)),
        body: `<div class="agents">${P.agentRow({ st: 'fail', name: '진단 에이전트 · 결과 보고서 작성', sub: AI.live() ? via('default') : '', tag: '오류 발생', tagCls: 'fail' })}</div>`,
        ops: P.opsBox([['', f.cause]]),
        foot: `<button class="btn line" data-act="post-fail-back">${icon('left')}사후 점검 응답 보기</button><button class="btn pri" data-act="make-report">${icon('retry')}다시 시도하기</button>`
      });
      const left = pl.acts.filter(a => P.st(a.id, pl) !== 'done').length;
      return P.page({
        back: 'checks', eyebrow: `${esc(pl.name)} · v${pl.version} · ${esc(pl.goal)}`, title: '사후 점검', lead: '사전 점검과 같은 문항이에요. 지금 기준으로 1~5점을 골라 주세요. 진단 에이전트가 계산한 수준값은 보여드리지 않아요.',
        body: `${left ? P.note(`아직 ‘진행 중’인 활동이 ${left}개 있어요. 결과 보고서에는 ‘진행 중’으로 남아요. 답한 내용은 저장되니 활동을 더 한 뒤 이어서 답해도 돼요.`) : ''}<div class="stack">${P.quizBody(pl.assess.questions, 'post.answers', pl.assess.answers)}
          <div class="card"><h2 class="st">처음 목표를 얼마나 이뤘나요?</h2><div class="chips">${D.goalSelf.map((l, i) => `<label class="chip"><input type="radio" name="goalSelf" value="${i + 1}" data-bind="post.goalSelf" ${String(R.post.goalSelf) === String(i + 1) ? 'checked' : ''}>${l}</label>`).join('')}</div></div>
          <div class="card"><h2 class="st">결과물·수료증 <span class="muted small" style="font-weight:400">선택</span></h2>${R.post.file ? `<div class="file-on">${icon('file')}<div class="tx"><b>${esc(R.post.file.name)}</b><small class="muted">파일 이름만 보관 · 내용은 검증하지 않아요</small></div></div>` : `<label class="drop"><input type="file" data-bind-file="post.file"><span class="ico">${icon('file')}</span><span><b>결과물·수료증 고르기</b><small>내지 않아도 기록은 그대로예요</small></span></label>`}</div></div>`,
        foot: '<button class="btn pri" data-act="make-report" data-need="post">결과 보고서 만들기</button>'
      });
    }
  };
  GP.act['make-report'] = async (a, el) => {
    const R = P.R(); if (!R) return;
    const post = R.post, here = () => S().route === 'post:' + R.id;
    /* 실패 화면의 '다시 시도하기': 응답 화면으로 돌아가 그 버튼에서 진행을 보여 준다 */
    if (post.fail) { post.fail = null; GP.render(false); el = document.querySelector('[data-act="make-report"]'); }
    if (!el || el.disabled) return;
    el.disabled = true; el.textContent = '진단 에이전트가 보고서를 쓰고 있어요…';
    let r = null;
    try { r = await P.makeReport(R); } catch (err) { post.fail = { cause: AI.cause(err) }; }
    if (S().plans[R.id] !== R || R.post !== post) return;
    if (!r) { GP.save(); if (here()) GP.render(false); return; }
    post.fail = null; GP.save();
    if (here()) GP.go('report:' + r.id); else GP.toast('결과 보고서가 나왔어요 · 점검·보고서에서 볼 수 있어요');
  };
  GP.act['post-fail-back'] = () => { const R = P.R(); if (R) R.post.fail = null; GP.save(); GP.render(false); };
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
  scr.report = {
    nav: 'checks', title: '결과 보고서', width: 'wide',
    render(id) {
      const r = P.report(id); if (!r) return P.page({ back: 'checks', title: '결과 보고서가 없어요' });
      const R = S().plans[r.planId], sup = P.mySup();
      return P.page({
        back: 'checks', eyebrow: `결과 보고서 · ${esc(r.opt)} v${r.version} · ${esc(r.createdAt)}`, title: '학습 결과 보고서', lead: esc(r.goal),
        body: `${P.reportBody(r)}
          ${sup ? P.note(`이 보고서는 내 계획을 보는 부서장 ${esc(sup.name)} 님도 볼 수 있어요.`) : ''}
          ${r.confirmed ? '' : P.note('‘확인했어요’를 누르면 이 로드맵을 마친 것으로 기록하고 내 로드맵의 ‘지난 로드맵’으로 옮겨요.')}`,
        foot: r.confirmed ? (R ? `<button class="btn line" data-go="roadmap:${R.id}">로드맵 보기</button>` : '') : `<button class="btn pri" data-act="report-ok" data-arg="${r.id}">확인했어요</button>`
      });
    }
  };
  GP.act['report-ok'] = id => {
    const r = P.report(id); if (!r) return;
    r.confirmed = true;
    const R = S().plans[r.planId];
    if (R && R.status !== 'done') Object.assign(R, { status: 'done', doneAt: D.today, pending: null, rev: null });
    GP.save(); GP.go('home'); GP.toast('결과 보고서를 확인했어요 · 이 로드맵은 지난 로드맵으로 옮겼어요');
  };

  /* ───────── 로그인 (시연용 · 실제 인증 없음 · 10/15) ─────────
     가상 사내 DB 직원 16명만 로그인한다. 사번 + 비밀번호(시연 초기 비밀번호 0000으로 통일).
     계정은 로그아웃한 뒤 다시 로그인해야만 바뀐다. '직원 고르기'(시연용)는 부서별로 묶어 보여 주고, 고르면 사번을 채운다 */
  const feat = (ic, t, d) => `<div class="feat"><span class="ico">${icon(ic)}</span><span><b>${t}</b><small>${d}</small></span></div>`;
  /* 부서는 DB 에 처음 나오는 순서, 부서 안에서는 부서장 먼저 */
  const deptGroups = () => {
    const out = [];
    GP.accts().forEach(e => { let g = out.find(x => x.dept === e.dept); if (!g) out.push(g = { dept: e.dept || '부서 없음', list: [] }); g.list.push(e); });
    out.forEach(g => g.list.sort((a, b) => (GP.isSup(b) ? 1 : 0) - (GP.isSup(a) ? 1 : 0)));
    return out;
  };
  scr.login = {
    title: '로그인',
    render: () => `<div class="login-wrap">
      <section class="login-card" aria-labelledby="lgTitle">
        <span class="tag acc">${icon('lock')}한국수자원공사 임직원 로그인 · 시연용</span>
        <h1 class="t lg" id="lgTitle">다시 오신 걸 환영해요</h1>
        <p class="lead">AI 활용·개발 역량 성장 로드맵을 이어서 만들어 보세요.</p>
        <form id="loginForm" novalidate>
          <div class="field lg-pick"><label for="lgPick">직원 고르기 <span class="muted small">시연용 · 고르면 사번을 채워요</span></label>
            <select class="input" id="lgPick"><option value="">가상 사내 DB 직원 ${GP.accts().length}명 중 고르기</option>${deptGroups().map(g => `<optgroup label="${esc(g.dept)}">${g.list.map(e => `<option value="${esc(e.code)}">${esc(e.name)}${GP.isSup(e) ? ' (부서장)' : ''}</option>`).join('')}</optgroup>`).join('')}</select></div>
          <div class="field"><label for="lgId">사번</label><input class="input" id="lgId" inputmode="numeric" maxlength="8" autocomplete="username" placeholder="8자리 사번 (예: 20200001)"></div>
          <div class="field"><label for="lgPw">비밀번호</label><div class="pw"><input class="input" id="lgPw" type="password" autocomplete="current-password" placeholder="비밀번호를 입력해 주세요"><button type="button" class="eye" data-act="pw-toggle" aria-label="비밀번호 보기">${icon('eye')}</button></div></div>
          <div class="row" style="margin-top:14px"><label class="check"><input type="checkbox" id="lgKeep" checked>로그인 상태 유지</label><span class="grow"></span><button type="button" class="link quiet" data-act="login-help" data-arg="pw">비밀번호 찾기</button></div>
          <p class="err" id="lgErr" role="alert" hidden></p>
          <button class="btn pri block" type="submit" style="margin-top:18px">로그인 ${icon('arrow')}</button>
        </form>
        <div class="or">또는</div>
        <button class="btn line block" data-act="login-help" data-arg="sso">${icon('users')}기관 통합인증(SSO)으로 로그인</button>
        ${P.note(`시연용 화면이에요. 실제 인증은 연결하지 않았어요. 가상 사내 DB 직원(엑셀 초안 ${esc(String((window.GPEMP || {}).source || '').replace(/^.*_(\d[\d.]*)\.xlsx$/, '$1'))}) ${GP.accts().length}명의 사번으로 들어올 수 있고, 초기 비밀번호는 모두 ${GP.PW}이에요. 입력한 비밀번호는 저장하지 않아요. 다른 직원으로 바꾸려면 로그아웃한 뒤 다시 로그인해 주세요.`)}
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
        <p class="small" style="margin-top:auto;opacity:.82">부서장은 감독 그룹 소속 직원의 확정 로드맵·진행 상태·결과 보고서를 보고 코멘트만 남겨요. 평가나 승인이 아니에요.</p>
      </aside>
    </div>`,
    after(root) {
      const f = root.querySelector('#loginForm'); if (!f) return;
      const pick = root.querySelector('#lgPick'), idIn = root.querySelector('#lgId'), pw = root.querySelector('#lgPw'), err = root.querySelector('#lgErr');
      const fail = t => { err.textContent = t; err.hidden = false; };
      /* 직원을 고르면 사번을 채우고 비밀번호 칸으로. 사번을 직접 적으면 맞는 직원을 골라 둔다 */
      pick.addEventListener('change', () => { if (pick.value) { idIn.value = pick.value; err.hidden = true; pw.focus(); } });
      idIn.addEventListener('input', () => { const e = GP.acctByCode(idIn.value); pick.value = e ? e.code : ''; });
      f.addEventListener('submit', e => {
        e.preventDefault();
        const code = idIn.value.trim(), p = pw.value;
        if (!code || !p) return fail('사번과 비밀번호를 입력해 주세요.');
        const acct = GP.acctByCode(code);
        pw.value = '';
        if (!acct || p !== GP.PW) return fail('사번 또는 비밀번호가 맞지 않아요.');
        if ((acct.accountStatus && acct.accountStatus !== 'active') || (acct.status && acct.status !== '재직')) return fail('지금은 쓸 수 없는 계정이에요. 인사 담당 부서(인재경영실 · 가상)에 문의해 주세요.');
        doLogin(acct);
      });
    }
  };
  function doLogin(acct) {
    const keep = !!(document.getElementById('lgKeep') || {}).checked;
    GP.setSession({ acct: acct.id, remember: keep }, keep);
    GP.load(acct.id);
    const r = S().route;
    GP.go(r && r !== 'login' && (!/^m-/.test(r) || GP.isSup(acct)) ? r : 'home');
    GP.toast(`${acct.name} 님, 반가워요`);
  }
  GP.act['pw-toggle'] = (a, el) => { const i = document.getElementById('lgPw'); i.type = i.type === 'password' ? 'text' : 'password'; el.setAttribute('aria-label', i.type === 'password' ? '비밀번호 보기' : '비밀번호 숨기기'); };
  GP.act['login-help'] = k => GP.toast(k === 'sso' ? '시연에서는 기관 통합인증을 연결하지 않았어요. 사번과 비밀번호로 로그인해 주세요' : `시연에서는 비밀번호 찾기를 연결하지 않았어요. 초기 비밀번호는 ${GP.PW}이에요`);

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

  /* ───────── 시연 단계 이동 ─────────
     로그인한 계정의 기록만 그 단계의 시연 데이터로 바꾼다(10/15). 다른 계정의 기록이 필요한 '부서장 코멘트 작성' 단계는 뺐다:
     직원 계정으로 '로드맵 실행 중'까지 옮긴 뒤 로그아웃하고 그 직원의 부서장으로 로그인한다.
     '코멘트 받은 뒤'는 DB 의 '내 계획을 보는 부서장' 이름으로 예시 코멘트를 넣는다(부서장이 없는 계정은 쓸 수 없음) */
  GP.JUMPS = [['start', '처음부터'], ['details', '세부 사항부터'], ['quiz', '사전 점검부터'], ['result', '점검 결과부터'], ['options', '로드맵 3안부터'], ['review', '확정 직전'],
    ['active', '로드맵 실행 중'], ['multi', '로드맵 2개 함께 진행'], ['comment', '코멘트 받은 뒤'], ['post', '사후 점검부터'], ['report', '결과 보고서']];
  GP.entry = { start: 'home', details: 'new-details', quiz: 'new-quiz', result: 'new-result', options: 'new-options', review: 'new-review', active: 'home', multi: 'home', comment: 'home', post: 'post:p1', report: 'report:r1' };
  GP.seed = function (stage) {
    const s = GP.fresh(); GP.S = s; s.demoOpen = true;
    if (stage === 'start') return s;
    const d = s.draft, M = AI.mock, sc = D.scenario;
    d.goal = sc.goal;
    if (stage === 'details') { s.lastNew = 'new-details'; return s; }
    Object.assign(d.prefs, sc.details); d.detailsOk = true;
    const q = M.questions({ goal: d.goal, prefs: d.prefs });
    d.quiz = { key: P.quizKey(d), questions: q.questions, domain: q.domain, base: quizBase(d) };
    if (stage === 'quiz') { s.lastNew = 'new-quiz'; return s; }
    d.answers = Object.assign({}, sc.pre);
    d.diag = Object.assign({ key: P.diagKey(d), answers: clone(d.answers) }, M.assess({ goal: d.goal, prefs: d.prefs, questions: d.quiz.questions, answers: d.answers }));
    if (stage === 'result') { s.lastNew = 'new-result'; return s; }
    d.handoff = P.buildHandoff(); d.genPrefs = clone(d.prefs);
    d.gen = { key: P.genKey(d.handoff), options: Object.fromEntries(D.optionOrder.map(pid => [pid, M.option({ pid, handoff: d.handoff })])) };
    D.optionOrder.forEach(pid => { d.gen.options[pid].support = M.support(pid, d.gen.options[pid]); });
    if (stage === 'options') { s.lastNew = 'new-options'; return s; }
    d.chosen = 'A3'; s.draftPlan = P.buildPlan(d.gen.options.A3, P.params(d.gen.options.A3));
    if (stage === 'review') { s.lastNew = 'new-review'; return s; }
    const assess = () => ({ questions: d.quiz.questions, answers: Object.assign({}, d.answers), level: d.diag.level, domain: d.quiz.domain });
    /* '로드맵 2개 함께 진행': 두 번째 로드맵(가데이터 A1 비용 우선안 · 목표 문장만 다름)도 같은 진단으로 만든다 */
    const second = stage === 'multi' ? Object.assign(P.buildPlan(d.gen.options.A1, P.params(d.gen.options.A1)), { goal: D.scenario2Goal }) : null;
    const R = P.newRec(Object.assign({}, s.draftPlan, {
      version: 1, confirmedAt: D.today, why: '최초 확정', assess: assess(),
      prefs: JSON.parse(JSON.stringify(d.prefs)), handoff: d.handoff, selection: P.selectionOf(d.gen.options.A3)
    }));
    s.picks = ['A3'];
    const pl = R.plan, ids = pl.acts.map(a => a.id), done = id => { R.progress[id] = { status: 'done', memo: '', file: null, at: D.today }; };
    ids.slice(0, 2).forEach(done);
    R.progress[ids[2]] = { status: 'doing', memo: '공개 가능 여부를 확인한 규정 6건까지 정리했어요.', file: null, at: D.today };
    if (second) {
      const R2 = P.newRec(Object.assign(second, { version: 1, confirmedAt: D.today, why: '최초 확정', assess: assess(), prefs: JSON.parse(JSON.stringify(d.prefs)), handoff: d.handoff, selection: P.selectionOf(d.gen.options.A1) }));
      R2.progress[R2.plan.acts[0].id] = { status: 'done', memo: '', file: null, at: D.today };
      s.picks.push('A1'); s.cur = R.id;
    }
    s.draft = GP.freshDraft(); s.draftPlan = null;
    if (stage === 'active' || stage === 'multi') return s;
    if (stage === 'comment') { const sup = P.mySup() || {}; R.comments = [Object.assign({ id: 'c1', by: sup.name || '부서장', byCode: sup.code || null }, D.commentSample, { at: D.today, status: 'new' })]; return s; }
    ids.slice(2, -1).forEach(done);
    R.progress[ids[ids.length - 1]] = { status: 'doing', memo: '팀 시연 일정 조율 중', file: null, at: D.today };
    if (stage === 'post') return s;
    R.post = { answers: Object.assign({}, sc.post), goalSelf: '4', file: { name: '규정QA_시제품_시연메모.pdf', size: 240000 } };
    const A = pl.assess, items = A.questions.map(x => ({ id: x.id, area: x.area, text: x.text, skill: AI.skillLabel(x.skill), pre: A.answers[x.id], post: R.post.answers[x.id] }));
    const doneA = pl.acts.filter(a => P.st(a.id, pl) === 'done'), rest = pl.acts.filter(a => P.st(a.id, pl) !== 'done');
    const out = M.report({ goal: pl.goal, opt: 'A3', domain: A.domain, items, doneTitles: doneA.map(a => a.title), restTitles: rest.map(a => a.title), total: pl.acts.length });
    s.reports = [{ id: 'r1', planId: R.id, version: 1, goal: pl.goal, opt: pl.name, createdAt: D.today, confirmed: false,
      gained: P.reportItems(items, true), still: P.reportItems(items, false),
      doneTitles: doneA.map(a => a.title), restTitles: rest.map(a => a.title), goalSelf: D.goalSelf[3], file: R.post.file, good: out.good, improve: out.improve, next: out.next,
      hidden: { pre: A.level, post: AI.levelOf(A.questions, R.post.answers) } }];
    return s;
  };
})();

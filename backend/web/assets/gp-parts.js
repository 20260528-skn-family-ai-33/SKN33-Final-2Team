/* GrowPath 5차 목업 (Claude) · 계산, 공통 조각, 여러 메뉴가 함께 쓰는 화면, 서버 동기화
   5차: 기록(작성 중인 로드맵·확정 로드맵·진행·수정안·코멘트·점검·보고서)은 서버가 저장한다. 이 파일은 4차 화면 그리기를 그대로 두고
   저장·에이전트 호출만 서버 API(gp-api.js)로 바꿨다 */
(function () {
  'use strict';
  const GP = window.GP, D = GP.D, AI = GP.AI, API = GP.API, { esc, won, hrs, icon } = GP;
  const P = GP.P = {};
  const S = () => GP.S;
  const stageName = n => (D.stages.find(s => s.n === n) || {}).name || '';
  P.stageName = stageName;
  const clone = o => JSON.parse(JSON.stringify(o));
  const resOf = id => D.res[id] || null;
  P.resOf = resOf;

  /* ───────── 상태 틀 ───────── */
  GP.freshDraft = () => ({
    goal: '', project: null, prefs: AI.emptyPrefs(), detailsOk: false,
    quiz: null, answers: {}, deepOn: false, deepMcq: {}, deepEssay: {}, diag: null, startStage: null, fix: null, edit: null, handoff: null, gen: null,
    chosen: null, quizFail: null, diagFail: null, genRun: null, doc: null, genPrefs: null, quizRun: null, diagRun: null
  });
  /* 로드맵 여러 개 (4차 묶음 6): plans[id] = 서버 기록 { id, status, createdAt·doneAt·archivedAt, plan, versions, progress, post, comments, pending, revision }
     + 화면에서 쓰는 중인 수정 요청 양식 rev. S.cur 은 지금 보고 있는 로드맵 id, S.plan·versions·progress·post·pending·rev 는 그 기록의 값 */
  const PER = ['plan', 'versions', 'progress', 'post', 'pending', 'rev'];
  const EMPTY = { plan: null, versions: [], progress: {}, post: null, pending: null, rev: null };
  P.wire = s => {
    PER.forEach(k => Object.defineProperty(s, k, {
      configurable: true, enumerable: false,
      get() { const R = s.plans && s.plans[s.cur]; return R ? R[k] : EMPTY[k]; },
      set(v) { const R = s.plans && s.plans[s.cur]; if (R) R[k] = v; }
    }));
    return s;
  };
  GP.fresh = () => P.wire({
    route: 'home', draft: GP.freshDraft(), draftId: null, draftPlan: null, plans: {}, cur: null,
    mgr: {}, reports: [], picks: [], lastNew: null, tmp: null, demoOpen: false
  });
  P.R = pid => (S().plans || {})[pid || S().cur] || null;
  P.recs = st => Object.values(S().plans || {}).filter(R => !st || R.status === st);
  P.focus = pid => { if (S().plans[pid]) S().cur = pid; return P.R(pid); };
  P.planReports = R => S().reports.filter(r => r.planId === R.id);
  P.newComments = R => (R.comments || []).filter(c => c.status === 'new');
  P.mySup = () => { const me = GP.me(); return (me && me.mySupervisor) || null; };
  P.cmBy = c => (c && c.by) || '부서장';

  /* ───────── 작성 중인 로드맵 서버 동기화 ─────────
     화면이 고치는 값(목표·기획서 이름·세부 사항·응답·고른 안·수정 화면 입력·마지막 단계)은 고친 뒤 0.4초 기다렸다가 서버에 저장한다.
     에이전트 결과(문항·진단·3안·지원 조건·기획서 요약 상태)는 서버만 쓰고, 화면은 서버 응답으로 받는다(takeDraft) */
  const CLIENT = ['goal', 'project', 'prefs', 'detailsOk', 'answers', 'deepOn', 'deepMcq', 'deepEssay', 'chosen', 'edit'];
  const snap = st => JSON.stringify([CLIENT.map(k => st.draft[k]), st.lastNew, st.draft.doc ? st.draft.doc.summary : null, (st.draft.gen && st.draft.gen.cur) || null]);
  let lastSent = null, timer = null, queue = Promise.resolve(), pendingBody = null;
  const hasContent = d => !!(String(d.goal || '').trim() || d.detailsOk || d.project);
  function bodyOf(st) {
    const d = st.draft, b = Object.fromEntries(CLIENT.map(k => [k, d[k]]));
    b.lastNew = st.lastNew;
    if (d.doc && d.doc.status === 'ok') b.docSummary = d.doc.summary || '';
    if (d.gen && d.gen.cur) b.genCur = d.gen.cur;
    return b;
  }
  GP.syncDraft = function () {
    const st = GP.own(); if (!st || !st.owner || !GP.me()) return;
    const s = snap(st);
    if (s === lastSent) return;
    if (!st.draftId && !hasContent(st.draft)) return;
    clearTimeout(timer);
    pendingBody = () => bodyOf(st);
    timer = setTimeout(() => { lastSent = s; send(st); }, 400);
  };
  function send(st) {
    const make = pendingBody; pendingBody = null; if (!make) return queue;
    queue = queue.then(async () => {
      const body = make();
      try {
        const r = st.draftId ? await API.draftPatch(st.draftId, body) : await API.draftCreate({ draft: body, lastNew: st.lastNew });
        if (GP.own() === st) GP.takeDraft(r, true);
      } catch (err) { lastSent = null; if (err.status === 404) { st.draftId = null; } else GP.fail(err, '작성 내용을 저장하지 못했어요'); }
    });
    return queue;
  }
  /* 에이전트 호출 전에 쓰던 입력을 먼저 서버에 저장한다 */
  GP.flush = async function () {
    const st = GP.own(); if (!st || !st.owner) return;
    clearTimeout(timer);
    if (snap(st) !== lastSent && (st.draftId || hasContent(st.draft))) { lastSent = snap(st); pendingBody = () => bodyOf(st); send(st); }
    await queue;
  };
  GP.ensureDraft = async function () {
    const st = GP.own();
    await GP.flush();
    if (!st.draftId) { const r = await API.draftCreate({ draft: bodyOf(st), lastNew: st.lastNew }); GP.takeDraft(r); lastSent = snap(st); }
    return st.draftId;
  };
  /* 서버 응답 → 상태. soft: 입력 저장 응답이라 화면이 고치는 값은 화면 것을 둔다(타이핑 중에 덮지 않게) */
  GP.takeDraftInto = function (st, r, soft) {
    if (!r) return;
    GP.mergeRes(r.res); if (AI.mergeReg) AI.mergeReg(r.reg);
    st.draftId = r.draftId || null;
    const server = r.draft || GP.freshDraft();
    if (soft && st.draft) {
      const keep = Object.fromEntries(CLIENT.map(k => [k, st.draft[k]]));
      const summary = st.draft.doc && server.doc ? st.draft.doc.summary : undefined;
      st.draft = Object.assign(GP.freshDraft(), server, keep);
      if (summary !== undefined && st.draft.doc) st.draft.doc.summary = summary;
    } else st.draft = Object.assign(GP.freshDraft(), server);
    st.draftPlan = r.draftPlan || null;
    if (!soft && r.lastNew !== undefined && r.lastNew !== null) st.lastNew = r.lastNew;
    if (!soft) lastSent = snap(st);
    if (GP.onDraftTaken && st === GP.own()) GP.onDraftTaken(st.draft);
  };
  GP.takeDraft = (r, soft) => GP.takeDraftInto(GP.own(), r, soft);
  /* 서버 상태를 다시 읽는다(진행 중인 작업 확인용) */
  P.pullDraft = async function () {
    const st = GP.own(); if (!st.draftId) return false;
    const before = JSON.stringify([st.draft, st.draftPlan]);
    try { GP.takeDraft(await API.draftGet(st.draftId), true); } catch (err) { if (err.status === 404) { st.draftId = null; st.draft = GP.freshDraft(); } return true; }
    return JSON.stringify([st.draft, st.draftPlan]) !== before;
  };
  /* 진행 중인 작업이 있으면 1.2초마다 서버 상태를 보고, 바뀌면 다시 그린다. 화면을 떠나거나 작업이 끝나면 멈춘다 */
  /* 다시 그리면 after() 가 감시를 새로 시작하므로, 토큰이 바뀐 이전 감시는 멈춘다(타이머가 쌓이지 않게). 10분이 지나면 멈춘다 */
  let watchT = null, watchTok = 0;
  P.busyDraft = d => !!(d.quizRun || d.diagRun || (d.doc && d.doc.status === 'reading')
    || (d.genRun && Object.values(d.genRun.rows || {}).some(x => x.st === 'run'))
    || (d.gen && ((d.gen.regenRun && Object.keys(d.gen.regenRun).length) || Object.values(d.gen.options || {}).some(o => !o.support && !o.supportFail))));
  P.watchDraft = function () {
    clearTimeout(watchT);
    const tok = ++watchTok, route0 = String(S().route).split(':')[0], until = Date.now() + 600000;
    const tick = async () => {
      const st = GP.own(); if (tok !== watchTok || !st || !GP.me() || String(st.route).split(':')[0] !== route0 || Date.now() > until) return;
      if (!P.busyDraft(st.draft)) return;
      const changed = await P.pullDraft();
      if (tok !== watchTok) return;
      if (changed && GP.S === st && String(st.route).split(':')[0] === route0) { GP.render(false); return; }
      watchT = setTimeout(tick, 1200);
    };
    if (P.busyDraft(S().draft)) watchT = setTimeout(tick, 900);
  };

  /* ───────── 확정한 로드맵 서버 동기화 ───────── */
  P.takePlan = function (r) {
    if (!r) return null;
    GP.mergeRes(r.res); if (AI.mergeReg) AI.mergeReg(r.reg);
    return GP.putRec(r.plan);
  };
  P.pullPlan = async function (pid) { try { return P.takePlan(await API.plan(pid)); } catch (err) { GP.fail(err, '로드맵을 불러오지 못했어요'); return null; } };
  let planT = null, planTok = 0;
  /* 수정안을 만드는 중이거나 수정안의 지원 조건을 확인하는 중이면 그 로드맵을 다시 읽는다 */
  P.busyPlan = R => !!(R && ((R.revision && R.revision.status === 'running') || (R.pending && !R.pending.to.def.support && !R.pending.supFail)));
  P.watchPlan = function (pid) {
    clearTimeout(planT);
    const tok = ++planTok, route0 = S().route, until = Date.now() + 600000;
    const tick = async () => {
      if (tok !== planTok || !GP.me() || S().route !== route0 || Date.now() > until) return;
      const R0 = P.R(pid); if (!P.busyPlan(R0)) return;
      const before = JSON.stringify(R0);
      const R = await P.pullPlan(pid);
      if (tok !== planTok) return;
      if (R && JSON.stringify(R) !== before && S().route === route0) { GP.render(false); return; }
      planT = setTimeout(tick, 1200);
    };
    if (P.busyPlan(P.R(pid))) planT = setTimeout(tick, 900);
  };
  /* 진행 기록 저장(API-38). 실행 기록 창의 저장하기에서만 부른다(상태·메모, 첨부는 있을 때만) */
  P.saveProgress = async function (pid, actId, body) {
    try { P.takePlan(await API.progress(pid, actId, body)); return true; } catch (err) { GP.fail(err, '진행 기록을 저장하지 못했어요'); await P.pullPlan(pid); return false; }
  };

  /* ───────── 계산 (화면 표시용 · 저장할 계획은 서버가 같은 규칙으로 다시 계산) ───────── */
  P.startOf = d => (+d.startStage >= 1 && +d.startStage <= 4 ? +d.startStage : d.diag.startStage);
  P.FIX = [['competencies', '익히게 될 역량'], ['resourceIds', '듣게 될 강좌·자료'], ['outcome', '만들 결과물'], ['known', '이미 할 수 있는 것']];
  P.dv = (d, k) => (d.fix && d.fix[k] != null ? d.fix[k] : d.diag[k]);
  P.edited = (d, k) => (k === 'start' ? P.startOf(d) !== d.diag.startStage : !!(d.fix && d.fix[k] != null));
  P.params = function (opt) {
    const h = S().draft.handoff;
    return { start: h.startStage, hours: h.prefs.weeklyHours || (opt && opt.weeklyHours) || D.autoHours, format: h.prefs.formatKey, patch: {} };
  };
  P.buildPlan = function (def, prm, base) {
    const p = Object.assign({ start: 1, hours: 4, format: 'mixed', patch: {} }, prm);
    const acts = def.acts.filter(a => a.stage >= p.start).map(a => {
      const r = resOf(a.res);
      const x = { id: a.id, stage: a.stage, title: a.title, res: a.res || null, task: !a.res, how: a.how || '', hours: a.res ? (r && r.hours != null ? r.hours : a.hours || 2) : a.hours };
      // 과제가 다루는 스킬(에이전트가 고른 팀 DB 스킬 이름 · 10/23 · 스킬 지도에서 씀). 자료 활동은 자료에 붙은 스킬을 쓴다
      if (!a.res && a.skills && a.skills.length) x.skills = a.skills.slice();
      if (p.patch[a.id]) Object.assign(x, p.patch[a.id]);
      return x;
    });
    let cum = 0;
    acts.forEach(a => { a.wFrom = Math.floor(cum / p.hours) + 1; cum += a.hours; a.wTo = Math.max(a.wFrom, Math.ceil(cum / p.hours)); });
    const weeks = Math.max(1, Math.ceil(cum / p.hours));
    const resIds = [...new Set(acts.map(a => a.res).filter(Boolean))];
    const cost = resIds.reduce((s, r) => s + ((resOf(r) || {}).cost || 0), 0);
    const costUnknown = resIds.some(r => !resOf(r) || resOf(r).cost == null);
    return { opt: def.id, name: def.name, short: def.short, tagline: def.tagline, goal: base ? base.goal : S().draft.goal, def, params: p, start: p.start, hours: p.hours, format: p.format, acts, totalH: cum, weeks, cost, costUnknown };
  };
  P.optionIds = function () { const g = S().draft.gen; return g ? D.optionOrder.filter(k => g.options[k]) : []; };
  P.opts = () => P.optionIds().map(id => P.buildPlan(S().draft.gen.options[id], P.params(S().draft.gen.options[id])));
  P.range = acts => { const a = Math.min(...acts.map(x => x.wFrom)), b = Math.max(...acts.map(x => x.wTo)); return a === b ? `${a}주차` : `${a}~${b}주차`; };
  P.prog = pl => { const R = pl && pl.rid ? S().plans[pl.rid] : P.R(); return (R && R.progress) || {}; };
  P.st = (id, pl) => (((P.prog(pl)[id] || {}).status) === 'done' ? 'done' : 'doing');
  P.count = pl => { const t = pl.acts.length, done = pl.acts.filter(a => P.st(a.id, pl) === 'done').length; return { t, done }; };
  P.nextAct = pl => pl.acts.find(a => P.st(a.id, pl) !== 'done');
  P.curStage = pl => (P.nextAct(pl) || pl.acts[pl.acts.length - 1]).stage;
  P.act = (id, pid) => { const R = P.R(pid); return ((R && R.plan) || S().draftPlan).acts.find(a => a.id === id); };
  P.stageActs = (pl, n) => pl.acts.filter(a => a.stage === n);

  const actTx = x => `${x.title} · ${x.stage}단계 · ${hrs(x.hours)}`;
  P.diff = function (a, b, pd) {
    const ch = [], push = (k, x, y) => ch.push({ k, a: x, b: y });
    if (a.opt !== b.opt) push('관점', `${a.opt} ${a.name}`, `${b.opt} ${b.name}`);
    if (pd && pd.prefsFrom && pd.prefsTo) [['format', '학습 방식'], ['cert', '자격증 계획'], ['weeks', '정해진 기간'], ['budget', '교육 예산'], ['etc', '일정·환경 제약']].forEach(([k, l]) => {
      const x = AI.prefText(k, pd.prefsFrom), y = AI.prefText(k, pd.prefsTo); if (x !== y) push(l, x, y);
    });
    if (a.start !== b.start) push('시작 단계', `${a.start}단계 ${stageName(a.start)}`, `${b.start}단계 ${stageName(b.start)}`);
    if (a.hours !== b.hours) push('주당 시간', hrs(a.hours), hrs(b.hours));
    const am = Object.fromEntries(a.acts.map(x => [x.id, x])), bm = Object.fromEntries(b.acts.map(x => [x.id, x]));
    b.acts.forEach(x => {
      const y = am[x.id];
      if (!y) push('활동 추가', '—', actTx(x));
      else if (y.title !== x.title || y.hours !== x.hours || y.stage !== x.stage) push('활동 변경', actTx(y), actTx(x));
    });
    a.acts.forEach(y => { if (!bm[y.id]) push('활동 제외', actTx(y), '—'); });
    if (a.weeks !== b.weeks) push('전체 기간', a.weeks + '주', b.weeks + '주');
    if (a.cost !== b.cost) push('예상 비용', won(a.cost), won(b.cost));
    return ch;
  };

  /* ───────── 수정 요청 → 수정안 (API-43~45) ─────────
     항목(여러 개)과 요청 문장을 받아, 로드맵을 쓴 관점의 하위 에이전트(관점을 바꾸면 새 관점)가 서버에서 수정안을 쓴다.
     확정하기 전까지 기존 로드맵은 그대로. 실패하면 가데이터로 대신하지 않고 안내하며, 다시 시도는 사용자가 눌러야만 한다 */
  P.REV_ITEMS = [
    ['hours', '주당 학습 시간', 'cond'], ['weeks', '정해진 기간', 'cond'], ['budget', '교육 예산', 'cond'], ['format', '학습 방식', 'cond'],
    ['cert', '자격증 계획', 'cond'], ['etc', '일정·환경 제약', 'cond'], ['start', '시작 단계', 'plan'], ['pid', '관점', 'plan'],
    ['remove', '활동 빼기', 'acts'], ['replace', '활동 바꾸기', 'acts'], ['add', '활동 추가', 'acts']
  ];
  P.revBase = () => S().plan;
  P.freshRev = (note, fromComment) => {
    const pl = S().plan, p = pl.prefs || {};
    return { on: {}, note: note || '', fromComment: fromComment || false, fail: null,
      v: { hours: pl.hours, weeks: p.weeks || '', budget: p.budget == null ? '' : p.budget, format: p.format || '', cert: p.cert || '', etc: p.etc || '', start: pl.start, pid: pl.opt, remove: [], replace: [], replaceHow: '', addRes: [], addTask: '' } };
  };
  const blankNum = v => v === '' || v == null;
  const addTasks = r => String(r.v.addTask || '').split('\n').map(t => t.trim()).filter(Boolean).slice(0, 5);
  P.revItemOk = (r, k) => {
    const v = r.v, pl = S().plan;
    if (k === 'hours') return blankNum(v.hours) || (+v.hours >= 0.5 && +v.hours <= 40);
    if (k === 'weeks') return blankNum(v.weeks) || (+v.weeks >= 1 && +v.weeks <= 52);
    if (k === 'budget') return blankNum(v.budget) || +v.budget >= 0;
    if (k === 'pid') return v.pid !== pl.opt;
    if (k === 'remove') return v.remove.length > 0;
    if (k === 'replace') return v.replace.length > 0;
    if (k === 'add') return v.addRes.length > 0 || addTasks(r).length > 0;
    return true;
  };
  P.revPicked = r => P.REV_ITEMS.map(([k]) => k).filter(k => r.on[k]);
  P.revKey = r => JSON.stringify([P.revPicked(r).map(k => [k, ['remove', 'replace'].includes(k) ? r.v[k] : k === 'add' ? [r.v.addRes, r.v.addTask] : r.v[k]]), r.v.replaceHow, String(r.note || '').trim()]);
  P.revBusy = () => { const R = P.R(); return !!(R && R.rev && R.rev.running); };
  P.revise = async function () {
    const R = P.R(), r = R && R.rev; if (!r || r.running) return;
    const key = P.revKey(r);
    r.running = true; r.fail = null; R.pending = null; GP.save(); GP.render(false);
    try {
      await API.revise(R.id, { rev: { on: r.on, v: r.v, note: r.note, fromComment: r.fromComment }, key });
    } catch (err) { r.running = false; r.fail = { cause: AI.cause(err) }; GP.render(false); return; }
    await P.pullPlan(R.id);
    if (S().route === 'revise:' + R.id) { GP.render(false); P.watchPlan(R.id); }
  };
  P.acceptRevision = async function () {
    const R = P.R(), rv = R && R.revision; if (!R || !R.pending || !rv) return;
    try {
      const r = await API.acceptRevision(rv.id);
      const Rn = P.takePlan(r); Rn.rev = null;
      if (Rn.plan.opt && !S().picks.includes(Rn.plan.opt)) S().picks.push(Rn.plan.opt);
      GP.save(); GP.go('confirmed:' + Rn.id);
    } catch (err) { GP.fail(err, '수정안을 확정하지 못했어요'); }
  };
  P.dropRevision = async function () {
    const R = P.R(), rv = R && R.revision, back = R ? (R.rev && R.rev.fromComment ? 'comment:' : 'roadmap:') + R.id : 'roadmap';
    try { if (rv) await API.dropRevision(rv.id); } catch (err) { GP.fail(err, '수정안을 버리지 못했어요'); return; }
    if (R) { R.pending = null; R.rev = null; R.revision = null; }
    GP.save(); GP.go(back); GP.toast('수정안을 버렸어요. 계획은 그대로예요');
  };
  P.choose = async function (id) {
    const st = GP.own();
    try { await GP.flush(); GP.takeDraft(await API.select(st.draftId, id)); GP.go('new-review'); } catch (err) { GP.fail(err, '안을 고르지 못했어요'); }
  };
  /* 확정(API-35): 새 로드맵 기록. 진행 중인 다른 로드맵은 보관하지 않고 함께 진행한다(10/14 · 묻지 않음) */
  P.confirm = async function () {
    const st = GP.own();
    try {
      await GP.flush();
      const r = await API.confirm(st.draftId);
      await GP.reload();
      GP.own().lastNew = null;
      GP.go('confirmed:' + r.planId);
    } catch (err) { GP.fail(err, '로드맵을 확정하지 못했어요'); }
  };

  /* 결과 보고서 문항 비교 표시용 */
  P.report = id => S().reports.find(r => r.id === id) || null;

  /* ───────── 검사 ───────── */
  const d = () => S().draft;
  /* 심화 질문(10/23): 고른 사람은 객관식에 모두 답해야 넘어간다('잘 모르겠어요' 포함 · 서술형은 비워도 됨) */
  const mcqDone = (dq, ans) => Object.keys(dq.mcq).every(k => (ans || {})[k]);
  const postDeepOk = p => !p.deep || !!(p.deep.status === 'ready' && p.deep.quiz && (p.deep.judge || mcqDone(p.deep.quiz, p.deep.mcq)));
  Object.assign(GP.valid, {
    goal: () => (d().goal || '').trim().length >= 4,
    quizDone: () => !!d().quiz && d().quiz.questions.every(q => d().answers[q.id]) && (!(d().deepOn && d().quiz.deep) || mcqDone(d().quiz.deep, d().deepMcq)),
    post: () => !!S().plan && S().plan.assess.questions.every(q => S().post.answers[q.id]) && !!S().post.goalSelf && postDeepOk(S().post),
    tmpStatus: () => !!(S().tmp && S().tmp.status),
    revOk: () => {
      const r = S().rev; if (!r || r.running) return false;
      const ks = P.revPicked(r);
      return ks.every(k => P.revItemOk(r, k)) && (ks.length > 0 || !!String(r.note || '').trim());
    },
    mFit: () => !!P.mgrDraft().fit, mLevel: () => !!P.mgrDraft().level
  });
  GP.valid.mComment = () => GP.valid.mFit() && GP.valid.mLevel();
  GP.valid.mEdit = () => { const k = GP.own().mcEdit, m = k && (GP.own().mgr || {})[k]; return !!(m && m.fit && m.level && P.cmChanged(m)); };
  GP.valid.editOk = () => { const e = d().edit; return !!e && !Object.values(P.editMissing(e)).some(Boolean); };

  /* ───────── 공통 조각 ───────── */
  P.page = o => `${o.back ? `<div class="wtop"><button class="back" data-go="${o.back}" aria-label="이전 화면">${icon('left')}</button><div class="wprog"></div></div>` : ''}
    ${o.eyebrow ? `<p class="eyebrow">${o.eyebrow}</p>` : ''}<h1 class="t">${o.title}</h1>${o.lead ? `<p class="lead">${o.lead}</p>` : ''}${o.body || ''}${o.foot ? `<div class="actions">${o.foot}</div>` : ''}`;
  P.next = (go, label, need) => `<button class="btn pri" data-go="${go}" ${need ? `data-need="${need}"` : ''}>${label || '다음'}</button>`;
  P.note = t => `<p class="note">${icon('info')}<span>${t}</span></p>`;
  P.errText = c => `${(c && c.user) || AI.userText(c && c.kind)}. ${AI.userTodo(c && c.kind).join(' ')}`;
  P.opsBox = (items, cls) => `<details class="ops ${cls || ''}"><summary>${icon('right')}자세히 보기 (운영자용)</summary><div class="ops-b">${items.map(([name, c]) => `<div class="ops-i">${name ? `<b>${name}</b>` : ''}
      ${c && c.text ? `<p><span>원인</span>${esc(c.text)}</p>` : ''}${c && c.hint ? `<p><span>조치</span>${esc(c.hint)}</p>` : ''}${c && c.raw ? `<p class="raw"><span>원문</span>${esc(c.raw)}</p>` : ''}</div>`).join('')}</div></details>`;
  P.loading = t => `<div class="loading"><span class="sp"></span><span>${t}</span></div>`;

  P.costB = (c, unk) => `${c ? c.toLocaleString('ko-KR') : 0}<em>원${unk ? '+' : ''}</em>`;
  P.stats = (pl, bare) => `<div class="stats ${bare ? 'bare' : ''}"><div><small>기간</small><b>${pl.weeks}<em>주</em></b></div><div><small>주당</small><b>${pl.hours}<em>시간</em></b></div><div><small>예상 비용${pl.costUnknown ? ' · 일부 비용 확인 필요' : ''}</small><b>${P.costB(pl.cost, pl.costUnknown)}</b></div></div>`;
  /* 규칙으로 채운 값(시간·단계·형식)은 '추정'으로 표시한다(팀 DB에 값이 없음 · 2026-10-21 사용자 결정) */
  P.est = (r, k) => (r && (r.estimated || []).includes(k) ? '<span class="est" title="팀 DB에 값이 없어 규칙으로 정한 추정값이에요">추정</span>' : '');
  /* 자료 그림(팀 DB image_url · 2026-10-22 사용자 결정): 원본 주소에서 바로 불러온다. 화면에 보일 때만 불러오고(lazy) 리퍼러는 보내지 않는다.
     주소가 없거나 못 불러오면 종류 아이콘(강좌·도서·자격·공식 문서·직접 수행 과제)을 보여 준다. 크기: xs 표·창 안 · 기본 목록 · lg 자료 상세 */
  const TH_TYPE = { 강좌: 'course', 도서: 'book', 자격: 'cert', '공식 문서': 'doc' };
  const TH_ICON = { course: 'play', book: 'book', cert: 'award', doc: 'file', task: 'flag' };
  P.thumb = (r, size, type) => {
    const t = type || (r && (r.type || TH_TYPE[r.kind])) || 'doc', src = r && /^https?:\/\//i.test(r.image || '') ? r.image : '';
    return `<span class="rthumb ${t}${size ? ' ' + size : ''}${src ? '' : ' none'}" aria-hidden="true">${src ? `<img src="${esc(src)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">` : ''}${icon(TH_ICON[t] || 'file')}</span>`;
  };
  P.actThumb = (a, size) => (a.task ? P.thumb(null, size, 'task') : P.thumb(resOf(a.res), size));
  /* 그림을 못 불러오면(주소 만료·차단) 아이콘으로 바꾼다. error 는 버블링되지 않아 캡처 단계에서 받는다 */
  document.addEventListener('error', e => {
    const im = e.target, box = im && im.tagName === 'IMG' ? im.parentElement : null;
    if (box && box.classList.contains('rthumb')) { box.classList.add('none'); im.remove(); }
  }, true);
  P.costText = r => (!r ? '' : r.cost == null ? (r.kind === '자격' ? '응시료 확인 필요' : r.kind === '도서' ? '가격 확인 필요' : '비용 확인 필요') : r.cost ? won(r.cost) : '무료');
  P.actMeta = function (a) {
    if (a.task) return '직접 수행 과제';
    const r = resOf(a.res);
    if (!r) return '등록 자료 (정보를 불러오지 못했어요)';
    return `${r.kind} · ${esc(r.provider)}${r.real ? '' : ' · 가상'} · ${P.costText(r)}`;
  };
  P.stt = (id, pl) => { const s = P.st(id, pl); return `<span class="stt ${s}" aria-label="${s === 'done' ? '완료' : '진행 중'}">${s === 'done' ? icon('check') : ''}</span>`; };
  P.stagesView = function (pl, o) {
    o = o || {};
    const prog = P.prog(pl);
    return D.stages.filter(st => st.n >= pl.start).map(st => {
      const acts = P.stageActs(pl, st.n); if (!acts.length) return '';
      return `<div class="stage"><div class="stage-h"><span class="no">${st.n}</span><b>${st.name}</b><span class="end">${P.range(acts)}${o.status ? ` · ${acts.filter(a => P.st(a.id, pl) === 'done').length}/${acts.length} 완료` : ''}</span></div>
        <ul class="acts">${acts.map(a => { const memo = o.memo && (prog[a.id] || {}).memo; return `<li>${o.status ? P.stt(a.id, pl) : ''}${P.actThumb(a)}<div class="tx">${esc(a.title)}<small>${P.actMeta(a)}</small>${memo ? `<small class="memo">메모 · ${esc(memo)}</small>` : ''}</div><span class="h">${hrs(a.hours)}${a.res ? P.est(resOf(a.res), 'hours') : ''}</span></li>`; }).join('')}</ul></div>`;
    }).join('');
  };
  P.diffView = pd => {
    const ch = P.diff(pd.from, pd.to, pd), same = pd.from.opt === pd.to.opt;
    return `${pd.summary ? `<p class="rv-sum">${icon('spark')}<span>${esc(pd.summary)}</span></p>` : ''}
      <div class="diff">${ch.length ? ch.map(c => `<div class="d"><span class="k">${esc(c.k)}</span><span class="ab"><s>${esc(c.a)}</s>${icon('arrow')}<span class="to">${esc(c.b)}</span></span></div>`).join('') : '<div class="d"><span class="k">변경</span><span>바뀌는 내용이 없어요</span></div>'}</div>
      ${pd.notes && pd.notes.length ? `<div class="callout soft rv-notes">${icon('info')}<div><b>요청 중 반영하지 못한 것</b><ul class="plain-list">${pd.notes.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div></div>` : ''}
      <p class="note">${icon('info')}<span>목표는 그대로예요.${same ? ` 관점(${esc(pd.from.opt)} ${esc(pd.from.name)})도 그대로예요.` : ''} 같은 활동의 진행 기록(완료·메모)은 이어져요.${pd.request ? ` 요청 내용: “${esc(pd.request)}”` : ''}</span></p>`;
  };
  P.commentView = c => {
    const fit = (D.commentFit.find(x => x[0] === c.fit) || [])[1], lv = (D.commentLevel.find(x => x[0] === c.level) || [])[1];
    return `<div class="cmt">
      <div class="card"><p class="q">업무 적합성 · 담당 업무와 부서 AI 사업에 맞는가</p><p><b>${esc(fit || '의견 없음')}</b>${c.fitText ? ` — ${esc(c.fitText)}` : ''}</p></div>
      <div class="card"><p class="q">수준·기간·분량</p><p><b>${esc(lv || '의견 없음')}</b>${c.levelText ? ` — ${esc(c.levelText)}` : ''}</p></div>
      ${c.free ? `<div class="card"><p class="q">자유 의견</p><p>${esc(c.free)}</p></div>` : ''}</div>`;
  };
  P.ansLabel = v => AI.ansLabel(v);

  GP.act['pre-answers'] = pid => {
    const R = P.R(pid), pl = R && R.plan, A = pl ? pl.assess : { questions: (S().draft.quiz || { questions: [] }).questions, answers: S().draft.answers };
    GP.sheet(`<div class="list">${A.questions.map(q => `<div class="li"><div class="tx"><small>${esc(q.area)}</small><b style="font-weight:500">${esc(q.text)}</b></div><span class="end">${esc(P.ansLabel(A.answers[q.id]))}</span></div>`).join('')}</div>
      ${P.note('처음 응답한 원본이에요. 진단 에이전트가 계산한 수준값은 사후 비교용으로 서버에만 저장하고 화면에 보여주지 않아요.')}`, { title: '사전 점검 응답', sub: pl ? pl.goal : '', wide: true });
  };
  GP.act.versions = function (pid) {
    const R = P.R(pid); if (!R) return;
    const vs = R.versions.slice().reverse();
    GP.sheet(`<div class="list">${vs.map(v => `<div class="li"><span class="idx ${v.version === R.plan.version ? 'on' : ''}">v${v.version}</span><div class="tx"><b>${esc(v.why)}</b><small>${esc(v.confirmedAt)} · ${v.weeks}주 · 주 ${v.hours}시간 · ${won(v.cost)}</small></div></div>`).join('')}</div>${P.note('계획을 고쳐 확정할 때마다 새 버전으로 쌓여요. 이전 버전은 지우지 않아요.')}`, { title: '계획 버전 이력', sub: R.plan.goal });
  };

  P.hero = (title, lead, foot) => `<div class="hero"><h1 class="t">${title}</h1><p class="lead" style="margin-bottom:0">${lead}</p>${foot ? `<div class="actions">${foot}</div>` : ''}</div>`;
  P.noPlan = () => (GP.draftActive()
    ? P.hero('작성 중인 로드맵이 있어요', esc(S().draft.goal), `<button class="btn pri" data-go="${GP.newRoute()}">이어서 작성하기</button>`)
    : P.hero('아직 확정한 로드맵이 없어요', '새 로드맵 작성에서 목표와 학습 여건을 적고 짧은 점검에 답하면 관점이 다른 3안을 받아볼 수 있어요.', `<button class="btn pri" data-go="new-goal">새 로드맵 작성</button>`));
  P.commentAlert = R => {
    const nw = P.newComments(R), n = nw.length, edited = n && nw.every(c => c.editedAt);
    return n ? `<button class="alert" data-go="comment:${R.id}">${icon('chat')}<span class="grow"><b>${esc(P.cmBy(nw.slice(-1)[0]))} 님이 ${edited ? '보낸 코멘트를 고쳤어요' : '이 로드맵에 코멘트를 남겼어요'}${n > 1 ? ` (${n}개)` : ''}</b><br><span class="small muted">평가가 아닌 계획 조정 의견이에요</span></span>${icon('right')}</button>` : '';
  };

  /* ───────── 실행 기록 창 ───────── */
  /* 진행 상태는 이 창에서만 바꾼다(홈·내 로드맵 활동 줄은 보여 주기만 · 10/23). 저장하기를 눌러야 반영된다 */
  P.STATUS = [['doing', '진행 중'], ['done', '완료']];
  let recFile = null;
  /* 자료 상자(10/23 사용자 결정): 그림을 크게, 버튼 두 개 — '원본 열기'(강좌·도서 사이트를 새 탭) + '자료 정보'(앱 안 자료 상세).
     원본 주소가 없거나 http(s)가 아니면 '자료 정보'만 둔다 */
  const recRes = (a, r) => {
    const url = r && /^https?:\/\//i.test(r.url || '') ? r.url : '';
    return `<div class="rec-res"><div class="rec-res-h">${P.thumb(r, 'md')}<div class="tx"><b>${esc(r ? r.title : a.title)}</b>${r ? `<small>${esc(r.kind)} · ${esc(r.provider)}${r.real ? '' : ' · 가상 자료'}</small>` : ''}</div></div>
      <div class="rec-res-b">${url ? `<a class="btn line" href="${esc(url)}" target="_blank" rel="noopener noreferrer">원본 열기${icon('out')}</a>` : ''}<button class="btn line" data-go="res:${a.res}">자료 정보</button></div></div>`;
  };
  P.recBody = function (a, R) {
    const pr = R.progress[a.id] || {}, r = a.res ? resOf(a.res) : null, t = S().tmp;
    return `<p class="small muted">${a.stage}단계 ${stageName(a.stage)} · ${a.wFrom === a.wTo ? a.wFrom : a.wFrom + '~' + a.wTo}주차 · ${hrs(a.hours)}</p>
      <p style="font-weight:650;font-size:17px;margin:4px 0 14px">${esc(a.title)}</p>
      ${a.task ? `<div class="callout soft">${icon('flag')}<div><b>직접 수행 과제</b><br>${esc(a.how)}</div></div>` : recRes(a, r)}
      <div class="field rec-st"><span class="flabel" id="recStL">진행 상태</span><div class="mini-seg" role="radiogroup" aria-labelledby="recStL">${P.STATUS.map(([v, l]) => `<label><input type="radio" name="recst" value="${v}" data-bind="tmp.status" ${t.status === v ? 'checked' : ''}>${l}</label>`).join('')}</div></div>
      <div class="field"><label>메모 <span class="muted small">선택</span></label><textarea class="textarea sm" data-bind="tmp.memo" placeholder="한 일, 막힌 점, 다음에 할 일">${esc(t.memo)}</textarea></div>
      <div class="field"><label>결과물·수료증 <span class="muted small">선택 · 서버에 보관(배포 때는 파일 저장소)</span></label>${pr.file ? `<p class="small">${icon('file')} ${esc(pr.file.name)}</p>` : ''}<input class="input" type="file" id="recFile"></div>
      ${P.note(`메모·첨부는 나만 봐요.${P.mySup() ? ` 완료 여부는 부서장 ${esc(P.mySup().name)} 님에게 진행 상태로 보여요.` : ''} 자료를 내지 않았다고 하지 않은 것으로 보지 않아요.`)}`;
  };
  GP.act['rec-open'] = arg => {
    const [pid, id] = String(arg).split('|'), R = P.R(pid), a = R && R.plan.acts.find(x => x.id === id); if (!a) return;
    const pr = R.progress[id] || {};
    S().tmp = { pid, id, status: P.st(id, R.plan), memo: pr.memo || '' }; recFile = null; GP.save();
    const ov = GP.sheet(P.recBody(a, R), { title: '실행 기록', sub: R.plan.goal, foot: '<button class="btn pri" data-act="rec-save" data-need="tmpStatus">저장하기</button>' });
    const fi = ov.querySelector('#recFile'); if (fi) fi.addEventListener('change', () => { recFile = fi.files && fi.files[0] || null; });
  };
  GP.act['rec-save'] = async () => {
    const t = S().tmp; if (!t) return;
    const body = { status: t.status, memo: t.memo || '' };
    try { if (recFile) { const up = await API.attach(t.pid, t.id, recFile); body.file = { fileId: up.fileId, name: up.name, size: up.size }; } } catch (err) { GP.fail(err, '파일을 올리지 못했어요'); return; }
    const ok = await P.saveProgress(t.pid, t.id, body);
    if (!ok) return;
    S().tmp = null; recFile = null; GP.save(); GP.closeSheet(); GP.render(false); GP.toast('실행 기록을 저장했어요');
  };

  /* ───────── 수정 요청 양식 (10/14) ───────── */
  P.ensureRev = () => { const R = P.R(), pl = R && R.plan; if (pl && (!R.rev || !R.rev.v)) { R.rev = P.freshRev(); GP.save(); } return R && R.rev; };
  const curText = (k, pl) => {
    const p = pl.prefs || {};
    if (k === 'hours') return `주 ${pl.hours}시간${+p.hours > 0 ? '' : ' (에이전트가 정함)'}`;
    if (k === 'cert') return AI.certNameOf(p) || '계획 없음';
    if (['weeks', 'budget', 'format', 'etc'].includes(k)) return AI.prefText(k, p);
    if (k === 'start') return `${pl.start}단계 ${stageName(pl.start)}`;
    if (k === 'pid') return `${pl.opt} ${pl.name}`;
    return `활동 ${pl.acts.length}개`;
  };
  const REV_MISS = { hours: '0.5~40 사이로 적거나 비워 주세요', weeks: '1~52 사이로 적거나 비워 주세요', budget: '0 이상으로 적거나 비워 주세요', pid: '지금과 다른 관점을 골라 주세요',
    remove: '뺄 활동을 하나 이상 골라 주세요', replace: '바꿀 활동을 하나 이상 골라 주세요', add: '넣을 자료를 고르거나 과제를 적어 주세요' };
  /* 자료 고르기: 팀 DB 자료가 수천 건이라 검색해서 고른다(관련 스킬 순 · 고른 것은 위에 고정) */
  P.resPicker = function (path, picked, opts) {
    const box = 'rp-' + path.replace(/\W/g, '');
    return `<div class="rpick" data-rp="${box}" data-path="${path}" data-stage="${(opts && opts.stage) || 0}" data-exclude="${esc((opts && opts.exclude || []).join(','))}">
      ${picked.length ? `<div class="choices">${picked.map(id => { const x = resOf(id); return `<label class="choice"><input type="checkbox" value="${id}" data-bind-arr="${path}" checked>${P.thumb(x)}<span class="tx">${esc(x ? x.title : id)}<small>${x ? `${x.stage || '-'}단계 · ${x.kind} · ${esc(x.provider)} · ${hrs(x.hours || 0)} · ${P.costText(x)}` : ''}</small></span><span class="ck">${icon('check')}</span></label>`; }).join('')}</div>` : ''}
      <div class="addrow"><input class="input" data-rp-q placeholder="자료 검색 (예: RAG, Python, 프롬프트)" autocomplete="off" aria-label="학습 자료 검색"><button type="button" class="btn line sm" data-act="rp-search" data-arg="${box}">검색</button></div>
      <div class="choices rp-list" data-rp-list><p class="muted small">검색하면 등록 자료(팀 DB 강좌·도서·공식 자료)가 보여요. 시작 단계 이후 자료만 보여요.</p></div></div>`;
  };
  GP.act['rp-search'] = async (box) => {
    const el = document.querySelector(`[data-rp="${box}"]`); if (!el) return;
    const q = el.querySelector('[data-rp-q]').value.trim(), list = el.querySelector('[data-rp-list]'), path = el.dataset.path;
    const picked = new Set(GP.getP(path) || []);
    list.innerHTML = P.loading('찾는 중…');
    try {
      const r = await API.resources({ q, stage: el.dataset.stage || 0, exclude: el.dataset.exclude || '', certs: 0, limit: 15 });
      GP.mergeRes(Object.fromEntries(r.items.map(x => [x.id, x])));
      list.innerHTML = r.items.filter(x => !picked.has(x.id)).map(x => `<label class="choice"><input type="checkbox" value="${x.id}" data-bind-arr="${path}">${P.thumb(x)}<span class="tx">${esc(x.title)}<small>${x.stage || '-'}단계${P.est(x, 'stage')} · ${x.kind} · ${esc(x.provider)} · ${hrs(x.hours || 0)}${P.est(x, 'hours')} · ${P.costText(x)}</small></span><span class="ck">${icon('check')}</span></label>`).join('')
        + `<p class="small muted">${r.total}건 중 ${r.items.length}건${r.total > r.items.length ? ' · 검색어를 더 적으면 좁혀져요' : ''}</p>`;
    } catch (err) { list.innerHTML = `<p class="small" style="color:var(--warn)">${esc(AI.cause(err).user)}</p>`; }
  };
  document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.matches && e.target.matches('[data-rp-q]') && !e.isComposing) { e.preventDefault(); GP.act['rp-search'](e.target.closest('[data-rp]').dataset.rp); } });
  function revCtl(k, r, pl) {
    const v = r.v, lab = (P.REV_ITEMS.find(x => x[0] === k) || [])[1];
    const num = (unit, attrs, ph, help) => `<div class="unit"><input class="input num" type="number" ${attrs} data-bind="rev.v.${k}" value="${esc(v[k])}" placeholder="${ph}" aria-label="${lab}"><span>${unit}</span></div><small class="muted">${help}</small>`;
    const actList = (path, sel) => `<div class="choices">${pl.acts.map(a => `<label class="choice"><input type="checkbox" value="${a.id}" data-bind-arr="${path}" ${sel.includes(a.id) ? 'checked' : ''}>${P.actThumb(a)}<span class="tx">${esc(a.title)}<small>${a.stage}단계 · ${P.actMeta(a)} · ${hrs(a.hours)}${P.st(a.id) === 'done' ? ' · 완료' : ''}</small></span><span class="ck">${icon('check')}</span></label>`).join('')}</div>`;
    if (k === 'hours') return num('시간 / 주', 'min="0.5" max="40" step="0.5"', '알아서', '0.5~40시간. 비우면 관점과 기간에 맞게 에이전트가 정해요');
    if (k === 'weeks') return num('주 안에', 'min="1" max="52" step="1"', '없음', '1~52주. 비우면 기간을 정하지 않아요');
    if (k === 'budget') return num('원', 'min="0" step="10000"', '알아서', '0을 넣으면 무료 자료만 써요. 비우면 알아서 골라요');
    if (k === 'format') return `<select class="input df-sel ${v.format ? '' : 'empty'}" data-bind="rev.v.format" aria-label="${lab}"><option value="">알아서</option>${D.formatOpts.map(([x, l]) => `<option value="${x}" ${v.format === x ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    if (k === 'cert') return `${P.certPick('rev.v.cert', v.cert)}<small class="muted">분야를 고른 뒤 자격을 골라 주세요. ‘계획 없음’이면 자격 준비 활동을 빼요</small>`;
    if (k === 'etc') return `<textarea class="textarea sm" data-bind="rev.v.etc" maxlength="500" aria-label="${lab}" placeholder="예: 다음 달 둘째 주는 출장이 많아요. 평일 저녁에만 공부할 수 있어요.">${esc(v.etc)}</textarea>`;
    if (k === 'start') return `<div class="chips">${D.stages.map(s => `<label class="chip"><input type="radio" name="rv-start" value="${s.n}" data-bind="rev.v.start" ${+v.start === s.n ? 'checked' : ''}>${s.n}단계 ${s.name}${s.n === pl.start ? ' (지금)' : ''}</label>`).join('')}</div>`;
    if (k === 'pid') return `<div class="chips">${D.optionOrder.map(id => `<label class="chip"><input type="radio" name="rv-pid" value="${id}" data-bind="rev.v.pid" data-rerender ${v.pid === id ? 'checked' : ''}>${id} ${esc(D.perspectives[id].name)}${id === pl.opt ? ' (지금)' : ''}</label>`).join('')}</div><small class="muted">고른 관점의 하위 에이전트가 진단 내용과 바뀐 조건으로 로드맵을 새로 써요</small>`;
    if (k === 'remove') return actList('rev.v.remove', v.remove);
    if (k === 'replace') return `${actList('rev.v.replace', v.replace)}<input class="input" data-bind="rev.v.replaceHow" value="${esc(v.replaceHow)}" maxlength="200" placeholder="어떻게 바꿀까요? (선택) 예: 영상 강의로, 더 짧은 자료로" aria-label="바꿀 방향">`;
    if (k === 'add') {
      const have = pl.acts.map(a => a.res).filter(Boolean);
      return `${P.resPicker('rev.v.addRes', v.addRes, { exclude: have })}
        <textarea class="textarea sm" data-bind="rev.v.addTask" maxlength="400" aria-label="직접 할 과제" placeholder="직접 할 과제를 한 줄에 하나씩 적어 주세요 (선택)&#10;예: 부서 FAQ 20건으로 답변 품질 점검하기">${esc(v.addTask)}</textarea><small class="muted">자격증은 위 ‘자격증 계획’에서 바꿔요</small>`;
    }
    return '';
  }
  const revRow = (k, r, pl) => {
    const lab = (P.REV_ITEMS.find(x => x[0] === k) || [])[1], on = !!r.on[k];
    return `<div class="ef rv${on ? ' on' : ''}"><label class="ef-l rv-l"><input type="checkbox" data-act="rev-on" data-arg="${k}" ${on ? 'checked' : ''}><span>${lab}<small>지금: ${esc(curText(k, pl))}</small></span></label>
      <div class="ef-c">${on ? `${revCtl(k, r, pl)}${REV_MISS[k] ? `<span class="miss" data-rvmiss="${k}" hidden>${icon('info')}${REV_MISS[k]}</span>` : ''}` : `<div><button type="button" class="link quiet rv-pick" data-act="rev-on" data-arg="${k}">${icon('edit')}바꾸기</button></div>`}</div></div>`;
  };
  const goalRow = pl => `<div class="ef rv"><div class="ef-l rv-l nock"><span>목표<small>지금: ${esc(pl.goal)}</small></span></div><div class="ef-c">
      <p class="small muted" style="margin:0">목표가 바뀌면 사전 점검부터 다시 해야 해서 새 로드맵으로 만들어요. 지금 로드맵은 새 로드맵을 확정할 때까지 그대로예요.</p>
      <div>${GP.draftActive() ? `<button type="button" class="btn line sm" data-go="${GP.newRoute()}">${icon('pen')}작성 중인 새 로드맵 이어서 하기</button>` : `<button type="button" class="btn line sm" data-act="rev-newgoal">${icon('pen')}지금 조건으로 새 로드맵 작성</button>`}</div></div></div>`;
  P.revForm = function (r, pl) {
    const grp = (g, title) => `<div class="card rv-g"><h2 class="st">${title}</h2><div class="efs">${P.REV_ITEMS.filter(x => x[2] === g).map(([k]) => revRow(k, r, pl)).join('')}${g === 'plan' ? goalRow(pl) : ''}</div></div>`;
    return `${grp('cond', '학습 여건')}${grp('plan', '로드맵 구성')}${grp('acts', '활동')}
      <div class="card rv-g"><h2 class="st">요청 내용 <span class="small muted">선택 · 항목 없이 문장만 적어도 돼요</span></h2>
        ${r.fromComment ? '<p class="small muted" style="margin:0 0 8px">부서장 코멘트로 채웠어요. 반영하지 않을 부분은 지우고, 덧붙일 내용을 적어 주세요.</p>' : ''}
        <textarea class="textarea" data-bind="rev.note" maxlength="600" aria-label="요청 내용" placeholder="예: 평일 저녁에만 시간이 나요. 실습을 늘려 주세요.">${esc(r.note)}</textarea></div>`;
  };
  GP.act['rev-on'] = k => { const r = P.ensureRev(); if (!r) return; r.on[k] = !r.on[k]; GP.save(); GP.render(false); };
  GP.act['rev-start'] = pid => {
    GP.closeSheet(); const R = P.focus(pid || S().cur); if (!R || R.status !== 'active') return;
    if (!(R.revision && R.revision.status === 'running')) { R.rev = P.freshRev(); R.pending = null; }
    GP.save(); GP.go('revise:' + R.id);
  };
  GP.act['rev-make'] = () => { if (GP.valid.revOk()) P.revise(); };
  GP.act['rev-newgoal'] = () => {
    const pl = S().plan; if (!pl) return;
    const st = GP.own();
    st.draft = GP.freshDraft(); st.draft.prefs = Object.assign(AI.emptyPrefs(), clone(pl.prefs || {})); st.draftId = null;
    st.draftPlan = null; S().rev = null; GP.save(); GP.go('new-goal');
    GP.toast('지금 로드맵의 학습 여건을 채워 뒀어요. 새 목표를 적어 주세요');
  };
  GP.act['rev-accept'] = () => P.acceptRevision();
  GP.act['rev-drop'] = () => P.dropRevision();
  GP.act.confirm = () => P.confirm();

  /* ───────── 여러 메뉴가 함께 쓰는 화면 ───────── */
  const scr = GP.screens;
  P.planGuard = (name, fallback, needActive) => param => {
    const R = param && S().plans[param];
    if (R && (!needActive || R.status === 'active')) { S().cur = R.id; return null; }
    if (R) return 'roadmap:' + R.id;
    const act = P.recs('active');
    return act.length === 1 ? `${name}:${act[0].id}` : fallback;
  };
  scr.confirmed = {
    nav: 'roadmap', title: '로드맵 확정', guard: P.planGuard('confirmed', 'roadmap'),
    render() {
      const pl = S().plan; if (!pl) return P.noPlan();
      const first = pl.version === 1, others = P.recs('active').filter(R => R.id !== pl.rid).length, sup = P.mySup();
      return `<div class="badge-ico">${icon('check')}</div>
        <p class="eyebrow">${esc(pl.name)} · v${pl.version}</p>
        <h1 class="t lg">${first ? '로드맵을 확정했어요' : '수정안을 확정했어요'}</h1>
        <p class="lead">${first ? '첫 활동부터 시작해 보세요. 실행한 만큼 기록하면 돼요.' : `${esc(pl.why)} 내용을 새 버전으로 저장했어요. 이전 버전도 남아 있어요.`}</p>
        <div class="card flat"><div class="stack">
          ${pl.selection ? `<div class="row top">${icon('spark')}<span>고른 안은 <b>${esc(pl.selection.perspective)} ${esc(pl.selection.name)}</b>이에요. 로드맵 계획 에이전트의 ${esc(pl.selection.perspective)} 하위 에이전트가 썼어요. 이 선택만 저장하고, 고르지 않은 두 안은 저장하지 않아요.</span></div>` : ''}
          ${first && others ? `<div class="row top">${icon('map')}<span>진행 중인 다른 로드맵 ${others}개도 그대로 함께 진행돼요.</span></div>` : ''}
          <div class="row top">${icon('users')}<span>${sup ? `내 계획을 보는 부서장 ${esc(sup.name)} 님은 <b>확정한 로드맵, 진행 상태, 결과 보고서</b>를 볼 수 있어요.` : '내 계획을 보는 부서장이 없어 로드맵과 보고서는 나만 봐요.'}</span></div>
          <div class="row top">${icon('lock')}<span>점검 응답 원본·진단 결과·활동 메모·첨부와 작성 중인 로드맵은 나만 봐요.${sup ? ' 결과 보고서에 들어 있는 문항별 사전→사후 응답 변화는 부서장도 볼 수 있어요.' : ''}</span></div>
          <div class="row top">${icon('db')}<span>확정한 로드맵은 팀 DB에 저장돼요(로드맵·단계·자료 연결). 다른 PC에서 로그인해도 같은 기록이 보여요.</span></div>
        </div></div>
        <div class="actions"><button class="btn pri" data-go="home">로드맵 시작하기</button><button class="btn line" data-go="roadmap:${pl.rid}">로드맵 보기</button></div>
        ${first && sup ? P.note(`시연: 로그아웃한 뒤 부서장 ${esc(sup.name)}(사번 ${esc(sup.code)})으로 로그인하면 이 로드맵에 코멘트를 남길 수 있어요.`) : ''}`;
    }
  };

  scr.revise = {
    nav: 'roadmap', title: '수정 요청', width: 'wide', guard: P.planGuard('revise', 'roadmap', true),
    render() {
      const base = P.revBase(); if (!base) return P.page({ title: '고칠 로드맵이 없어요', body: P.noPlan() });
      const R = P.R(), r = P.ensureRev(), pd = S().pending, busy = !!r.running;
      const pid = r.on.pid && r.v.pid !== base.opt ? r.v.pid : base.opt, agent = `${pid} ${D.perspectives[pid].name}`;
      const cm = r.fromComment && (R.comments || []).find(c => c.id === r.fromComment);
      /* 요청 내용을 채운 뒤 부서장이 코멘트를 고쳤으면(10/23 코멘트 수정) 알리고, 고친 내용으로 다시 채울 수 있게 한다 */
      const stale = !!(cm && r.cmStamp && cm.stamp !== r.cmStamp);
      const cmt = cm ? `<div class="callout soft rv-cmt">${icon('chat')}<div><b>부서장 코멘트 · ${esc(P.cmBy(cm))} · ${esc(cm.at)}${cm.editedAt ? ` · 수정됨 ${esc(cm.editedAt)}` : ''}</b><br><span class="small muted">${stale ? '이 수정 요청을 시작한 뒤 부서장이 코멘트를 고쳤어요. 아래가 고친 코멘트이고, ‘요청 내용’은 고치기 전 내용이에요.' : '아래 ‘요청 내용’에 채워 뒀어요. 반영할 부분만 남기고 수정안을 만들어 주세요.'} 확정하면 이 코멘트가 ‘v${base.version + 1}에 반영’으로 바뀌어요.</span>${stale && !busy ? '<div class="actions cm-act"><button class="btn line sm" data-act="rev-refill">고친 코멘트로 요청 내용 다시 채우기</button></div>' : ''}</div></div>${P.commentView(cm)}` : '';
      const fail = r.fail && r.fail.cause ? r.fail.cause : null;
      const make = `${fail && !busy ? '' : `<div class="actions rv-act"><button class="btn ${pd ? 'line' : 'pri'}" data-act="rev-make" data-need="revOk">${busy ? '수정안을 만드는 중…' : pd ? '수정안 다시 만들기' : '수정안 만들기'}</button></div>`}
        <p class="small muted rv-hint" data-rvhint hidden>바꿀 항목을 고르거나 요청 내용을 적어 주세요. 고른 항목의 값이 맞는지도 확인해 주세요.</p>`;
      let out = '';
      if (busy) out = `<div class="agents">${P.agentRow({ st: 'run', name: `${agent} · 수정안 작성`, sub: P.runSub('roadmap', '고른 항목과 요청 내용을 반영하고 있어요') })}</div>`;
      else if (fail) out = P.failPage({
        title: '수정안을 만들지 못했어요', desc: `${esc(agent)} 에이전트가 수정안을 쓰지 못했어요. 지금 로드맵은 그대로이고, 고른 항목과 요청 내용도 그대로 남아 있어요.`,
        cause: esc(P.errText(fail)),
        body: `<div class="agents">${P.agentRow({ st: 'fail', name: `${agent} · 수정안 작성`, sub: AI.live() ? `${AI.PROV[AI.mode()]} · ${esc(AI.modelName('roadmap'))}` : '', tag: '오류 발생', tagCls: 'fail' })}</div>`,
        ops: P.opsBox([['', fail]]),
        foot: `<button class="btn pri" data-act="rev-make" data-need="revOk">${icon('retry')}다시 시도하기</button>`
      });
      else if (pd) out = `<div class="sec-h"><h2 class="st">수정안</h2>${pd.source && pd.source !== 'mock' ? `<span class="tag acc">${AI.PROV[pd.source] || 'API'} 작성</span>` : '<span class="tag">가데이터</span>'}</div>
        ${P.revKey(r) !== pd.key ? P.note('수정안을 만든 뒤 고른 항목이나 요청 내용을 바꿨어요. 바뀐 내용으로 보려면 ‘수정안 다시 만들기’를 눌러 주세요.') : ''}${P.diffView(pd)}${P.revSupView ? P.revSupView(pd) : ''}`;
      return P.page({
        back: (r.fromComment ? 'comment:' : 'roadmap:') + base.rid, eyebrow: `${esc(base.name)} · v${base.version} · ${esc(base.goal)}`,
        title: '무엇을 바꿀까요?', lead: `여러 항목을 함께 골라도 돼요. 고른 항목과 요청 내용을 ${esc(agent)} 에이전트가 함께 보고 수정안을 먼저 보여 드려요. 확정하기 전까지 지금 로드맵은 그대로예요.`,
        body: `${cmt}${P.revForm(r, base)}${make}${out ? `<div class="sec" id="diffSec">${out}</div>` : ''}`,
        foot: pd && !busy && !fail ? `<button class="btn pri" data-act="rev-accept">v${base.version + 1}로 확정하기</button><button class="btn line" data-act="rev-drop">취소</button>` : ''
      });
    },
    /* 새로 고침·재접속: 서버가 이어서 만들던 수정안·지원 조건 확인을 다시 읽는다(새 작업을 만들지 않음) */
    after() { const R = P.R(); if (R) P.watchPlan(R.id); }
  };

  /* 부서장 코멘트 (10/14): 쌓이고, 상태(새·확인함·vN에 반영)가 직원·부서장 화면에 같이 보인다. 답글은 없다 */
  P.cmTag = (c, mgr) => (c.status === 'applied' ? `<span class="tag ok">v${c.appliedVersion || ''}에 반영</span>`
    : c.status === 'read' ? '<span class="tag line">확인함</span>' : `<span class="tag acc">${mgr ? '확인 전' : '새 코멘트'}</span>`);
  P.cmMine = c => !!(c.byCode && c.byCode === (GP.me() || {}).code);
  P.cmItem = (c, foot, mgr) => `<div class="cm-item"><div class="cm-h"><b>${mgr && P.cmMine(c) ? '보낸 코멘트' : esc(P.cmBy(c))}</b><span class="small muted">${esc(c.at)}${c.editedAt ? ` · 수정됨 ${esc(c.editedAt)}` : ''}</span>${P.cmTag(c, mgr)}</div>${P.commentView(c)}${foot || ''}</div>`;
  scr.comment = {
    nav: 'roadmap', title: '부서장 코멘트',
    guard: param => {
      if (param && S().plans[param]) { S().cur = param; return null; }
      const R = P.recs('active').find(x => P.newComments(x).length) || P.recs().find(x => (x.comments || []).length);
      return R ? 'comment:' + R.id : 'home';
    },
    render() {
      const R = P.R(), pl = R.plan, list = (R.comments || []).slice().reverse(), live = R.status === 'active', n = P.newComments(R).length;
      if (!list.length) return P.page({ back: 'roadmap:' + R.id, title: '받은 코멘트가 없어요', lead: '이 로드맵에 부서장이 의견을 남기면 여기에 쌓여요.' });
      const foot = c => (live && c.status !== 'applied' ? `<div class="actions cm-act"><button class="btn pri sm" data-act="comment-apply" data-arg="${R.id}|${c.id}">이 의견으로 수정안 받기</button>${c.status === 'new' ? `<button class="btn line sm" data-act="comment-read" data-arg="${R.id}|${c.id}">확인했어요</button>` : ''}</div>` : '');
      return P.page({
        back: 'roadmap:' + R.id, eyebrow: `${esc(pl.name)} · v${pl.version} · 부서장 코멘트 ${list.length}개`, title: n ? '로드맵에 대한 의견이 왔어요' : '받은 코멘트', lead: esc(pl.goal),
        body: `<div class="stack">${list.map(c => P.cmItem(c, foot(c))).join('')}</div>
          <div class="callout soft" style="margin-top:16px">${icon('info')}<div>코멘트만으로 로드맵이 바뀌지는 않아요. ‘이 의견으로 수정안 받기’를 누르면 코멘트를 채운 수정 요청 화면이 열려요. 반영할 부분만 남겨 수정안을 만들고, 내가 확정해야 로드맵이 바뀌어요. 확인했는지와 몇 번째 버전에 반영했는지는 부서장에게도 보여요.</div></div>`
      });
    }
  };
  const commentReq = c => {
    const lb = (list, v) => (list.find(x => x[0] === v) || [])[1] || '';
    const fit = c.fit && c.fit !== 'none' ? lb(D.commentFit, c.fit) : '', lv = c.level && c.level !== 'none' ? lb(D.commentLevel, c.level) : '';
    const line = (k, pick, text) => (text ? `${k}${pick ? `(${pick})` : ''}: ${text}` : pick ? `${k}: ${pick}` : '');
    return [line('업무 적합성', fit, c.fitText), line('수준·기간·분량', lv, c.levelText), c.free && `자유 의견: ${c.free}`].filter(Boolean).join('\n');
  };
  const cmOf = arg => { const [pid, cid] = String(arg).split('|'), R = P.R(pid); return { R, c: R && (R.comments || []).find(x => x.id === cid) }; };
  GP.act['comment-apply'] = arg => {
    const { R, c } = cmOf(arg); if (!c || R.status !== 'active') return;
    P.focus(R.id); R.rev = Object.assign(P.freshRev(commentReq(c), c.id), { cmStamp: c.stamp }); R.pending = null; GP.save(); GP.go('revise:' + R.id);
  };
  GP.act['rev-refill'] = () => {
    const R = P.R(), r = R && R.rev, c = r && r.fromComment && (R.comments || []).find(x => x.id === r.fromComment);
    if (!c || r.running) return;
    r.note = commentReq(c); r.cmStamp = c.stamp; GP.save(); GP.render(false);
    GP.toast('고친 코멘트로 요청 내용을 다시 채웠어요');
  };
  GP.act['comment-read'] = async arg => {
    const { R, c } = cmOf(arg); if (!c) return;
    try { P.takePlan(await API.commentRead(R.id, c.id)); GP.render(false); GP.toast('코멘트를 확인했어요 · 부서장에게 ‘확인함’으로 보여요'); } catch (err) { GP.fail(err, '확인 표시를 저장하지 못했어요'); }
  };

  scr.checks = {
    nav: 'checks', title: '점검·보고서', width: 'wide',
    render() {
      const s = S(), all = P.recs(), act = P.recs('active');
      if (!all.length && !s.reports.length) return P.page({ title: '점검·보고서', body: P.noPlan() });
      const top = act.length ? `<div class="card acc"><h2 class="st">로드맵을 마쳤나요?</h2><p class="muted">사전 점검과 같은 문항에 다시 답하면 진단 에이전트가 결과 보고서를 만들어 드려요. 활동이 남아 있어도 시작할 수 있어요.</p>
          <div class="list ck-list">${act.map(R => { const c = P.count(R.plan); return `<div class="li"><span class="idx">${icon('map')}</span><div class="tx"><b>${esc(R.plan.goal)}</b><small>${esc(R.plan.name)} v${R.plan.version} · 활동 ${c.done}/${c.t} 완료</small></div><button class="btn ${c.done === c.t ? 'pri' : 'line'} sm" data-act="post-start" data-arg="${R.id}">사후 점검</button></div>`; }).join('')}</div></div>` : '';
      const pre = all.map(R => `<button class="li" data-act="pre-answers" data-arg="${R.id}"><span class="idx">${icon('file')}</span><div class="tx"><b>사전 점검 응답 · ${esc(R.plan.name)}</b><small>${esc(R.plan.goal)} · ${esc(R.createdAt)} · ${R.plan.assess.questions.length}문항</small></div><span class="end">${R.status !== 'active' ? `<span class="tag line">${R.status === 'done' ? '마침' : '보관'}</span>` : ''}${icon('right')}</span></button>`).join('');
      const reps = s.reports.map(r => `<button class="li" data-go="report:${r.id}"><span class="idx">${icon('chart')}</span><div class="tx"><b>결과 보고서 · ${esc(r.opt)} v${r.version}</b><small>${esc(r.goal)} · ${esc(r.createdAt)} · ${r.confirmed ? '확인함' : '확인 전'}</small></div><span class="end">${icon('right')}</span></button>`).join('');
      const sup = P.mySup();
      return P.page({ title: '점검·보고서', lead: sup ? `점검 응답은 나만 봐요. 결과 보고서는 내 계획을 보는 부서장 ${esc(sup.name)} 님도 볼 수 있어요.` : '점검 응답과 결과 보고서는 나만 봐요(내 계획을 보는 부서장 없음).', body: `${top}<div class="sec"><div class="sec-h"><h2 class="st">기록</h2></div><div class="list">${pre}${reps}</div></div>` });
    }
  };

  /* ───────── 학습 자료 (API-53·54 · 팀 DB 강좌·도서·자격증, 검색·쪽 나누기) ───────── */
  let resState = { kind: '전체', q: '', items: null, total: 0, loading: false, err: null };
  async function loadRes(more) {
    resState.loading = true; resState.err = null; GP.render(false);
    try {
      const r = await API.resources({ kind: resState.kind === '전체' ? '' : resState.kind, q: resState.q, limit: 30, offset: more ? (resState.items || []).length : 0 });
      GP.mergeRes(Object.fromEntries(r.items.map(x => [x.id, x])));
      resState.items = more ? (resState.items || []).concat(r.items) : r.items; resState.total = r.total;
    } catch (err) { resState.err = AI.cause(err); }
    resState.loading = false;
    if (String(S().route).split(':')[0] === 'resources') GP.render(false);
  }
  GP.act.resf = k => { resState.kind = k; resState.items = null; loadRes(); };
  GP.act['res-search'] = () => { const i = document.getElementById('resQ'); resState.q = i ? i.value.trim() : ''; resState.items = null; loadRes(); };
  GP.act['res-more'] = () => loadRes(true);
  P.resKv = r => `<dl class="kv" style="margin-top:4px">
    ${r.audience ? `<dt>대상</dt><dd>${esc(r.audience)}</dd>` : ''}${r.prereq ? `<dt>선수지식</dt><dd>${esc(r.prereq)}</dd>` : ''}<dt>내용</dt><dd>${esc(r.content || '내용 소개가 없어요')}</dd>
    <dt>단계·형식</dt><dd>${r.stage ? `${r.stage}단계 ${esc(stageName(r.stage))}` : '-'}${P.est(r, 'stage')} · ${esc(r.format || '-')}${P.est(r, 'format')}</dd>
    <dt>시간·비용</dt><dd>${r.hours != null ? hrs(r.hours) : '-'}${P.est(r, 'hours')} · ${P.costText(r)}${r.note ? `<br><span class="small muted">${esc(r.note)}</span>` : ''}</dd>
    ${(r.skills || []).length ? `<dt>스킬</dt><dd>${r.skills.map(esc).join(', ')}</dd>` : ''}
    <dt>출처</dt><dd>${esc(r.source)}${r.checked ? ` · 확인일 ${esc(r.checked)}` : ''}${r.url ? `<br><a class="link" href="${esc(r.url)}" target="_blank" rel="noopener">원문 열기 ${icon('out')}</a>` : ''}</dd></dl>`;
  scr.resources = {
    nav: 'resources', title: '학습 자료', width: 'wide',
    render() {
      const kinds = ['전체', '강좌', '도서', '자격'];
      const list = resState.items || [];
      return P.page({
        eyebrow: '부록', title: '학습 자료', lead: '로드맵에 쓰는 등록 자료예요. 팀 DB의 강좌(MS Learn·K-MOOC)·도서·자격증에서 추천에 쓸 수 있는 것만 보여요. 직접 수행하는 실습 과제는 여기 없어요.',
        body: `<div class="chips" style="margin-bottom:12px">${kinds.map(k => `<button class="chip ${resState.kind === k ? 'on' : ''}" data-act="resf" data-arg="${k}">${k}</button>`).join('')}</div>
          <div class="addrow" style="margin-bottom:16px"><input class="input" id="resQ" value="${esc(resState.q)}" placeholder="제목·제공처·스킬로 찾기 (예: RAG, Python, SQL)"><button class="btn line sm" data-act="res-search">찾기</button></div>
          ${resState.err ? `<p class="small" style="color:var(--warn)">${esc(resState.err.user)}</p>` : ''}
          <div class="list">${list.map(r => `<div class="li" style="display:block"><details class="more"><summary style="color:var(--ink);font-size:15px;display:flex;width:100%;gap:12px;align-items:center">${P.thumb(r)}<span class="grow"><b>${esc(r.title)}</b><small class="muted" style="display:block;font-weight:400;font-size:13px">${r.kind} · ${esc(r.provider)} · ${r.hours != null ? hrs(r.hours) : '-'}${(r.estimated || []).includes('hours') ? '(추정)' : ''} · ${P.costText(r)}</small></span>${r.real ? '<span class="tag line">실제 자료</span>' : '<span class="tag dash">가상</span>'}</summary>${P.resKv(r)}</details></div>`).join('')}</div>
          ${resState.loading ? P.loading('불러오는 중…') : resState.items && resState.items.length < resState.total ? `<div class="actions"><button class="btn line" data-act="res-more">더 보기 (${resState.items.length} / ${resState.total})</button></div>` : resState.items ? `<p class="small muted">${resState.total}건</p>` : ''}
          ${P.note('시간·단계·형식에 ‘추정’이 붙은 값은 팀 DB에 없어 규칙으로 정한 계획값이에요. 관리자 화면의 교육 데이터 엑셀로 고칠 수 있어요. 도서 가격·응시료·K-MOOC 수강료는 확인이 필요해요.')}`
      });
    },
    after(root) {
      if (!resState.items && !resState.loading) loadRes();
      const i = root.querySelector('#resQ'); if (i) i.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) GP.act['res-search'](); });
    }
  };
  scr.res = {
    nav: 'resources', title: '학습 자료',
    render(id) {
      const r = resOf(id);
      if (!r) { API.resourcesLookup([id]).then(m => { GP.mergeRes(m); if (m[id]) GP.render(false); }).catch(() => {}); return P.page({ back: 'resources', title: '자료를 불러오는 중이에요' }); }
      return P.page({ back: 'resources', eyebrow: `${r.kind} · ${r.real ? '실제 자료' : '가상 자료'}`, title: esc(r.title), lead: esc(r.provider), body: `<div class="card res-card ${esc(r.type || '')}">${P.thumb(r, 'lg')}${P.resKv(r)}</div>` });
    }
  };

  /* ───────── 부서장 (API-55~59) ─────────
     부서장 범위(2026-10-21 사용자 결정): 자기 부서 직원 + 바로 아래 부서의 부서장. 서버가 소속 관계를 확인하고 공개 범위만 보낸다.
     공개 범위(설계서 v1.7 1.1): 직원 소속·직급·직위, 확정 로드맵(버전)·활동 진행 상태·결과 보고서(전체)·받은 코멘트 기록. 메모·첨부·진단·작성 중인 로드맵은 보내지 않는다 */
  const ST_TAG = { active: '', done: '<span class="tag line">마침</span>', archived: '<span class="tag line">보관</span>' };
  const mk = (uid, x) => `${uid}~${x}`;
  const mkSplit = p => String(p || '').split('~');
  P.myMembers = () => GP.members();
  P.memberOf = uid => P.myMembers().find(e => e.id === String(uid)) || null;
  const who = e => `${esc(e.name)} · ${esc(GP.meLine(e))}`;
  const av = e => `<span class="avatar">${esc(e.name.slice(1))}</span>`;
  P.teamRow = m => {
    const e = m.user, tag = GP.isSup(e) ? ' <span class="tag line">부서장</span>' : '';
    const all = m.activePlans + m.pastPlans;
    if (!all) return `<div class="li">${av(e)}<div class="tx"><b>${esc(e.name)}${tag}</b><small>${esc(GP.meLine(e))} · 확정한 로드맵 없음</small></div></div>`;
    return `<button class="li" data-go="m-plan:${e.id}">${av(e)}<div class="tx"><b>${esc(e.name)}${tag}</b><small>${esc(GP.meLine(e))} · 진행 중 ${m.activePlans}개${m.pastPlans ? ` · 지난 로드맵 ${m.pastPlans}개` : ''}${m.reports ? ` · 결과 보고서 ${m.reports}개` : ''}</small></div><span class="end">${m.unreadComments ? `<span class="tag acc">코멘트 확인 전 ${m.unreadComments}</span>` : ''}${icon('right')}</span></button>`;
  };
  P.privacy = () => P.note('직원의 소속·직급·직위, 확정한 로드맵, 활동 진행 상태, 결과 보고서(사전→사후 점검 응답 변화 포함)를 볼 수 있어요. 활동 메모·첨부, 진단 수준값, 작성 중인 로드맵은 공개되지 않아요.');
  const loadingMember = st => (st.loading ? P.loading('서버에서 소속 직원의 기록을 불러오는 중…') : st.loadError ? `<p class="small" style="color:var(--warn)">${esc(st.loadError.user)}</p>` : '');
  scr['m-list'] = {
    nav: 'm-list', role: 'mgr', title: '소속 직원 계획', width: 'wide',
    render() {
      const me = GP.me(), T = GP.TEAM || { members: [] };
      return P.page({ eyebrow: `부서장 · ${esc(me.name)} · ${esc(me.dept || '')}`, title: '소속 직원의 성장 로드맵',
        lead: `소속 직원 ${T.members.length}명이 확정한 로드맵과 진행 상태, 결과 보고서를 보고 계획 조정 의견을 남길 수 있어요.`,
        body: `${T.error ? `<p class="small" style="color:var(--warn)">${esc(T.error.user)}</p>` : ''}<div class="list">${T.members.map(P.teamRow).join('')}</div>${P.privacy()}${P.note('소속 직원은 팀 DB의 부서 계층에서 정해요: 내 부서의 직원과 바로 아래 부서의 부서장. 부서·부서장 권한은 관리자 화면의 인적 데이터 엑셀로 바꿔요.')}` });
    },
    after() {
      if (mListFetched) return;
      mListFetched = true;
      GP.cleanup = () => { mListFetched = false; };
      GP.loadTeam(true).then(() => { GP.MEMBERS = {}; if (S().route === 'm-list') GP.render(false); });
    }
  };
  /* 직원 목록은 화면에 들어올 때 한 번만 새로 받는다(10/26). 받은 뒤 다시 그리면 after 가 또 불려 목록을 끝없이 다시 부르던 문제를 막는다.
     다른 화면으로 가면(GP.cleanup)·로그아웃·초기화 뒤에는 다음 방문 때 다시 받는다 */
  let mListFetched = false;
  const prevMgrReset = GP.onDataReset;
  GP.onDataReset = () => { if (prevMgrReset) prevMgrReset(); mListFetched = false; };
  P.mgrDraft = key => {
    const own = GP.own(), m = own.mgr && typeof own.mgr === 'object' ? own.mgr : (own.mgr = {}), k = key || own.mcur || '_';
    if (!m[k] || typeof m[k] !== 'object') m[k] = {};
    return m[k];
  };
  /* nm: 같은 화면에 새 코멘트 칸과 고치는 코멘트 칸이 함께 있을 때 라디오 묶음 이름이 겹치지 않게 붙이는 꼬리 */
  P.mgrCommentFields = function (pid, nm) {
    const m = P.mgrDraft(pid), b = `mgr.${pid}`, sfx = nm || '';
    return `<div class="field"><label>업무 적합성 <span class="muted small">담당 업무·부서 AI 사업과 맞나요?</span></label>
        <div class="chips">${D.commentFit.map(([v, l]) => `<label class="chip"><input type="radio" name="mfit${sfx}" value="${v}" data-bind="${b}.fit" ${m.fit === v ? 'checked' : ''}>${l}</label>`).join('')}</div>
        <textarea class="textarea sm" data-bind="${b}.fitText" placeholder="한두 문장으로 적어 주세요 (선택)">${esc(m.fitText)}</textarea></div>
      <div class="field"><label>수준·기간·분량 <span class="muted small">난이도와 기간이 적절한가요?</span></label>
        <div class="chips">${D.commentLevel.map(([v, l]) => `<label class="chip"><input type="radio" name="mlevel${sfx}" value="${v}" data-bind="${b}.level" ${m.level === v ? 'checked' : ''}>${l}</label>`).join('')}</div>
        <textarea class="textarea sm" data-bind="${b}.levelText" placeholder="조정이 필요하면 무엇을 어떻게 (선택)">${esc(m.levelText)}</textarea></div>
      <div class="field"><label>자유 의견 <span class="muted small">선택</span></label><textarea class="textarea sm" data-bind="${b}.free" placeholder="계획 조정에 도움이 될 의견">${esc(m.free)}</textarea></div>`;
  };
  const mgrRoadRow = uid => R => {
    const pl = R.plan, c = P.count(pl), cs = R.comments || [], wait = P.newComments(R).length, mine = cs.filter(x => x.byCode === GP.me().code).length;
    return `<button class="li" data-go="m-road:${mk(uid, R.id)}"><span class="idx">${icon('map')}</span><div class="tx"><b>${esc(pl.goal)}</b><small>${esc(pl.name)} v${pl.version} · 활동 ${c.done}/${c.t} 완료${mine ? ` · 보낸 코멘트 ${mine}개` : ''}</small></div><span class="end">${ST_TAG[R.status] || ''}${wait ? `<span class="tag acc">확인 전 ${wait}</span>` : ''}${icon('right')}</span></button>`;
  };
  /* 보낸 코멘트 고치기(10/23 사용자 요청): 내가 보낸 코멘트를 직원이 반영하기 전(새·확인함)까지 그 자리에서 고친다. 고치면 직원에게 다시 '새 코멘트'.
     이전 내용은 남기지 않고(덮어쓰기) '수정됨 · 날짜'만 보인다. 지우기는 직원의 로드맵 수정에 혼선을 줘서 두지 않는다 */
  P.cmChanged = m => { const o = m.orig || {}; return ['fit', 'fitText', 'level', 'levelText', 'free'].some(k => String(m[k] || '').trim() !== String(o[k] || '').trim()); };
  const mgrCmItem = (rkey, c, live) => {
    if (!live || !P.cmMine(c)) return P.cmItem(c, '', true);
    if (c.status === 'applied') return P.cmItem(c, `<p class="small muted cm-act">v${c.appliedVersion || ''}에 반영된 코멘트라 고칠 수 없어요.</p>`, true);
    const k = mk(rkey, c.id);
    if (GP.own().mcEdit !== k) return P.cmItem(c, `<div class="actions cm-act"><button class="btn line sm" data-act="m-edit" data-arg="${k}">${icon('edit')}수정</button></div>`, true);
    return `<div class="cm-item cm-edit"><div class="cm-h"><b>보낸 코멘트 고치기</b><span class="small muted">${esc(c.at)}${c.editedAt ? ` · 수정됨 ${esc(c.editedAt)}` : ''}</span>${P.cmTag(c, true)}</div>
      ${P.mgrCommentFields(k, '-e')}
      <p class="small muted" style="margin:0">${c.status === 'read' ? '직원이 확인한 코멘트예요. 저장하면 직원에게 다시 ‘새 코멘트’로 알려요.' : '직원이 아직 확인하지 않은 코멘트예요. 저장하면 고친 내용으로 보여요.'} 고치기 전 내용은 남지 않고 ‘수정됨’과 날짜만 보여요.</p>
      <div class="actions cm-act"><button class="btn pri sm" data-act="m-edit-save" data-arg="${k}" data-need="mEdit">저장</button><button class="btn line sm" data-act="m-edit-cancel" data-arg="${k}">취소</button></div></div>`;
  };
  const mgrRepRow = uid => r => `<button class="li" data-go="m-report:${mk(uid, r.id)}"><span class="idx">${icon('chart')}</span><div class="tx"><b>결과 보고서 · ${esc(r.opt)} v${r.version}</b><small>${esc(r.goal)} · ${esc(r.createdAt)} · ${r.confirmed ? '직원 확인함' : '직원 확인 전'}</small></div><span class="end">${icon('right')}</span></button>`;
  scr['m-plan'] = {
    nav: 'm-list', role: 'mgr', title: '직원 로드맵', width: 'wide',
    guard: uid => (P.memberOf(uid) ? null : 'm-list'),
    render(uid) {
      const e = P.memberOf(uid), st0 = GP.stateOf(uid);
      if (st0.loading || st0.loadError) return P.page({ back: 'm-list', eyebrow: who(e), title: `${esc(e.name)} 님의 로드맵`, body: loadingMember(st0) });
      return GP.asState(st0, () => {
        const all = P.recs(), act = P.recs('active'), past = all.filter(R => R.status !== 'active'), reps = S().reports;
        if (!all.length) return P.page({ back: 'm-list', eyebrow: who(e), title: '확정한 로드맵이 없어요', lead: '직원이 로드맵을 확정하면 여기에서 볼 수 있어요.', body: P.privacy() });
        return P.page({
          back: 'm-list', eyebrow: who(e), title: `${esc(e.name)} 님의 로드맵`, lead: '로드맵마다 진행 상태를 보고 계획 조정 의견을 남길 수 있어요.',
          body: `${act.length ? `<div class="sec"><div class="sec-h"><h2 class="st">진행 중 ${act.length}</h2></div><div class="list">${act.map(mgrRoadRow(uid)).join('')}</div></div>` : ''}
            ${past.length ? `<div class="sec"><div class="sec-h"><h2 class="st">지난 로드맵 ${past.length}</h2></div><div class="list">${past.map(mgrRoadRow(uid)).join('')}</div></div>` : ''}
            ${reps.length ? `<div class="sec"><div class="sec-h"><h2 class="st">결과 보고서 ${reps.length}</h2></div><div class="list">${reps.map(mgrRepRow(uid)).join('')}</div></div>` : ''}${P.privacy()}`
        });
      });
    }
  };
  scr['m-road'] = {
    nav: 'm-list', role: 'mgr', title: '직원 로드맵', width: 'wide',
    guard: param => {
      const [uid, pid] = mkSplit(param);
      if (!P.memberOf(uid)) return 'm-list';
      const st = GP.stateOf(uid);
      if (!st.loading && !st.loadError && !st.plans[pid]) return 'm-plan:' + uid;
      GP.own().mcur = mk(uid, pid); return null;
    },
    render(param) {
      const [uid, pid] = mkSplit(param), e = P.memberOf(uid), key = mk(uid, pid), st0 = GP.stateOf(uid);
      if (st0.loading || st0.loadError) return P.page({ back: 'm-plan:' + uid, eyebrow: who(e), title: '확정한 로드맵', body: loadingMember(st0) });
      return GP.asState(st0, () => {
        const R = S().plans[pid], pl = R.plan, live = R.status === 'active', cs = (R.comments || []).slice().reverse(), reps = P.planReports(R);
        const body = `<div class="card"><p class="eyebrow">${esc(pl.name)} · v${pl.version} · ${esc(R.createdAt)} 확정${live ? '' : R.status === 'done' ? ' · 마침' : ' · 보관'}</p><p style="font-weight:650;font-size:16px">${esc(pl.goal)}</p><div style="margin-top:16px">${P.stats(pl, true)}</div></div>
          <div class="sec"><div class="sec-h"><h2 class="st">단계별 진행</h2></div>${P.stagesView(pl, { status: true })}</div>
          ${reps.length ? `<div class="sec"><div class="sec-h"><h2 class="st">결과 보고서</h2></div><div class="list">${reps.map(mgrRepRow(uid)).join('')}</div></div>` : ''}${P.privacy()}
          ${cs.length ? `<div class="sec"><div class="sec-h"><h2 class="st">코멘트 기록 ${cs.length}</h2></div><div class="stack">${cs.map(c => mgrCmItem(key, c, live)).join('')}</div></div>` : ''}
          ${live ? `<div class="sec"><div class="sec-h"><h2 class="st">${cs.length ? '새 코멘트' : '계획 조정 의견'}</h2><button class="link quiet" data-act="m-sample" data-arg="${key}">시연용 예시 문장</button></div><div class="card">${P.mgrCommentFields(key)}</div>
            ${P.note('새 코멘트는 앞서 보낸 코멘트를 덮어쓰지 않고 쌓여요(팀 DB 부서장 코멘트 표). 보낸 코멘트는 직원이 로드맵에 반영하기 전까지 ‘수정’으로 고칠 수 있고, 지울 수는 없어요. 직원이 확인했는지, 몇 번째 버전에 반영했는지 여기서 볼 수 있어요. 직원이 반영을 요청해 수정안을 확정해야 로드맵이 바뀌어요.')}</div>`
          : P.note(`직원이 ${R.status === 'done' ? '마친' : '보관한'} 로드맵이에요. 코멘트는 진행 중인 로드맵에만 보낼 수 있어요.`)}`;
        return P.page({ back: 'm-plan:' + uid, eyebrow: who(e), title: '확정한 로드맵', body, foot: live ? `<button class="btn pri" data-act="m-send" data-arg="${key}" data-need="mComment">코멘트 보내기</button>` : '' });
      });
    }
  };
  scr['m-report'] = {
    nav: 'm-list', role: 'mgr', title: '직원 결과 보고서', width: 'wide',
    guard: param => {
      const [uid, rid] = mkSplit(param);
      if (!P.memberOf(uid)) return 'm-list';
      const st = GP.stateOf(uid);
      return st.loading || st.loadError || st.reports.some(r => r.id === rid) ? null : 'm-plan:' + uid;
    },
    render(param) {
      const [uid, rid] = mkSplit(param), e = P.memberOf(uid), st0 = GP.stateOf(uid);
      if (st0.loading || st0.loadError) return P.page({ back: 'm-plan:' + uid, eyebrow: who(e), title: '학습 결과 보고서', body: loadingMember(st0) });
      return GP.asState(st0, () => {
        const r = S().reports.find(x => x.id === rid), R = S().plans[r.planId];
        return P.page({
          back: R ? 'm-road:' + mk(uid, R.id) : 'm-plan:' + uid, eyebrow: `${who(e)} · 결과 보고서 · ${esc(r.opt)} v${r.version} · ${esc(r.createdAt)}`, title: '학습 결과 보고서', lead: esc(r.goal),
          body: `${P.reportBody(r)}${P.note(`${esc(e.name)} 님이 ${r.confirmed ? '확인한' : '아직 확인하지 않은'} 보고서예요. 부서장은 읽기만 할 수 있어요.`)}`
        });
      });
    }
  };
  GP.act['m-sample'] = key => { const c = D.commentSample; Object.assign(P.mgrDraft(key), { fit: c.fit, fitText: c.fitText, level: c.level, levelText: c.levelText, free: c.free }); GP.save(); GP.render(false); };
  GP.act['m-send'] = async key => {
    const [uid, pid] = mkSplit(key);
    if (!P.memberOf(uid) || !GP.valid.mComment()) return;
    const m = P.mgrDraft(key);
    try {
      await API.teamComment(pid, { fit: m.fit, fitText: m.fitText || '', level: m.level, levelText: m.levelText || '', free: m.free || '' });
      GP.own().mgr[key] = {}; GP.save();
      delete GP.MEMBERS[uid]; GP.loadTeam(true);
      GP.go('m-done:' + key);
    } catch (err) { GP.fail(err, '코멘트를 보내지 못했어요'); }
  };
  const endEdit = key => { const own = GP.own(); if (own.mgr) delete own.mgr[key]; if (own.mcEdit === key) own.mcEdit = null; GP.save(); };
  GP.act['m-edit'] = key => {
    const [uid, pid, cid] = mkSplit(key), st = (GP.MEMBERS[uid] || {}).st, R = st && st.plans[pid], c = R && (R.comments || []).find(x => x.id === cid);
    if (!c) return;
    const own = GP.own(), v = { fit: c.fit, fitText: c.fitText, level: c.level, levelText: c.levelText, free: c.free };
    if (own.mcEdit && own.mcEdit !== key) endEdit(own.mcEdit);  // 한 번에 하나만 고친다
    P.mgrDraft(key); own.mgr[key] = Object.assign({}, v, { orig: v });
    own.mcEdit = key; GP.save(); GP.render(false);
  };
  GP.act['m-edit-cancel'] = key => { endEdit(key); GP.render(false); };
  GP.act['m-edit-save'] = async (key, btn) => {
    const [uid, pid, cid] = mkSplit(key), m = (GP.own().mgr || {})[key];
    if (!P.memberOf(uid) || !m || GP.own().mcEdit !== key || !GP.valid.mEdit()) return;
    btn.disabled = true;
    try {
      const r = await API.teamCommentEdit(pid, cid, { fit: m.fit, fitText: m.fitText || '', level: m.level, levelText: m.levelText || '', free: m.free || '' });
      endEdit(key);
      await GP.loadTeam(true); await GP.reloadMember(uid);
      GP.render(false);
      GP.toast(r.changed ? '코멘트를 고쳤어요 · 직원에게 ‘새 코멘트’로 보여요' : '바뀐 내용이 없어 저장하지 않았어요');
    } catch (err) {
      GP.fail(err, '코멘트를 고치지 못했어요');
      const code = err && err.payload && err.payload.code;
      if (code !== 'COMMENT_APPLIED' && code !== 'NOT_ACTIVE') { btn.disabled = false; return; }
      // 그사이 직원이 반영했거나 로드맵을 마쳤으면 고치는 칸을 닫고 지금 상태를 다시 읽는다(못 읽으면 다음 그리기 때 다시 불러옴)
      endEdit(key);
      try { await GP.reloadMember(uid); } catch (e) { delete GP.MEMBERS[uid]; }
      GP.render(false);
    }
  };
  scr['m-done'] = {
    nav: 'm-list', role: 'mgr', title: '코멘트 전달',
    guard: param => (P.memberOf(mkSplit(param)[0]) ? null : 'm-list'),
    render(param) {
      const [uid, pid] = mkSplit(param), e = P.memberOf(uid);
      return `<div class="badge-ico">${icon('send')}</div>
      <h1 class="t lg">${esc(e.name)} 님에게 코멘트를 보냈어요</h1>
      <p class="lead">직원이 반영을 요청하고 수정안을 확정해야 로드맵이 바뀌어요. 직원이 확인했는지와 반영했는지는 이 로드맵의 ‘코멘트 기록’에서 볼 수 있어요.</p>
      <div class="actions"><button class="btn pri" data-go="m-road:${mk(uid, pid)}">코멘트 기록 보기</button><button class="btn line" data-go="m-list">소속 직원 계획으로</button></div>
      ${P.note(`시연: 로그아웃한 뒤 ${esc(e.name)}(사번 ${esc(e.code)})으로 로그인하면 받은 코멘트를 볼 수 있어요.`)}`;
    }
  };
})();

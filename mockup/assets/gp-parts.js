/* GrowPath 4차 목업 (Claude) · 계산, 공통 조각, 여러 메뉴가 함께 쓰는 화면 */
(function () {
  'use strict';
  const GP = window.GP, D = GP.D, AI = GP.AI, { esc, won, hrs, icon } = GP;
  const P = GP.P = {};
  const S = () => GP.S;
  const stageName = n => (D.stages.find(s => s.n === n) || {}).name || '';
  P.stageName = stageName;

  /* ───────── 상태 틀 ───────── */
  GP.freshDraft = () => ({
    goal: '', project: null, prefs: AI.emptyPrefs(), detailsOk: false,
    quiz: null, answers: {}, diag: null, startStage: null, fix: null, edit: null, handoff: null, gen: null,
    chosen: null,
    /* 생성 실패·3안 진행 상태도 저장한다: 새로 고쳐도 실패한 것은 실패로 남고, 사용자가 '다시 시도'를 눌러야 다시 돈다 */
    quizFail: null, diagFail: null, genRun: null
  });
  /* ───────── 로드맵 여러 개 (10/14 · 묶음 6) ─────────
     확정한 로드맵마다 기록 하나를 둔다. 개수 제한 없이 동시에 진행한다(사용자 결정).
       plans[id] = { id, status: active 진행 중 | done 마침(결과 보고서 확인) | archived 보관, createdAt·doneAt·archivedAt,
                     plan(지금 버전), versions, progress(활동 상태·메모), post(사후 점검 응답), comments(부서장 코멘트 기록), pending·rev(수정 요청) }
     S.cur 은 지금 보고 있는 로드맵 id 이고, S.plan·versions·progress·post·pending·rev 는 그 로드맵 기록의 값을 가리킨다
     (저장되지 않는 접근자 · 로드맵 하나를 다루는 화면·수정 요청 코드를 그대로 쓰려고). 여러 로드맵을 함께 보는 화면은 P.recs 로 기록을 직접 돈다 */
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
  P.freshPost = () => ({ answers: {}, goalSelf: '', file: null });
  GP.fresh = () => P.wire({
    route: 'home', draft: GP.freshDraft(), draftPlan: null, plans: {}, cur: null,
    mgr: {}, reports: [], picks: [], lastNew: null, tmp: null, demoOpen: false
  });
  P.R = pid => (S().plans || {})[pid || S().cur] || null;
  P.recs = st => Object.values(S().plans || {}).filter(R => !st || R.status === st);
  P.focus = pid => { if (S().plans[pid]) S().cur = pid; return P.R(pid); };
  /* 확정한 로드맵을 새 기록으로 넣는다. 진행 중인 다른 로드맵은 그대로 둔다(함께 진행) */
  P.newRec = plan => {
    const s = S(), id = 'p' + (Object.keys(s.plans).length + 1);
    plan.rid = id;
    s.plans[id] = { id, status: 'active', createdAt: D.today, plan, versions: [plan], progress: {}, post: P.freshPost(), comments: [], pending: null, rev: null };
    s.cur = id;
    return s.plans[id];
  };
  P.planReports = R => S().reports.filter(r => r.planId === R.id);
  P.newComments = R => (R.comments || []).filter(c => c.status === 'new');
  /* 내 계획을 보는 부서장 (가상 사내 DB 감독 그룹 · 10/15). 없으면 null(내 계획은 나만 봄) */
  P.mySup = () => { const me = GP.me(); return (me && me.mySupervisor) || null; };
  /* 코멘트를 쓴 부서장 이름(예전 기록에는 이름이 없어 '부서장') */
  P.cmBy = c => (c && c.by) || '부서장';
  /* 예전(로드맵 하나) 저장 형식을 새 형식으로 옮긴다. 진행 중이던 로드맵과 보관된 로드맵, 코멘트, 보고서 연결을 그대로 살린다 */
  GP.migrateState = o => {
    if (!o.plans) {
      o.plans = {};
      const put = (rec, status, extra) => {
        const id = 'p' + (Object.keys(o.plans).length + 1);
        rec.plan.rid = id; (rec.versions || []).forEach(v => { v.rid = id; });
        o.plans[id] = Object.assign({ id, status, createdAt: rec.plan.confirmedAt || D.today, plan: rec.plan, versions: rec.versions || [rec.plan], progress: rec.progress || {}, post: P.freshPost(), comments: [], pending: null, rev: null }, extra);
        return id;
      };
      (o.archive || []).forEach(a => { if (a && a.plan) put(a, 'archived', { archivedAt: a.plan.confirmedAt || D.today }); });
      if (o.plan) {
        const cm = o.comment ? [Object.assign({ id: 'c1' }, o.comment)] : [];
        if (o.rev && o.rev.fromComment === true) o.rev.fromComment = cm.length ? 'c1' : false;
        if (o.pending && o.pending.fromComment === true) o.pending.fromComment = cm.length ? 'c1' : false;
        const id = put({ plan: o.plan, versions: o.versions, progress: o.progress }, o.plan.status === 'done' ? 'done' : 'active', { post: o.post || P.freshPost(), comments: cm, pending: o.pending || null, rev: o.rev || null });
        o.cur = id;
        (o.reports || []).forEach(r => { if (!r.planId) r.planId = id; });
      }
    }
    ['plan', 'versions', 'progress', 'post', 'pending', 'rev', 'comment', 'archive'].forEach(k => { delete o[k]; });
    return o;
  };

  /* ───────── 계산 ───────── */
  /* 세부 사항 → 로드맵 계획 에이전트 조건. 빈 칸('알아서')은 null 로 넘겨 에이전트가 정한다(기간 null = 정해진 기간 없음).
     자격증은 기본값이 '계획 없음'이라 고른 자격이 있을 때만 certRes 를 넘긴다 */
  P.handoffPrefs = p => {
    const budget = p.budget === '' || p.budget == null ? null : Math.max(0, +p.budget || 0);
    return {
      format: AI.prefText('format', p), formatKey: p.format || 'auto', certPlan: AI.prefText('cert', p), certRes: AI.certRes(p),
      weeklyHours: +p.hours > 0 ? Math.min(40, +p.hours) : null, hoursAuto: !(+p.hours > 0), deadlineWeeks: +p.weeks > 0 ? Math.min(52, Math.round(+p.weeks)) : null,
      budgetWon: budget, budgetAuto: budget == null, budgetLimit: budget
    };
  };
  /* 진단 에이전트 → 로드맵 계획 에이전트 전달 내용. '로드맵 생성'을 누를 때 최신 선호로 만든다 */
  /* 시작 단계: 진단 에이전트 제안이 기본, 점검 결과 수정 화면에서 사용자가 바꾸면 그 값 */
  P.startOf = d => (+d.startStage >= 1 && +d.startStage <= 4 ? +d.startStage : d.diag.startStage);
  /* 역량·자료·결과물·이미 할 수 있는 것: 진단 에이전트 제안(d.diag)이 기본, 수정 화면에서 고친 항목만 d.fix 에 둔다 */
  P.FIX = [['competencies', '익히게 될 역량'], ['resourceIds', '듣게 될 강좌·자료'], ['outcome', '만들 결과물'], ['known', '이미 할 수 있는 것']];
  P.dv = (d, k) => (d.fix && d.fix[k] != null ? d.fix[k] : d.diag[k]);
  P.edited = (d, k) => (k === 'start' ? P.startOf(d) !== d.diag.startStage : !!(d.fix && d.fix[k] != null));
  P.buildHandoff = function () {
    const d = S().draft, a = d.diag, start = P.startOf(d), changed = start !== a.startStage;
    return {
      goal: d.goal, projectFile: d.project ? d.project.name : null, projectSummary: (P.docSummary && P.docSummary(d)) || null, domain: d.quiz ? d.quiz.domain : AI.domainOf(d.goal),
      startStage: start, startReason: changed ? `사용자가 ${start}단계부터 하기로 정함 (진단 제안: ${a.startStage}단계 · ${a.startReason})` : a.startReason,
      startSuggested: a.startStage, known: P.dv(d, 'known'), gaps: a.gaps, focus: P.dv(d, 'competencies'), outcome: P.dv(d, 'outcome'),
      resourceHints: P.dv(d, 'resourceIds'), prefs: P.handoffPrefs(d.prefs), userNotes: String(d.prefs.etc || '').trim() ? [d.prefs.etc.trim()] : [], agentNotes: a.handoffNotes,
      userEdited: (changed ? ['시작 단계'] : []).concat(P.FIX.filter(([k]) => P.edited(d, k)).map(([, l]) => l))
    };
  };
  /* 주당 시간: 사용자가 적은 값, '알아서'면 그 안을 쓴 하위 에이전트가 정한 값 */
  P.params = function (opt) {
    const h = S().draft.handoff;
    return { start: h.startStage, hours: h.prefs.weeklyHours || (opt && opt.weeklyHours) || D.autoHours, format: h.prefs.formatKey, patch: {} };
  };

  /* 자료는 에이전트가 쓴 그대로 둔다(10/14). 학습 방식 변경도 수정 요청에서 에이전트가 자료를 다시 고른다 */
  P.buildPlan = function (def, prm, base) {
    const p = Object.assign({ start: 1, hours: 4, format: 'mixed', patch: {} }, prm);
    const acts = def.acts.filter(a => a.stage >= p.start).map(a => {
      const res = a.res, title = a.title;
      const x = { id: a.id, stage: a.stage, title, res: res || null, task: !res, how: a.how || '', hours: res ? D.res[res].hours : a.hours };
      if (p.patch[a.id]) Object.assign(x, p.patch[a.id]);
      return x;
    });
    let cum = 0;
    acts.forEach(a => { a.wFrom = Math.floor(cum / p.hours) + 1; cum += a.hours; a.wTo = Math.max(a.wFrom, Math.ceil(cum / p.hours)); });
    const weeks = Math.max(1, Math.ceil(cum / p.hours));
    const resIds = [...new Set(acts.map(a => a.res).filter(Boolean))];
    const cost = resIds.reduce((s, r) => s + (D.res[r].cost || 0), 0);
    const costUnknown = resIds.some(r => D.res[r].cost == null);
    /* 기간·예산 한도 검사는 프론트에서 하지 않는다 (백엔드 범위 · 10/08 결정). 한도는 에이전트 지시문으로만 전달 */
    return { opt: def.id, name: def.name, short: def.short, tagline: def.tagline, goal: base ? base.goal : S().draft.goal, def, params: p, start: p.start, hours: p.hours, format: p.format, acts, totalH: cum, weeks, cost, costUnknown };
  };

  /* 열 순서는 A1·A2·A3 고정. 고른 기록으로 순서를 바꾸거나 '자주 고른 관점'을 표시하지 않는다(10/14 · 선택에 영향을 주지 않게) */
  P.optionIds = function () {
    const g = S().draft.gen; return g ? D.optionOrder.filter(k => g.options[k]) : [];
  };
  P.opts = () => P.optionIds().map(id => P.buildPlan(S().draft.gen.options[id], P.params(S().draft.gen.options[id])));

  P.range = acts => { const a = Math.min(...acts.map(x => x.wFrom)), b = Math.max(...acts.map(x => x.wTo)); return a === b ? `${a}주차` : `${a}~${b}주차`; };
  /* 활동 상태는 완료 / 진행 중 두 가지. 예전 값(todo·part)은 진행 중으로 읽는다 */
  /* 진행 기록은 로드맵마다 따로: pl(로드맵 버전)에 붙은 rid 로 기록을 찾고, 없으면 지금 보고 있는 로드맵 */
  P.prog = pl => { const R = pl && pl.rid ? S().plans[pl.rid] : P.R(); return (R && R.progress) || {}; };
  P.st = (id, pl) => (((P.prog(pl)[id] || {}).status) === 'done' ? 'done' : 'doing');
  P.count = pl => { const t = pl.acts.length, done = pl.acts.filter(a => P.st(a.id, pl) === 'done').length; return { t, done }; };
  P.nextAct = pl => pl.acts.find(a => P.st(a.id, pl) !== 'done');
  P.curStage = pl => (P.nextAct(pl) || pl.acts[pl.acts.length - 1]).stage;
  P.act = (id, pid) => { const R = P.R(pid); return ((R && R.plan) || S().draftPlan).acts.find(a => a.id === id); };
  P.stageActs = (pl, n) => pl.acts.filter(a => a.stage === n);

  /* 변경 전 → 후. 활동은 id로 맞춘다(수정안을 만들 때 같은 활동은 이전 id를 이어 받음). 학습 여건·관점 변경도 함께 보여 준다 */
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

  /* 수정 요청 → 수정안 (확정한 로드맵 · 10/14 에이전트로 바꿈)
     항목(여러 개)과 요청 문장을 받아, 로드맵을 쓴 관점의 하위 에이전트(관점을 바꾸면 새 관점의 에이전트)가 수정안을 쓴다.
     확정하기 전까지 기존 로드맵은 그대로. 실패하면 가데이터로 대신하지 않고 안내하며, 다시 시도는 사용자가 눌러야만 한다 */
  P.REV_ITEMS = [
    ['hours', '주당 학습 시간', 'cond'], ['weeks', '정해진 기간', 'cond'], ['budget', '교육 예산', 'cond'], ['format', '학습 방식', 'cond'],
    ['cert', '자격증 계획', 'cond'], ['etc', '일정·환경 제약', 'cond'], ['start', '시작 단계', 'plan'], ['pid', '관점', 'plan'],
    ['remove', '활동 빼기', 'acts'], ['replace', '활동 바꾸기', 'acts'], ['add', '활동 추가', 'acts']
  ];
  P.revBase = () => S().plan;
  P.freshRev = (note, fromComment) => {
    const pl = S().plan, p = pl.prefs || {};
    /* fromComment: 이 수정 요청을 시작한 코멘트 id (확정하면 그 코멘트를 'vN에 반영'으로) */
    return { on: {}, note: note || '', fromComment: fromComment || false, fail: null,
      v: { hours: pl.hours, weeks: p.weeks || '', budget: p.budget == null ? '' : p.budget, format: p.format || '', cert: p.cert || '', etc: p.etc || '', start: pl.start, pid: pl.opt, remove: [], replace: [], replaceHow: '', addRes: [], addTask: '' } };
  };
  const blankNum = v => v === '' || v == null;
  const addTasks = r => String(r.v.addTask || '').split('\n').map(t => t.trim()).filter(Boolean).slice(0, 5);
  /* 고른 항목마다 값이 맞는지 (빈 칸은 '알아서'·'없음'으로 허용) */
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
  /* 에이전트에게 넘길 변경 요청: 고른 항목만, 사람이 읽는 값으로 */
  function revChanges(r, pl) {
    const v = r.v, on = r.on, c = {}, actRef = id => { const a = pl.acts.find(x => x.id === id); return a ? { key: a.id, title: a.title } : null; };
    const raw = Object.assign({}, pl.prefs);
    ['hours', 'weeks', 'budget', 'format', 'cert', 'etc'].forEach(k => { if (on[k]) raw[k] = v[k]; });
    if (on.hours) c.weeklyHours = blankNum(v.hours) ? '알아서' : +v.hours;
    if (on.weeks) c.deadlineWeeks = blankNum(v.weeks) ? '없음' : +v.weeks;
    if (on.budget) c.budgetWon = blankNum(v.budget) ? '알아서' : +v.budget;
    if (on.format) c.format = AI.prefText('format', raw);
    if (on.cert) c.certification = AI.certNameOf(raw) || '계획 없음';
    if (on.etc) c.constraints = String(v.etc || '').trim() || '없음';
    if (on.start) c.startStage = +v.start;
    if (on.pid && v.pid !== pl.opt) c.perspective = `${v.pid} ${D.perspectives[v.pid].name}`;
    if (on.remove) c.removeActs = v.remove.map(actRef).filter(Boolean);
    if (on.replace) { c.replaceActs = v.replace.filter(id => !(on.remove && v.remove.includes(id))).map(actRef).filter(Boolean); if (String(v.replaceHow || '').trim()) c.replaceHint = v.replaceHow.trim(); }
    if (on.add) { if (v.addRes.length) c.addResources = v.addRes.slice(); const t = addTasks(r); if (t.length) c.addTasks = t; }
    return { c, raw, pid: on.pid && v.pid !== pl.opt ? v.pid : pl.opt, start: on.start ? +v.start : pl.start };
  }
  /* 같은 활동은 이전 id를 이어 받아 진행 기록(완료·메모)이 그대로 따라가게 한다. 새 활동은 새 id */
  function keepIds(def, base, ver) {
    const used = new Set(), key = a => (a.res ? 'r:' + a.res : 't:' + a.title), norm = t => String(t || '').replace(/\s+/g, '');
    /* 1) 같은 자료 또는 같은 제목의 과제  2) 같은 단계의 과제 중 제목이 다른 쪽을 포함하면(예: 끝에 '(점검 확대)'만 붙음) 같은 활동으로 본다 */
    const got = new Set();
    def.acts.forEach(a => { const old = base.acts.find(x => !used.has(x.id) && key(x) === key(a)); if (old) { a.id = old.id; used.add(old.id); got.add(a); } });
    def.acts.forEach((a, i) => {
      if (got.has(a)) return;
      const old = !a.res && base.acts.find(x => !used.has(x.id) && !x.res && x.stage === a.stage && (norm(a.title).includes(norm(x.title)) || norm(x.title).includes(norm(a.title))));
      a.id = old ? old.id : `${def.id.toLowerCase()}-v${ver}-${i + 1}`;
      if (old) used.add(old.id);
    });
    return def;
  }
  let revBusy = false;
  P.revBusy = () => revBusy;
  /* 수정안은 요청한 로드맵 기록(R)에 넣는다. 기다리는 동안 다른 로드맵을 봐도 섞이지 않는다 */
  P.revise = async function () {
    const R = P.R(), r = R && R.rev, base = R && R.plan; if (!r || !base || revBusy) return;
    const { c, raw, pid, start } = revChanges(r, base), prefsH = P.handoffPrefs(raw);
    const handoff = Object.assign({}, base.handoff, { prefs: prefsH, startStage: start, userNotes: String(raw.etc || '').trim() ? [raw.etc.trim()] : [] });
    const req = String(r.note || '').trim(), key = P.revKey(r);
    const inp = { pid, handoff, changes: c, request: req || null, fromComment: r.fromComment,
      plan: { opt: base.opt, name: base.name, tagline: base.tagline, def: base.def, hours: base.hours, start: base.start, acts: base.acts.map(a => ({ id: a.id, stage: a.stage, title: a.title, res: a.res, hours: a.hours, how: a.how, done: P.st(a.id) === 'done' })) } };
    revBusy = true; r.fail = null; R.pending = null; GP.save(); GP.render(false);
    const sim = AI.simOnce('rev', key);
    if (!AI.live() || sim) await new Promise(ok => setTimeout(ok, sim ? 1200 : 900));
    let out = null, err = null;
    try { out = await AI.roadmapRevise(inp, { simFail: sim }); } catch (e) { err = e; }
    revBusy = false;
    const here = () => S().route === 'revise:' + R.id;
    if (S().plans[R.id] !== R || R.rev !== r || R.plan !== base) { if (here()) GP.render(false); return; }
    if (err) { r.fail = { cause: AI.cause(err) }; GP.save(); if (here()) GP.render(false); return; }
    const def = keepIds(out, base, base.version + 1);
    const hours = prefsH.weeklyHours || def.weeklyHours || base.hours || D.autoHours;
    const to = P.buildPlan(def, { start, hours, format: prefsH.formatKey, patch: {} }, base);
    const summary = String(out.summary || '').trim();
    R.pending = { from: base, to, key, request: req, fromComment: r.fromComment, summary, notes: out.notes || [], source: def.source,
      prefsFrom: base.prefs, prefsTo: raw, handoff, label: `${r.fromComment ? '부서장 코멘트 반영' : '수정 요청 반영'}${summary ? ' · ' + summary : ''}`.slice(0, 70) };
    GP.save();
    if (here()) { GP.render(false); const el = document.getElementById('diffSec'); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  };
  P.acceptRevision = function () {
    const s = S(), R = P.R(), pd = R && R.pending; if (!pd) return;
    const changed = pd.to.opt !== R.plan.opt;
    const keep = { rid: R.id, version: R.plan.version + 1, confirmedAt: D.today, why: pd.label, assess: R.plan.assess, prefs: pd.prefsTo, handoff: pd.handoff, selection: changed ? P.selectionOf(pd.to.def) : R.plan.selection };
    R.plan = Object.assign({}, pd.to, keep); R.versions.push(R.plan);
    if (changed) s.picks.push(R.plan.opt);
    /* 코멘트로 시작한 수정안이면 그 코멘트를 '반영함'으로 (부서장 화면에도 vN에 반영으로 보임) */
    const c = pd.fromComment && R.comments.find(x => x.id === pd.fromComment);
    if (c) Object.assign(c, { status: 'applied', appliedVersion: R.plan.version, appliedAt: D.today });
    R.pending = null; R.rev = null; GP.save(); GP.go('confirmed:' + R.id);
  };
  P.dropRevision = function () {
    const R = P.R(), r = R && R.rev, to = R ? (r && r.fromComment ? 'comment:' : 'roadmap:') + R.id : 'roadmap';
    if (R) { R.pending = null; R.rev = null; }
    GP.save(); GP.go(to); GP.toast('수정안을 버렸어요. 계획은 그대로예요');
  };

  P.selectionOf = def => ({ perspective: def.id, name: def.name, agent: `로드맵 계획 에이전트 · ${def.id} ${def.name}`, source: def.source, at: D.today });
  P.choose = function (id) {
    const d = S().draft;
    d.chosen = id; S().draftPlan = P.buildPlan(d.gen.options[id], P.params(d.gen.options[id]));
    GP.save(); GP.go('new-review');
  };
  /* 확정: 새 로드맵 기록을 만든다. 진행 중인 다른 로드맵은 보관하지 않고 함께 진행한다(10/14 · 묻지 않음) */
  P.confirm = function () {
    const s = S(), d = s.draft;
    const R = P.newRec(Object.assign({}, s.draftPlan, {
      version: 1, confirmedAt: D.today, why: '최초 확정',
      assess: { questions: d.quiz.questions, answers: Object.assign({}, d.answers), level: d.diag.level, domain: d.quiz.domain },
      prefs: JSON.parse(JSON.stringify(d.prefs)), handoff: d.handoff,
      selection: P.selectionOf(d.gen.options[d.chosen])
    }));
    s.picks.push(R.plan.opt);
    s.draft = GP.freshDraft(); s.draftPlan = null; s.lastNew = null;
    GP.save(); GP.go('confirmed:' + R.id);
  };
  P.record = function (id, status, memo, file, pid) {
    const R = P.R(pid); if (!R) return;
    const old = R.progress[id] || {};
    R.progress[id] = { status, memo: memo != null ? memo : (old.memo || ''), file: file !== undefined ? file : (old.file || null), at: D.today };
    GP.save();
  };

  /* 결과 보고서 (수준값은 hidden 에만 저장). 문항마다 사전→사후 5점 응답을 보여 주고, 응답이 오른 것 / 그대로이거나 내려간 것으로 나눈다 */
  P.reportItems = (items, rose) => items.filter(x => AI.rose(x.pre, x.post) === rose).map(x => ({ skill: x.skill, from: x.pre, to: x.post }));
  P.makeReport = async function (R) {
    const s = S(), pl = R.plan, A = pl.assess, post = R.post.answers;
    const items = A.questions.map(q => ({ id: q.id, area: q.area, text: q.text, skill: AI.skillLabel(q.skill), pre: A.answers[q.id], post: post[q.id] }));
    const done = pl.acts.filter(a => P.st(a.id, pl) === 'done'), rest = pl.acts.filter(a => P.st(a.id, pl) !== 'done');
    const sim = AI.simOnce('report', JSON.stringify([R.id, post, R.post.goalSelf]));
    if (!AI.live() || sim) await new Promise(r => setTimeout(r, sim ? 1200 : 400));
    /* 실패하면 그대로 던진다 → 사후 점검 화면이 실패 안내와 '다시 시도하기'를 보여 준다 */
    const out = await AI.diagReport({ goal: pl.goal, planName: pl.name, opt: pl.opt, domain: A.domain, items, doneTitles: done.map(a => a.title), restTitles: rest.map(a => a.title), total: pl.acts.length, goalSelf: D.goalSelf[+R.post.goalSelf - 1] || '' }, { simFail: sim });
    const r = {
      id: 'r' + (s.reports.length + 1), planId: R.id, version: pl.version, goal: pl.goal, opt: pl.name, createdAt: D.today, confirmed: false,
      gained: P.reportItems(items, true), still: P.reportItems(items, false),
      doneTitles: done.map(a => a.title), restTitles: rest.map(a => a.title), goalSelf: D.goalSelf[+R.post.goalSelf - 1] || '', file: R.post.file,
      good: out.good, improve: out.improve, next: out.next,
      hidden: { pre: A.level, post: AI.levelOf(A.questions, post) }
    };
    s.reports.unshift(r); GP.save();
    return r;
  };
  P.report = id => S().reports.find(r => r.id === id) || S().reports[0];

  /* ───────── 검사 ───────── */
  const d = () => S().draft;
  Object.assign(GP.valid, {
    goal: () => (d().goal || '').trim().length >= 4,
    quizDone: () => !!d().quiz && d().quiz.questions.every(q => d().answers[q.id]),
    post: () => !!S().plan && S().plan.assess.questions.every(q => S().post.answers[q.id]) && !!S().post.goalSelf,
    tmpStatus: () => !!(S().tmp && S().tmp.status),
    /* 수정안 만들기: 고른 항목이 있고 값이 모두 맞거나, 요청 문장이 있을 때 */
    revOk: () => {
      const r = S().rev; if (!r || revBusy) return false;
      const ks = P.revPicked(r);
      return ks.every(k => P.revItemOk(r, k)) && (ks.length > 0 || !!String(r.note || '').trim());
    },
    /* 부서장이 쓰는 중인 코멘트는 로드맵마다 따로 둔다(mgr[로드맵 id]) */
    mFit: () => !!P.mgrDraft().fit, mLevel: () => !!P.mgrDraft().level
  });
  GP.valid.mComment = () => GP.valid.mFit() && GP.valid.mLevel();
  GP.valid.editOk = () => { const e = d().edit; return !!e && !Object.values(P.editMissing(e)).some(Boolean); };

  /* ───────── 공통 조각 ───────── */
  P.page = o => `${o.back ? `<div class="wtop"><button class="back" data-go="${o.back}" aria-label="이전 화면">${icon('left')}</button><div class="wprog"></div></div>` : ''}
    ${o.eyebrow ? `<p class="eyebrow">${o.eyebrow}</p>` : ''}<h1 class="t">${o.title}</h1>${o.lead ? `<p class="lead">${o.lead}</p>` : ''}${o.body || ''}${o.foot ? `<div class="actions">${o.foot}</div>` : ''}`;
  P.next = (go, label, need) => `<button class="btn pri" data-go="${go}" ${need ? `data-need="${need}"` : ''}>${label || '다음'}</button>`;
  P.note = t => `<p class="note">${icon('info')}<span>${t}</span></p>`;
  /* AI 호출 실패 안내 (10/14): 사용자에게는 쉬운 말과 할 일만 보여 주고, 원인·조치·원문 오류는 '자세히 보기(운영자용)'에 접어 둔다.
     items: [[이름(이미 이스케이프한 HTML) 또는 '', {text, hint, raw}]] */
  P.errText = c => `${c.user || AI.userText(c.kind)}. ${AI.userTodo(c.kind).join(' ')}`;
  P.opsBox = (items, cls) => `<details class="ops ${cls || ''}"><summary>${icon('right')}자세히 보기 (운영자용)</summary><div class="ops-b">${items.map(([name, c]) => `<div class="ops-i">${name ? `<b>${name}</b>` : ''}
      ${c.text ? `<p><span>원인</span>${esc(c.text)}</p>` : ''}${c.hint ? `<p><span>조치</span>${esc(c.hint)}</p>` : ''}${c.raw ? `<p class="raw"><span>원문</span>${esc(c.raw)}</p>` : ''}</div>`).join('')}</div></details>`;
  P.loading = t => `<div class="loading"><span class="sp"></span><span>${t}</span></div>`;

  P.costB = (c, unk) => `${c ? c.toLocaleString('ko-KR') : 0}<em>원${unk ? '+' : ''}</em>`;
  P.stats = (pl, bare) => `<div class="stats ${bare ? 'bare' : ''}"><div><small>기간</small><b>${pl.weeks}<em>주</em></b></div><div><small>주당</small><b>${pl.hours}<em>시간</em></b></div><div><small>예상 비용${pl.costUnknown ? ' · 응시료 별도' : ''}</small><b>${P.costB(pl.cost, pl.costUnknown)}</b></div></div>`;
  P.actMeta = function (a) {
    if (a.task) return '직접 수행 과제';
    const r = D.res[a.res];
    return `${r.kind} · ${esc(r.provider)}${r.real ? '' : ' · 가상'}${r.cost ? ' · ' + won(r.cost) : r.cost == null ? ' · 응시료 확인 필요' : ''}`;
  };
  P.stt = (id, pl) => { const s = P.st(id, pl); return `<span class="stt ${s}" aria-label="${s === 'done' ? '완료' : '진행 중'}">${s === 'done' ? icon('check') : ''}</span>`; };
  P.stagesView = function (pl, o) {
    o = o || {};
    const prog = P.prog(pl);
    return D.stages.filter(st => st.n >= pl.start).map(st => {
      const acts = P.stageActs(pl, st.n); if (!acts.length) return '';
      return `<div class="stage"><div class="stage-h"><span class="no">${st.n}</span><b>${st.name}</b><span class="end">${P.range(acts)}${o.status ? ` · ${acts.filter(a => P.st(a.id, pl) === 'done').length}/${acts.length} 완료` : ''}</span></div>
        <ul class="acts">${acts.map(a => { const memo = o.memo && (prog[a.id] || {}).memo; return `<li>${o.status ? P.stt(a.id, pl) : '<span class="bullet"></span>'}<div class="tx">${esc(a.title)}<small>${P.actMeta(a)}</small>${memo ? `<small class="memo">메모 · ${esc(memo)}</small>` : ''}</div><span class="h">${hrs(a.hours)}</span></li>`; }).join('')}</ul></div>`;
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
      ${P.note('처음 응답한 원본이에요. 진단 에이전트가 계산한 수준값은 사후 비교용으로만 저장하고 화면에 보여주지 않아요.')}`, { title: '사전 점검 응답', sub: pl ? pl.goal : '', wide: true });
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
  /* 로드맵마다 확인하지 않은 부서장 코멘트 알림 */
  P.commentAlert = R => {
    const n = P.newComments(R).length;
    return n ? `<button class="alert" data-go="comment:${R.id}">${icon('chat')}<span class="grow"><b>${esc(P.cmBy(P.newComments(R).slice(-1)[0]))} 님이 이 로드맵에 코멘트를 남겼어요${n > 1 ? ` (${n}개)` : ''}</b><br><span class="small muted">평가가 아닌 계획 조정 의견이에요</span></span>${icon('right')}</button>` : '';
  };
  /* 다음 로드맵 제안은 결과 보고서에만 보여 준다. 홈 카드·'이 목표로 새 로드맵 작성'(목표 채우기)은 없앴다(10/14 사용자 결정) */

  /* ───────── 실행 기록 창 ───────── */
  P.STATUS = [['doing', '진행 중이에요'], ['done', '다 했어요']];
  P.recBody = function (a, R) {
    const pr = R.progress[a.id] || {}, r = a.res ? D.res[a.res] : null, t = S().tmp;
    return `<p class="small muted">${a.stage}단계 ${stageName(a.stage)} · ${a.wFrom === a.wTo ? a.wFrom : a.wFrom + '~' + a.wTo}주차 · ${hrs(a.hours)}</p>
      <p style="font-weight:650;font-size:17px;margin:4px 0 14px">${esc(a.title)}</p>
      ${a.task ? `<div class="callout soft">${icon('flag')}<div><b>직접 수행 과제</b><br>${esc(a.how)}</div></div>`
        : `<div class="callout soft">${icon('book')}<div><b>${esc(r.title)}</b><br>${esc(r.kind)} · ${esc(r.provider)}${r.real ? '' : ' · 가상 자료'} <button class="link" data-go="res:${a.res}">자료 보기</button></div></div>`}
      <div class="field" style="margin-top:22px"><label>어디까지 했나요?</label><div class="chips">${P.STATUS.map(([v, l]) => `<label class="chip"><input type="radio" name="recst" value="${v}" data-bind="tmp.status" ${t.status === v ? 'checked' : ''}>${l}</label>`).join('')}</div></div>
      <div class="field"><label>메모 <span class="muted small">선택</span></label><textarea class="textarea sm" data-bind="tmp.memo" placeholder="한 일, 막힌 점, 다음에 할 일">${esc(t.memo)}</textarea></div>
      <div class="field"><label>결과물·수료증 <span class="muted small">선택 · 파일 이름만 보관</span></label>${pr.file ? `<p class="small">${icon('file')} ${esc(pr.file.name)}</p>` : ''}<input class="input" type="file" data-bind-file="tmp.file"></div>
      ${P.note(`메모·첨부는 나만 봐요.${P.mySup() ? ` 완료 여부는 부서장 ${esc(P.mySup().name)} 님에게 진행 상태로 보여요.` : ''} 자료를 내지 않았다고 하지 않은 것으로 보지 않아요.`)}`;
  };
  /* arg: '로드맵 id|활동 id' */
  GP.act['rec-open'] = arg => {
    const [pid, id] = String(arg).split('|'), R = P.R(pid), a = R && R.plan.acts.find(x => x.id === id); if (!a) return;
    const pr = R.progress[id] || {};
    S().tmp = { pid, id, status: P.st(id, R.plan), memo: pr.memo || '', file: pr.file || null }; GP.save();
    GP.sheet(P.recBody(a, R), { title: '실행 기록', sub: R.plan.goal, foot: '<button class="btn pri" data-act="rec-save" data-need="tmpStatus">저장하기</button>' });
  };
  GP.act['rec-save'] = () => {
    const t = S().tmp; if (!t) return;
    P.record(t.id, t.status, t.memo, t.file, t.pid); S().tmp = null; GP.save();
    GP.closeSheet(); GP.render(false); GP.toast('실행 기록을 저장했어요');
  };

  /* ───────── 수정 요청 조작 (10/14) ─────────
     항목을 여러 개 골라(고른 항목만 값을 바꿈) 요청 문장을 덧붙인다. 항목 없이 문장만 적어도 된다.
     부서장 코멘트 반영은 코멘트를 요청 칸에 채워 시작하고, 직원이 고친 뒤 수정안을 만든다 */
  P.ensureRev = () => { const pl = S().plan; if (pl && (!S().rev || !S().rev.v)) { S().rev = P.freshRev(); GP.save(); } return S().rev; };
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
  function revCtl(k, r, pl) {
    const v = r.v, lab = (P.REV_ITEMS.find(x => x[0] === k) || [])[1];
    const num = (unit, attrs, ph, help) => `<div class="unit"><input class="input num" type="number" ${attrs} data-bind="rev.v.${k}" value="${esc(v[k])}" placeholder="${ph}" aria-label="${lab}"><span>${unit}</span></div><small class="muted">${help}</small>`;
    const actList = (path, sel) => `<div class="choices">${pl.acts.map(a => `<label class="choice"><input type="checkbox" value="${a.id}" data-bind-arr="${path}" ${sel.includes(a.id) ? 'checked' : ''}><span class="tx">${esc(a.title)}<small>${a.stage}단계 · ${P.actMeta(a)} · ${hrs(a.hours)}${P.st(a.id) === 'done' ? ' · 완료' : ''}</small></span><span class="ck">${icon('check')}</span></label>`).join('')}</div>`;
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
      const have = new Set(pl.acts.map(a => a.res).filter(Boolean));
      const list = Object.entries(D.res).filter(([id, x]) => x.kind !== '자격' && !have.has(id));
      return `<div class="choices">${list.map(([id, x]) => `<label class="choice"><input type="checkbox" value="${id}" data-bind-arr="rev.v.addRes" ${v.addRes.includes(id) ? 'checked' : ''}><span class="tx">${esc(x.title)}<small>${x.stage}단계 · ${x.kind} · ${esc(x.provider)} · ${hrs(x.hours)} · ${x.cost ? won(x.cost) : '무료'}${x.real ? '' : ' · 가상'}</small></span><span class="ck">${icon('check')}</span></label>`).join('') || '<p class="muted small">더 넣을 등록 자료가 없어요</p>'}</div>
        <textarea class="textarea sm" data-bind="rev.v.addTask" maxlength="400" aria-label="직접 할 과제" placeholder="직접 할 과제를 한 줄에 하나씩 적어 주세요 (선택)&#10;예: 부서 FAQ 20건으로 답변 품질 점검하기">${esc(v.addTask)}</textarea><small class="muted">자격증은 위 ‘자격증 계획’에서 바꿔요</small>`;
    }
    return '';
  }
  /* 왼쪽 확인란을 고르면 그 항목의 입력이 열린다 (지금 값으로 미리 채움) */
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
    R.rev = P.freshRev(); R.pending = null; GP.save(); GP.go('revise:' + R.id);
  };
  GP.act['rev-make'] = () => { if (GP.valid.revOk()) P.revise(); };
  GP.act['rev-newgoal'] = () => {
    const pl = S().plan; if (!pl) return;
    S().draft = GP.freshDraft(); S().draft.prefs = Object.assign(AI.emptyPrefs(), JSON.parse(JSON.stringify(pl.prefs || {})));
    S().draftPlan = null; S().rev = null; S().pending = null; GP.save(); GP.go('new-goal');
    GP.toast('지금 로드맵의 학습 여건을 채워 뒀어요. 새 목표를 적어 주세요');
  };
  GP.act['rev-accept'] = () => P.acceptRevision();
  GP.act['rev-drop'] = () => P.dropRevision();
  GP.act.confirm = () => P.confirm();

  /* ───────── 여러 메뉴가 함께 쓰는 화면 ───────── */
  const scr = GP.screens;

  /* 로드맵 하나를 다루는 화면: 주소의 로드맵 id 로 S.cur 을 맞춘다.
     id 가 없거나 틀리면 진행 중인 로드맵이 하나일 때만 그 로드맵으로, 아니면 fallback(목록)으로 보낸다 */
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
          <div class="row top">${icon('lock')}<span>활동 메모·첨부와 작성 중인 로드맵은 나만 봐요.${sup ? ' 결과 보고서에는 사전→사후 점검 응답 변화가 들어 있어요.' : ''}</span></div>
        </div></div>
        <div class="actions"><button class="btn pri" data-go="home">로드맵 시작하기</button><button class="btn line" data-go="roadmap:${pl.rid}">로드맵 보기</button></div>
        ${first && sup ? P.note(`시연: 로그아웃한 뒤 부서장 ${esc(sup.name)}(사번 ${esc(sup.code)})으로 로그인하면 이 로드맵에 코멘트를 남길 수 있어요.`) : ''}`;
    }
  };

  scr.revise = {
    nav: 'roadmap', title: '수정 요청', width: 'wide', guard: P.planGuard('revise', 'roadmap', true),
    render() {
      const base = P.revBase(); if (!base) return P.page({ title: '고칠 로드맵이 없어요', body: P.noPlan() });
      const r = P.ensureRev(), pd = S().pending, busy = P.revBusy();
      const pid = r.on.pid && r.v.pid !== base.opt ? r.v.pid : base.opt, agent = `${pid} ${D.perspectives[pid].name}`;
      const cm = r.fromComment && (P.R().comments || []).find(c => c.id === r.fromComment);
      const cmt = cm ? `<div class="callout soft rv-cmt">${icon('chat')}<div><b>부서장 코멘트 · ${esc(P.cmBy(cm))} · ${esc(cm.at)}</b><br><span class="small muted">아래 ‘요청 내용’에 채워 뒀어요. 반영할 부분만 남기고 수정안을 만들어 주세요. 확정하면 이 코멘트가 ‘v${base.version + 1}에 반영’으로 바뀌어요.</span></div></div>${P.commentView(cm)}` : '';
      /* 실패했을 때는 아래 실패 안내의 '다시 시도하기'만 둔다(같은 버튼이 두 개 보이지 않게) */
      const make = `${r.fail && !busy ? '' : `<div class="actions rv-act"><button class="btn ${pd ? 'line' : 'pri'}" data-act="rev-make" data-need="revOk">${busy ? '수정안을 만드는 중…' : pd ? '수정안 다시 만들기' : '수정안 만들기'}</button></div>`}
        <p class="small muted rv-hint" data-rvhint hidden>바꿀 항목을 고르거나 요청 내용을 적어 주세요. 고른 항목의 값이 맞는지도 확인해 주세요.</p>`;
      let out = '';
      if (busy) out = `<div class="agents">${P.agentRow({ st: 'run', name: `${agent} · 수정안 작성`, sub: P.runSub('roadmap', '고른 항목과 요청 내용을 반영하고 있어요') })}</div>`;
      else if (r.fail) out = P.failPage({
        title: '수정안을 만들지 못했어요', desc: `${esc(agent)} 에이전트가 수정안을 쓰지 못했어요. 지금 로드맵은 그대로이고, 고른 항목과 요청 내용도 그대로 남아 있어요.`,
        cause: esc(P.errText(r.fail.cause)),
        body: `<div class="agents">${P.agentRow({ st: 'fail', name: `${agent} · 수정안 작성`, sub: AI.live() ? `${AI.PROV[AI.mode()]} · ${esc(AI.modelName('roadmap'))}` : '', tag: '오류 발생', tagCls: 'fail' })}</div>`,
        ops: P.opsBox([['', r.fail.cause]]),
        foot: `<button class="btn pri" data-act="rev-make" data-need="revOk">${icon('retry')}다시 시도하기</button>`
      });
      else if (pd) out = `<div class="sec-h"><h2 class="st">수정안</h2>${pd.source && pd.source !== 'mock' ? `<span class="tag acc">${AI.PROV[pd.source] || 'API'} 작성</span>` : '<span class="tag">가데이터</span>'}</div>
        ${P.revKey(r) !== pd.key ? P.note('수정안을 만든 뒤 고른 항목이나 요청 내용을 바꿨어요. 바뀐 내용으로 보려면 ‘수정안 다시 만들기’를 눌러 주세요.') : ''}${P.diffView(pd)}`;
      return P.page({
        back: (r.fromComment ? 'comment:' : 'roadmap:') + base.rid, eyebrow: `${esc(base.name)} · v${base.version} · ${esc(base.goal)}`,
        title: '무엇을 바꿀까요?', lead: `여러 항목을 함께 골라도 돼요. 고른 항목과 요청 내용을 ${esc(agent)} 에이전트가 함께 보고 수정안을 먼저 보여 드려요. 확정하기 전까지 지금 로드맵은 그대로예요.`,
        body: `${cmt}${P.revForm(r, base)}${make}${out ? `<div class="sec" id="diffSec">${out}</div>` : ''}`,
        foot: pd && !busy && !r.fail ? `<button class="btn pri" data-act="rev-accept">v${base.version + 1}로 확정하기</button><button class="btn line" data-act="rev-drop">취소</button>` : ''
      });
    }
  };

  /* 부서장 코멘트 (10/14): 다시 보내도 덮어쓰지 않고 로드맵마다 쌓는다.
     상태: new 새 코멘트(부서장에게는 '확인 전') → read 확인함 → applied vN에 반영. 직원·부서장 화면에 같은 상태가 보인다. 답글은 없다 */
  P.cmTag = (c, mgr) => (c.status === 'applied' ? `<span class="tag ok">v${c.appliedVersion || ''}에 반영</span>`
    : c.status === 'read' ? '<span class="tag line">확인함</span>' : `<span class="tag acc">${mgr ? '확인 전' : '새 코멘트'}</span>`);
  /* mgr: 부서장 화면. 내가 보낸 코멘트는 '보낸 코멘트', 다른 부서장이 남긴 것은 그 이름 */
  P.cmItem = (c, foot, mgr) => `<div class="cm-item"><div class="cm-h"><b>${mgr && c.byCode && c.byCode === (GP.me() || {}).code ? '보낸 코멘트' : esc(P.cmBy(c))}</b><span class="small muted">${esc(c.at)}</span>${P.cmTag(c, mgr)}</div>${P.commentView(c)}${foot || ''}</div>`;
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
          <div class="callout soft" style="margin-top:16px">${icon('info')}<div>코멘트는 평가나 승인이 아니에요. ‘이 의견으로 수정안 받기’를 누르면 코멘트를 채운 수정 요청 화면이 열려요. 반영할 부분만 남겨 수정안을 만들고, 내가 확정해야 로드맵이 바뀌어요. 확인했는지와 몇 번째 버전에 반영했는지는 부서장에게도 보여요.</div></div>`
      });
    }
  };
  /* 코멘트를 요청 문장으로 채워 수정 요청 화면을 연다(바로 수정안을 만들지 않음 · 10/14) */
  const commentReq = c => {
    const lb = (list, v) => (list.find(x => x[0] === v) || [])[1] || '';
    const fit = c.fit && c.fit !== 'none' ? lb(D.commentFit, c.fit) : '', lv = c.level && c.level !== 'none' ? lb(D.commentLevel, c.level) : '';
    const line = (k, pick, text) => (text ? `${k}${pick ? `(${pick})` : ''}: ${text}` : pick ? `${k}: ${pick}` : '');
    return [line('업무 적합성', fit, c.fitText), line('수준·기간·분량', lv, c.levelText), c.free && `자유 의견: ${c.free}`].filter(Boolean).join('\n');
  };
  const cmOf = arg => { const [pid, cid] = String(arg).split('|'), R = P.R(pid); return { R, c: R && (R.comments || []).find(x => x.id === cid) }; };
  GP.act['comment-apply'] = arg => {
    const { R, c } = cmOf(arg); if (!c || R.status !== 'active') return;
    P.focus(R.id); R.rev = P.freshRev(commentReq(c), c.id); R.pending = null; GP.save(); GP.go('revise:' + R.id);
  };
  GP.act['comment-read'] = arg => {
    const { c } = cmOf(arg); if (!c) return;
    Object.assign(c, { status: 'read', readAt: D.today }); GP.save(); GP.render(false); GP.toast('코멘트를 확인했어요 · 부서장에게 ‘확인함’으로 보여요');
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

  let resKind = '전체';
  GP.act.resf = k => { resKind = k; GP.render(false); };
  P.resKv = r => `<dl class="kv" style="margin-top:4px">
    <dt>대상</dt><dd>${esc(r.audience)}</dd><dt>선수지식</dt><dd>${esc(r.prereq)}</dd><dt>내용</dt><dd>${esc(r.content)}</dd>
    <dt>시간·비용</dt><dd>${hrs(r.hours)} · ${r.cost == null ? '응시료 확인 필요' : won(r.cost)}${r.note ? `<br><span class="small muted">${esc(r.note)}</span>` : ''}</dd>
    <dt>출처</dt><dd>${esc(r.source)} · 확인일 ${esc(r.checked)}${r.url ? `<br><a class="link" href="${esc(r.url)}" target="_blank" rel="noopener">원문 열기 ${icon('out')}</a>` : ''}</dd></dl>`;
  scr.resources = {
    nav: 'resources', title: '학습 자료', width: 'wide',
    render() {
      const kinds = ['전체', '강좌', '도서', '공식 문서', '자격'];
      const list = Object.entries(D.res).filter(([, r]) => resKind === '전체' || r.kind === resKind);
      return P.page({
        eyebrow: '부록', title: '학습 자료', lead: '로드맵에 쓰는 등록된 교육·도서·자격·공식 문서예요. 직접 수행하는 실습 과제는 여기 없어요.',
        body: `<div class="chips" style="margin-bottom:16px">${kinds.map(k => `<button class="chip ${resKind === k ? 'on' : ''}" data-act="resf" data-arg="${k}">${k}</button>`).join('')}</div>
          <div class="list">${list.map(([, r]) => `<div class="li" style="display:block"><details class="more"><summary style="color:var(--ink);font-size:15px;display:flex;width:100%;gap:10px"><span class="grow"><b>${esc(r.title)}</b><small class="muted" style="display:block;font-weight:400;font-size:13px">${r.kind} · ${esc(r.provider)} · ${hrs(r.hours)} · ${r.cost == null ? '응시료 확인 필요' : won(r.cost)}</small></span>${r.real ? '<span class="tag line">실제 자료</span>' : '<span class="tag dash">가상</span>'}</summary>${P.resKv(r)}</details></div>`).join('')}</div>
          ${P.note('가상 자료는 화면 시연용이에요. 자격은 이름만 확인했고 일정·응시료·교육 인정 여부는 확인하지 않았어요.')}`
      });
    }
  };
  scr.res = {
    nav: 'resources', title: '학습 자료',
    render(id) {
      const r = D.res[id]; if (!r) return P.page({ back: 'resources', title: '자료를 찾을 수 없어요' });
      return P.page({ back: 'resources', eyebrow: `${r.kind} · ${r.real ? '실제 자료' : '가상 자료'}`, title: esc(r.title), lead: esc(r.provider), body: `<div class="card">${P.resKv(r)}</div>` });
    }
  };

  /* ───────── 부서장 (10/15: 계정 기반) ─────────
     부서장 권한이 있는 계정(가상 사내 DB 감독 그룹의 supervisor)만 들어온다. 자기 감독 그룹 소속 직원(DB '볼 수 있는 직원')의 기록만 본다.
     공개 범위: 확정 로드맵(버전)·활동 진행 상태·결과 보고서(전체)·받은 코멘트 기록. 활동 메모·첨부, 진단 수준값, 작성 중인 로드맵, 사전 점검 응답 화면은 보이지 않는다.
     소속 직원의 기록은 그 계정의 저장 칸에서 읽고(GP.stateOf), 화면 조각은 GP.asState 로 그 기록을 S 로 두고 그린다. 코멘트는 그 직원 기록에 쌓는다.
     주소: m-plan:<직원 id> · m-road:<직원 id>~<로드맵 id> · m-report:<직원 id>~<보고서 id> · m-done:<직원 id>~<로드맵 id> */
  const ST_TAG = { active: '', done: '<span class="tag line">마침</span>', archived: '<span class="tag line">보관</span>' };
  const mk = (uid, x) => `${uid}~${x}`;
  const mkSplit = p => String(p || '').split('~');
  P.myMembers = () => GP.members(GP.me());
  P.memberOf = uid => P.myMembers().find(e => e.id === uid) || null;
  const who = e => `${esc(e.name)} · ${esc(GP.meLine(e))}`;
  const av = e => `<span class="avatar">${esc(e.name.slice(1))}</span>`;
  P.teamRow = e => GP.asState(GP.stateOf(e.id), () => {
    const all = P.recs(), act = P.recs('active'), reps = S().reports.length, tag = GP.isSup(e) ? ' <span class="tag line">부서장</span>' : '';
    if (!all.length) return `<div class="li">${av(e)}<div class="tx"><b>${esc(e.name)}${tag}</b><small>${esc(GP.meLine(e))} · 확정한 로드맵 없음</small></div></div>`;
    const wait = act.reduce((n, R) => n + P.newComments(R).length, 0);
    return `<button class="li" data-go="m-plan:${e.id}">${av(e)}<div class="tx"><b>${esc(e.name)}${tag}</b><small>${esc(GP.meLine(e))} · 진행 중 ${act.length}개${all.length > act.length ? ` · 지난 로드맵 ${all.length - act.length}개` : ''}${reps ? ` · 결과 보고서 ${reps}개` : ''}</small></div><span class="end">${wait ? `<span class="tag acc">코멘트 확인 전 ${wait}</span>` : ''}${icon('right')}</span></button>`;
  });
  P.privacy = () => P.note('확정한 로드맵, 활동 진행 상태, 결과 보고서(사전→사후 점검 응답 변화 포함)를 볼 수 있어요. 활동 메모·첨부, 진단 수준값, 작성 중인 로드맵은 공개되지 않아요.');
  scr['m-list'] = {
    nav: 'm-list', role: 'mgr', title: '소속 직원 계획', width: 'wide',
    render() {
      const me = GP.me(), ms = P.myMembers();
      return P.page({ eyebrow: `부서장 · ${esc(me.name)} · 감독 그룹 ${esc(me.supGroup ? me.supGroup.name : '')}`, title: '소속 직원의 성장 로드맵',
        lead: `감독 그룹 소속 직원 ${ms.length}명이 확정한 로드맵과 진행 상태, 결과 보고서를 보고 계획 조정 의견을 남길 수 있어요.`,
        body: `<div class="list">${ms.map(P.teamRow).join('')}</div>${P.privacy()}${P.note('소속 직원은 가상 사내 DB의 감독 그룹에서 정해요. 그룹·부서장 권한은 인사 관리자가 바꿔요(관리자 기능은 아직 없음).')}` });
    }
  };
  /* 쓰는 중인 코멘트는 내(부서장) 기록에 로드맵마다 둔다(mgr['직원 id~로드맵 id']). 소속 직원 기록을 S 로 둔 채 그려도 내 기록에서 읽는다 */
  P.mgrDraft = key => {
    const own = GP.own(), m = own.mgr && typeof own.mgr === 'object' ? own.mgr : (own.mgr = {}), k = key || own.mcur || '_';
    if (!m[k] || typeof m[k] !== 'object') m[k] = {};
    return m[k];
  };
  P.mgrCommentFields = function (pid) {
    const m = P.mgrDraft(pid), b = `mgr.${pid}`;
    return `<div class="field"><label>업무 적합성 <span class="muted small">담당 업무·부서 AI 사업과 맞나요?</span></label>
        <div class="chips">${D.commentFit.map(([v, l]) => `<label class="chip"><input type="radio" name="mfit" value="${v}" data-bind="${b}.fit" ${m.fit === v ? 'checked' : ''}>${l}</label>`).join('')}</div>
        <textarea class="textarea sm" data-bind="${b}.fitText" placeholder="한두 문장으로 적어 주세요 (선택)">${esc(m.fitText)}</textarea></div>
      <div class="field"><label>수준·기간·분량 <span class="muted small">난이도와 기간이 적절한가요?</span></label>
        <div class="chips">${D.commentLevel.map(([v, l]) => `<label class="chip"><input type="radio" name="mlevel" value="${v}" data-bind="${b}.level" ${m.level === v ? 'checked' : ''}>${l}</label>`).join('')}</div>
        <textarea class="textarea sm" data-bind="${b}.levelText" placeholder="조정이 필요하면 무엇을 어떻게 (선택)">${esc(m.levelText)}</textarea></div>
      <div class="field"><label>자유 의견 <span class="muted small">선택</span></label><textarea class="textarea sm" data-bind="${b}.free" placeholder="계획 조정에 도움이 될 의견">${esc(m.free)}</textarea></div>`;
  };
  const mgrRoadRow = uid => R => {
    const pl = R.plan, c = P.count(pl), cs = R.comments || [], wait = P.newComments(R).length, mine = cs.filter(x => x.byCode === GP.me().code).length;
    return `<button class="li" data-go="m-road:${mk(uid, R.id)}"><span class="idx">${icon('map')}</span><div class="tx"><b>${esc(pl.goal)}</b><small>${esc(pl.name)} v${pl.version} · 활동 ${c.done}/${c.t} 완료${mine ? ` · 보낸 코멘트 ${mine}개` : ''}</small></div><span class="end">${ST_TAG[R.status] || ''}${wait ? `<span class="tag acc">확인 전 ${wait}</span>` : ''}${icon('right')}</span></button>`;
  };
  const mgrRepRow = uid => r => `<button class="li" data-go="m-report:${mk(uid, r.id)}"><span class="idx">${icon('chart')}</span><div class="tx"><b>결과 보고서 · ${esc(r.opt)} v${r.version}</b><small>${esc(r.goal)} · ${esc(r.createdAt)} · ${r.confirmed ? '직원 확인함' : '직원 확인 전'}</small></div><span class="end">${icon('right')}</span></button>`;
  scr['m-plan'] = {
    nav: 'm-list', role: 'mgr', title: '직원 로드맵', width: 'wide',
    guard: uid => (P.memberOf(uid) ? null : 'm-list'),
    render(uid) {
      const e = P.memberOf(uid);
      return GP.asState(GP.stateOf(uid), () => {
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
  /* 직원 로드맵 하나: 진행 상태, 결과 보고서, 코멘트 기록(상태 포함), 진행 중이면 새 코멘트 */
  scr['m-road'] = {
    nav: 'm-list', role: 'mgr', title: '직원 로드맵', width: 'wide',
    guard: param => {
      const [uid, pid] = mkSplit(param);
      if (!P.memberOf(uid)) return 'm-list';
      if (!GP.stateOf(uid).plans[pid]) return 'm-plan:' + uid;
      GP.own().mcur = mk(uid, pid); return null;
    },
    render(param) {
      const [uid, pid] = mkSplit(param), e = P.memberOf(uid), key = mk(uid, pid);
      return GP.asState(GP.stateOf(uid), () => {
        const R = S().plans[pid], pl = R.plan, live = R.status === 'active', cs = (R.comments || []).slice().reverse(), reps = P.planReports(R);
        const body = `<div class="card"><p class="eyebrow">${esc(pl.name)} · v${pl.version} · ${esc(R.createdAt)} 확정${live ? '' : R.status === 'done' ? ' · 마침' : ' · 보관'}</p><p style="font-weight:650;font-size:16px">${esc(pl.goal)}</p><div style="margin-top:16px">${P.stats(pl, true)}</div></div>
          <div class="sec"><div class="sec-h"><h2 class="st">단계별 진행</h2></div>${P.stagesView(pl, { status: true })}</div>
          ${reps.length ? `<div class="sec"><div class="sec-h"><h2 class="st">결과 보고서</h2></div><div class="list">${reps.map(mgrRepRow(uid)).join('')}</div></div>` : ''}${P.privacy()}
          ${cs.length ? `<div class="sec"><div class="sec-h"><h2 class="st">코멘트 기록 ${cs.length}</h2></div><div class="stack">${cs.map(c => P.cmItem(c, '', true)).join('')}</div></div>` : ''}
          ${live ? `<div class="sec"><div class="sec-h"><h2 class="st">${cs.length ? '새 코멘트' : '계획 조정 의견'}</h2><button class="link quiet" data-act="m-sample" data-arg="${key}">시연용 예시 문장</button></div><div class="card">${P.mgrCommentFields(key)}</div>
            ${P.note('보낸 코멘트는 덮어쓰지 않고 쌓여요. 직원이 확인했는지, 몇 번째 버전에 반영했는지 여기서 볼 수 있어요. 자동으로 반영되지 않고, 평가나 승인으로 쓰이지 않아요.')}</div>`
          : P.note(`직원이 ${R.status === 'done' ? '마친' : '보관한'} 로드맵이에요. 코멘트는 진행 중인 로드맵에만 보낼 수 있어요.`)}`;
        return P.page({ back: 'm-plan:' + uid, eyebrow: who(e), title: '확정한 로드맵', body, foot: live ? `<button class="btn pri" data-act="m-send" data-arg="${key}" data-need="mComment">코멘트 보내기</button>` : '' });
      });
    }
  };
  /* 소속 직원의 결과 보고서 (10/15 사용자 결정: 보고서 전체 공개). 읽기만 한다 */
  scr['m-report'] = {
    nav: 'm-list', role: 'mgr', title: '직원 결과 보고서', width: 'wide',
    guard: param => {
      const [uid, rid] = mkSplit(param);
      if (!P.memberOf(uid)) return 'm-list';
      return GP.stateOf(uid).reports.some(r => r.id === rid) ? null : 'm-plan:' + uid;
    },
    render(param) {
      const [uid, rid] = mkSplit(param), e = P.memberOf(uid);
      return GP.asState(GP.stateOf(uid), () => {
        const r = S().reports.find(x => x.id === rid), R = S().plans[r.planId];
        return P.page({
          back: R ? 'm-road:' + mk(uid, R.id) : 'm-plan:' + uid, eyebrow: `${who(e)} · 결과 보고서 · ${esc(r.opt)} v${r.version} · ${esc(r.createdAt)}`, title: '학습 결과 보고서', lead: esc(r.goal),
          body: `${P.reportBody(r)}${P.note(`${esc(e.name)} 님이 ${r.confirmed ? '확인한' : '아직 확인하지 않은'} 보고서예요. 부서장은 읽기만 할 수 있어요.`)}`
        });
      });
    }
  };
  GP.act['m-sample'] = key => { const c = D.commentSample; Object.assign(P.mgrDraft(key), { fit: c.fit, fitText: c.fitText, level: c.level, levelText: c.levelText, free: c.free }); GP.save(); GP.render(false); };
  /* 코멘트 보내기: 소속 직원의 기록(그 계정 저장 칸)에 쌓는다. 쓰던 칸은 내 기록에서 비운다 */
  GP.act['m-send'] = key => {
    const [uid, pid] = mkSplit(key), me = GP.me();
    if (!P.memberOf(uid) || !GP.valid.mComment()) return;
    const st = GP.stateOf(uid), R = st.plans[pid]; if (!R || R.status !== 'active') return;
    const m = P.mgrDraft(key);
    R.comments = R.comments || [];
    R.comments.push({ id: 'c' + (R.comments.length + 1), by: me.name, byCode: me.code, fit: m.fit, fitText: m.fitText || '', level: m.level, levelText: m.levelText || '', free: m.free || '', at: D.today, status: 'new' });
    GP.saveState(st);
    GP.own().mgr[key] = {}; GP.save(); GP.go('m-done:' + key);
  };
  scr['m-done'] = {
    nav: 'm-list', role: 'mgr', title: '코멘트 전달',
    guard: param => (P.memberOf(mkSplit(param)[0]) ? null : 'm-list'),
    render(param) {
      const [uid, pid] = mkSplit(param), e = P.memberOf(uid);
      return `<div class="badge-ico">${icon('send')}</div>
      <h1 class="t lg">${esc(e.name)} 님에게 코멘트를 보냈어요</h1>
      <p class="lead">직원이 반영을 요청하고 수정안을 확정해야 로드맵이 바뀌어요. 직원이 확인했는지와 반영했는지는 이 로드맵의 ‘코멘트 기록’에서 볼 수 있어요. 코멘트는 평가나 승인으로 쓰이지 않아요.</p>
      <div class="actions">${GP.stateOf(uid).plans[pid] ? `<button class="btn pri" data-go="m-road:${mk(uid, pid)}">코멘트 기록 보기</button>` : ''}<button class="btn line" data-go="m-list">소속 직원 계획으로</button></div>
      ${P.note(`시연: 로그아웃한 뒤 ${esc(e.name)}(사번 ${esc(e.code)})으로 로그인하면 받은 코멘트를 볼 수 있어요.`)}`;
    }
  };
})();

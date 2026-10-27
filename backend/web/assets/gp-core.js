/* GrowPath 5차 목업 (Claude) · 공통 엔진
   계정(서버 로그인 · 직원/관리자), 상태(서버 기록 + 화면 상태), 화면 이동, 입력 연결, 좌측 메뉴, 시연 도구, 가운데 창, 알림.
   5차: 기록은 서버(팀 DB)가 갖는다. 브라우저 저장소에는 화면 상태(지금 화면·펼침·쓰는 중인 양식)와 테마만 둔다.
   작성 중인 로드맵의 입력(목표·세부 사항·응답 등)은 고칠 때마다 잠깐 기다렸다가 서버에 저장한다(GP.syncDraft) */
(function () {
  'use strict';
  const D = window.GPD, API = window.GPAPI;
  const THEMES = [
    ['green', '그린', '#0E7C66'], ['blue', '블루', '#2F5BEA'], ['purple', '퍼플', '#6B4FD8'],
    ['coral', '코랄', '#CF5136'], ['charcoal', '차콜', '#35383E']
  ];
  const THEME_KEY = 'gp5c.theme', UI_KEY = id => 'gp5c.ui.' + id;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장 불가 환경 */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* 저장 불가 환경 */ } }
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const won = n => (n ? Number(n).toLocaleString('ko-KR') + '원' : '0원');
  const hrs = n => (Number.isInteger(+n) ? +n : Number(n).toFixed(1)) + '시간';

  const P = {
    home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z', plus: 'M12 5v14M5 12h14', minus: 'M5 12h14',
    pen: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z', map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14',
    chart: 'M4 20V11M10 20V5M16 20v-6M21 20H3', book: 'M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5zM5 19.5A1.5 1.5 0 0 0 6.5 21H19',
    users: 'M16 20v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 20v-1a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8',
    chat: 'M20.5 12a8.5 8.5 0 0 1-12.3 7.6L3.5 21l1.4-4.6A8.5 8.5 0 1 1 20.5 12z', scale: 'M12 3v18M5 7h14M7 7l-3 7a3 3 0 0 0 6 0zM17 7l-3 7a3 3 0 0 0 6 0zM8 21h8',
    check: 'M5 12.5l4.5 4.5L19 7', left: 'M15 18l-6-6 6-6', right: 'M9 6l6 6-6 6', arrow: 'M5 12h14M13 6l6 6-6 6', x: 'M6 6l12 12M18 6 6 18',
    file: 'M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8zM14 3v5h5',
    spark: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z',
    send: 'M21 3 10 14M21 3l-7 18-4-7-7-4z', info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 7.5h.01', edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
    flag: 'M5 21V4M5 4h11l-2 4 2 4H5', out: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
    alert: 'M12 9v4M12 17h.01M10.3 3.9 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z', history: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2',
    retry: 'M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4', stop: 'M7 7h10v10H7z', lock: 'M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z',
    eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6', logout: 'M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3',
    user: 'M20 21v-1a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8', cpu: 'M9 9h6v6H9zM5 5h14v14H5zM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3',
    logo: 'M4 17l5-5 4 4 7-8M15 8h5v5', db: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6',
    upload: 'M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3', download: 'M12 4v12M7 11l5 5 5-5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
    play: 'M7 4.5v15l12-7.5z', award: 'M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM8.5 13.5 7 22l5-3 5 3-1.5-8.5'
  };
  const icon = (n, cls) => `<svg class="i ${cls || ''}" viewBox="0 0 24 24" aria-hidden="true"><path d="${P[n] || ''}"/></svg>`;

  /* ── 상태 ──
     S: 지금 화면이 쓰는 기록(평소에는 로그인한 직원의 기록 OWN). 부서장 화면은 GP.asState 로 잠깐 소속 직원의 기록(서버가 공개 범위만 줌)을 S 로 둔다.
     서버 기록: draft·draftId·draftPlan·lastNew(작성 중인 로드맵) · plans(확정 로드맵) · reports(결과 보고서)
     화면 상태(브라우저 저장소): route·demoOpen·cur·mgr(쓰는 중인 코멘트)·mcEdit(고치는 중인 보낸 코멘트 키)·revs(쓰는 중인 수정 요청)·tmp·meEdit·regenReq */
  let S = null, OWN = null;
  const UI_FIELDS = ['route', 'demoOpen', 'cur', 'mgr', 'mcEdit', 'tmp', 'meEdit', 'regenReq', 'picks', 'resQ'];
  const saveUi = () => {
    if (!OWN || !OWN.owner) return;
    const ui = Object.fromEntries(UI_FIELDS.map(k => [k, OWN[k]]));
    ui.revs = Object.fromEntries(Object.entries(OWN.plans || {}).filter(([, R]) => R.rev).map(([id, R]) => [id, Object.assign({}, R.rev, { running: false, fail: null })]));
    store.set(UI_KEY(OWN.owner), JSON.stringify(ui));
  };
  const readUi = id => { try { return JSON.parse(store.get(UI_KEY(id)) || '{}') || {}; } catch (e) { return {}; } };
  const save = () => { saveUi(); if (GP.syncDraft) GP.syncDraft(); };
  const getP = path => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), S);
  function setP(path, val) {
    const ks = path.split('.');
    let o = S;
    ks.slice(0, -1).forEach(k => { if (o[k] == null || typeof o[k] !== 'object') o[k] = {}; o = o[k]; });
    o[ks[ks.length - 1]] = val;
  }

  const GP = window.GP = {
    D, THEMES, esc, won, hrs, icon, store, API,
    get S() { return S; }, set S(v) { if (v && !v.owner && OWN) v.owner = OWN.owner; S = v; OWN = v; },
    save, saveState: () => {}, getP, setP, screens: {}, act: {}, valid: {}, cleanup: null
  };

  /* ── 계정 (서버 로그인) ──
     직원: 사번 + 비밀번호(시연 초기 비밀번호 · .env 의 GP5_DEMO_PASSWORD) · 관리자: 관리자 아이디(직원과 별개 계정 · 2026-10-21 사용자 결정).
     계정은 로그아웃한 뒤 다시 로그인해야만 바뀐다. 부서장 권한·소속 직원은 서버가 부서 계층으로 정한다 */
  GP.ACCOUNT = null;        // {accountType: 'employee'|'admin', user?, admin?}
  GP.ACCTS = [];            // 로그인 화면 '직원 고르기'(시연 전용)
  GP.TEAM = null;           // 부서장: 소속 직원 목록(서버)
  GP.MEMBERS = {};          // 부서장: 소속 직원 기록(서버 · 공개 범위만)
  GP.me = () => (GP.ACCOUNT && GP.ACCOUNT.accountType === 'employee' ? GP.ACCOUNT.user : null);
  GP.isAdmin = () => !!(GP.ACCOUNT && GP.ACCOUNT.accountType === 'admin');
  GP.isSup = e => !!(e && e.supervisor && (e.members || []).length);
  GP.acct = id => (GP.me() && GP.me().id === String(id) ? GP.me() : ((GP.TEAM && GP.TEAM.members) || []).map(m => m.user).find(u => u.id === String(id)) || null);
  GP.members = () => ((GP.TEAM && GP.TEAM.members) || []).map(m => m.user);
  GP.own = () => OWN;
  GP.session = () => GP.ACCOUNT;

  /* 서버 작업 공간(작성 중인 로드맵·확정 로드맵·보고서)을 받아 상태를 만든다 */
  GP.fromWorkspace = function (w, id) {
    const st = GP.fresh();
    st.owner = id;
    Object.assign(st, readUi(id));
    st.plans = {};
    const revs = st.revs || {}; delete st.revs;
    Object.entries(w.plans || {}).forEach(([pid, R]) => { st.plans[pid] = GP.prepRec(R, revs[pid]); });
    st.reports = w.reports || [];
    GP.mergeRes(w.res); if (GP.AI) GP.AI.mergeReg(w.reg);
    GP.takeDraftInto(st, w.draft || {});
    if (st.cur && !st.plans[st.cur]) st.cur = null;
    return st;
  };
  /* 로드맵 기록 하나를 화면 형식으로: 쓰는 중인 수정 요청(rev)은 브라우저에 두고, 서버 수정안 상태를 이어 붙인다 */
  GP.prepRec = function (R, rev) {
    R.rev = rev || null;
    const rv = R.revision;
    if (rv && R.rev) {
      R.rev.running = rv.status === 'running';
      R.rev.fail = rv.status === 'failed' ? (rv.error || {}) : null;
      R.rev.jobId = rv.status === 'running' ? rv.jobId : null;
    } else if (rv && rv.status !== 'ready' && rv.request) {
      R.rev = Object.assign({ on: {}, v: {}, note: '' }, rv.request, { running: rv.status === 'running', fail: rv.status === 'failed' ? (rv.error || {}) : null, jobId: rv.jobId });
    }
    if (R.pending && R.rev == null && rv && rv.request) R.rev = Object.assign({ on: {}, v: {}, note: '' }, rv.request);
    R.post = R.post || { answers: {}, goalSelf: '', file: null };
    return R;
  };
  GP.putRec = function (R, st) {
    st = st || OWN; if (!st || !R) return null;
    const old = st.plans[R.id];
    st.plans[R.id] = GP.prepRec(R, old && old.rev ? Object.assign({}, old.rev) : null);
    if (old && old.rev && !R.revision) st.plans[R.id].rev = old.rev.running ? null : old.rev;
    return st.plans[R.id];
  };
  GP.mergeRes = res => { Object.entries(res || {}).forEach(([k, r]) => { D.res[k] = r; }); };
  GP.load = async function () {
    if (!GP.me()) { S = OWN = Object.assign(GP.fresh(), { owner: null }); return; }
    const w = await API.workspace();
    S = OWN = GP.fromWorkspace(w, GP.me().id);
  };
  GP.reload = async function () { const route = OWN && OWN.route; await GP.load(); if (route) OWN.route = route; };
  GP.asState = (st, fn) => { const prev = S; S = st; try { return fn(); } finally { S = prev; } };
  /* 부서장: 소속 직원 기록 (없으면 불러온 뒤 다시 그린다) */
  const memberState = (uid, w) => {
    const st = GP.fresh(); st.owner = uid;
    st.plans = Object.fromEntries(Object.entries(w.plans || {}).map(([k, R]) => [k, GP.prepRec(R, null)]));
    st.reports = w.reports || []; GP.mergeRes(w.res); GP.AI.mergeReg(w.reg);
    return st;
  };
  GP.stateOf = function (uid) {
    const m = GP.MEMBERS[uid];
    if (m && m.st) return m.st;
    if (!m) {
      GP.MEMBERS[uid] = { loading: true };
      API.teamMember(uid).then(w => { GP.MEMBERS[uid] = { st: memberState(uid, w) }; render(false); })
        .catch(err => { GP.MEMBERS[uid] = { st: Object.assign(GP.fresh(), { owner: uid, loadError: GP.AI.cause(err) }) }; render(false); });
    }
    return Object.assign(GP.fresh(), { owner: uid, loading: true });
  };
  /* 저장 뒤 다시 읽기: 받은 다음에 바꿔 끼워 화면이 '불러오는 중'으로 깜빡이지 않게 한다 */
  GP.reloadMember = async uid => { GP.MEMBERS[uid] = { st: memberState(uid, await API.teamMember(uid)) }; };
  GP.loadTeam = async function (force) {
    if (!GP.isSup(GP.me())) { GP.TEAM = null; return; }
    if (GP.TEAM && !force) return;
    try { GP.TEAM = await API.team(); } catch (e) { GP.TEAM = { members: [], error: GP.AI.cause(e) }; }
    if (force) GP.MEMBERS = {};
  };

  /* ── 화면 이동 ── */
  GP.go = function (r, opts) {
    if (!(opts && opts.force) && GP.beforeGo && GP.beforeGo(r) === false) return;
    if (GP.cleanup) { GP.cleanup(); GP.cleanup = null; }
    GP.prev = S.route;
    S.route = r; save();
    if (decodeURIComponent(location.hash.slice(1)) !== r) history.pushState(null, '', '#' + r);
    render(!(opts && opts.keepScroll));
  };
  window.addEventListener('popstate', () => {
    const r = decodeURIComponent(location.hash.slice(1));
    if (r && S && r !== S.route) { if (GP.cleanup) { GP.cleanup(); GP.cleanup = null; } S.route = r; save(); render(true); }
  });

  let side, view, rib;
  function render(top) {
    const acct = GP.ACCOUNT;
    document.body.classList.toggle('auth', !acct);
    document.body.classList.toggle('admin', GP.isAdmin());
    if (!acct) {
      side.innerHTML = ''; view.className = 'view login'; view.innerHTML = GP.screens.login.render();
      rib.querySelector('.mode').outerHTML = modeChip(); document.title = 'GrowPath · 로그인';
      if (GP.onRender) GP.onRender(GP.screens.login, 'login');
      GP.screens.login.after(view); refresh(); if (top) window.scrollTo(0, 0);
      return;
    }
    if (GP.isAdmin()) return GP.renderAdmin ? GP.renderAdmin(side, view, rib, top) : null;
    const me = GP.me();
    S = OWN;
    let [id, param] = String(S.route || 'home').split(':');
    let sc = GP.screens[id];
    if (!sc || sc.role === 'admin' || (sc.role === 'mgr' && !GP.isSup(me))) {
      id = 'home'; sc = GP.screens[id]; S.route = id; save();
      history.replaceState(null, '', '#' + id);
    }
    param = String(S.route).split(':').slice(1).join(':') || undefined;
    if (sc.guard) { const to = sc.guard(param); if (to && to !== S.route) { S.route = to; save(); history.replaceState(null, '', '#' + to); return render(top); } }
    if (sc.newStep) S.lastNew = S.route;
    side.innerHTML = sidebar(typeof sc.nav === 'function' ? sc.nav(param) : sc.nav);
    rib.querySelector('.mode').outerHTML = modeChip();
    view.className = 'view ' + (sc.width || '');
    view.innerHTML = sc.render(param);
    document.title = 'GrowPath · ' + (sc.title || '');
    if (GP.onRender) GP.onRender(sc, id);
    if (sc.after) sc.after(view, param);
    refresh();
    if (top) window.scrollTo(0, 0);
  }
  GP.render = render;

  function refresh() {
    document.querySelectorAll('[data-need]').forEach(b => {
      b.disabled = !b.dataset.need.split(',').every(k => (GP.valid[k] ? GP.valid[k]() : !!getP(k)));
    });
    if (GP.onRefresh) GP.onRefresh();
  }
  GP.refresh = refresh;

  /* ── 입력 연결 ── */
  function onField(e) {
    const el = e.target;
    if (el.matches('[data-bind-arr]')) {
      const path = el.dataset.bindArr, arr = (getP(path) || []).slice(), i = arr.indexOf(el.value);
      if (el.checked && i < 0) arr.push(el.value);
      if (!el.checked && i >= 0) arr.splice(i, 1);
      setP(path, arr);
      if (GP.onBindChange) GP.onBindChange(path);
    } else if (el.matches('[data-bind-file]')) {
      if (e.type !== 'change') return;
      const f = el.files && el.files[0];
      setP(el.dataset.bindFile, f ? { name: f.name, size: f.size } : null);
      if (GP.onFile) GP.onFile(el.dataset.bindFile, f);
      save(); if (GP.onBindChange) GP.onBindChange(el.dataset.bindFile);
      render(false); return;
    } else if (el.matches('[data-bind]')) {
      if (el.type === 'radio' && !el.checked) return;
      let v = el.value;
      if (el.type === 'number') v = el.value === '' ? '' : Number(el.value);
      setP(el.dataset.bind, v);
      document.querySelectorAll(`[data-act="set"][data-arg^="${el.dataset.bind}="]`).forEach(b => b.classList.toggle('on', b.dataset.arg === `${el.dataset.bind}=${v}`));
      if (GP.onBindChange) GP.onBindChange(el.dataset.bind, e.type);
    } else if (el.matches('[data-jump]')) {
      if (e.type === 'change' && el.value) GP.jump(el.value);
      return;
    } else if (el.matches('[name="gp-prov"]')) {
      if (e.type === 'change') {
        const AI = GP.AI, p = el.value;
        AI.setChoice(p).then(() => {
          AI.resetConn(); render(false);
          GP.toast(AI.demoMock() ? `${AI.PROV[p]}로 바꿨어요 · 지금은 시연 도구에서 가데이터로 보는 중이에요` : AI.available(p) ? `${AI.PROV[p]}로 에이전트를 호출해요` : `${AI.PROV[p]}를 지금 쓸 수 없어요 · 가데이터로 자동 대체하지 않아요`);
          if (AI.live()) AI.ping();
        }).catch(err => GP.toast(GP.AI.cause(err).user));
      }
      return;
    } else if (el.matches('[name="gp-demomock"]')) {
      if (e.type === 'change') {
        const AI = GP.AI;
        AI.setDemoMock(el.checked).then(() => { AI.resetConn(); render(false); GP.toast(el.checked ? '시연용 가데이터로 보여요' : AI.off() ? `${AI.PROV[AI.choice()]}를 지금 쓸 수 없어요 · 가데이터로 자동 대체하지 않아요` : `${AI.PROV[AI.choice()]} 기준으로 돌아왔어요`); if (AI.live()) AI.ping(); })
          .catch(err => GP.toast(GP.AI.cause(err).user));
      }
      return;
    } else if (el.matches('[name="gp-fail"]')) {
      if (e.type === 'change') GP.AI.setFailSim(el.value, el.checked).then(() => GP.toast(el.checked ? '다음 생성의 첫 시도가 실패해요. 다시 시도하면 성공해요' : '실패 시연을 껐어요'));
      return;
    } else return;
    save(); refresh();
    if (el.dataset.rerender != null && e.type === 'change') render(false);
  }
  document.addEventListener('input', onField);
  document.addEventListener('change', onField);

  document.addEventListener('click', e => {
    const g = e.target.closest('[data-go]');
    if (g && !g.disabled) { e.preventDefault(); GP.closeSheet(); GP.go(g.dataset.go); return; }
    const a = e.target.closest('[data-act]');
    if (a && !a.disabled) {
      const fn = GP.act[a.dataset.act];
      if (fn) { e.preventDefault(); fn(a.dataset.arg, a, e); }
    }
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') GP.closeSheet(); });

  GP.act.set = function (arg, el) {
    const i = arg.indexOf('='), path = arg.slice(0, i), raw = arg.slice(i + 1);
    const v = raw !== '' && !isNaN(raw) && !/^0\d/.test(raw) ? Number(raw) : raw;
    setP(path, v); save();
    document.querySelectorAll(`[data-bind="${path}"]`).forEach(inp => { if (inp.type !== 'radio') inp.value = v; else inp.checked = String(inp.value) === String(v); });
    document.querySelectorAll(`[data-act="set"][data-arg^="${path}="]`).forEach(b => b.classList.toggle('on', b === el));
    if (GP.onBindChange) GP.onBindChange(path);
    if (el && el.dataset.rerender != null) render(false); else refresh();
  };

  /* ── 가운데 창 ── */
  GP.sheet = function (inner, opts) {
    GP.closeSheet();
    const ov = document.createElement('div');
    ov.className = 'ov'; ov.id = 'sheet';
    ov.innerHTML = `<div class="sheet ${opts && opts.wide ? 'wide' : ''}" role="dialog" aria-modal="true">
      <div class="sheet-h"><div><b>${esc(opts && opts.title)}</b>${opts && opts.sub ? `<small>${esc(opts.sub)}</small>` : ''}</div>
      <button class="x" data-act="sheet-close" aria-label="닫기">${icon('x')}</button></div>
      <div class="sheet-b">${inner}</div>${opts && opts.foot ? `<div class="sheet-f">${opts.foot}</div>` : ''}</div>`;
    ov.addEventListener('mousedown', e => { if (e.target === ov) GP.closeSheet(); });
    document.body.appendChild(ov);
    refresh();
    return ov;
  };
  GP.closeSheet = function () { const s = document.getElementById('sheet'); if (s) s.remove(); };
  GP.act['sheet-close'] = () => GP.closeSheet();

  let toastT;
  GP.toast = function (msg) {
    let t = document.getElementById('toast');
    if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 2600);
  };
  /* 서버 요청 실패를 쉬운 말로 알린다(원문은 콘솔에만) */
  GP.fail = function (err, what) {
    if (err && err.name === 'AbortError') return;
    const c = GP.AI.cause(err);
    console.warn('GrowPath', what || '', c.raw || err);
    GP.toast(`${what ? what + ' · ' : ''}${c.user}`);
  };

  /* ── 테마 색상 ── */
  function applyTheme(key) {
    const t = THEMES.find(x => x[0] === key) || THEMES[0];
    document.documentElement.style.setProperty('--accent', t[2]);
    return t[0];
  }
  GP.theme = applyTheme(store.get(THEME_KEY) || 'green');
  GP.act.theme = function (key) { GP.theme = applyTheme(key); store.set(THEME_KEY, key); document.querySelectorAll('.theme button').forEach(b => b.classList.toggle('on', b.dataset.arg === key)); };

  /* ── 초기화·단계 이동·로그아웃 (로그인한 계정의 기록만 · 서버) ── */
  const dataReset = () => { if (GP.onDataReset) GP.onDataReset(); };
  GP.act.reset = function () {
    const me = GP.me(); if (!me) return;
    GP.sheet(`<p style="margin-top:0"><b>${esc(me.name)}</b> 님의 기록을 모두 지우고 처음 상태로 돌려요.</p>
      <ul class="plain-list small"><li>지우는 것: 확정한 로드맵(진행 중·지난 로드맵), 작성 중인 로드맵, 점검 응답·결과 보고서, 받은 코멘트 (서버 DB에서)</li>
      <li>그대로 두는 것: 내 정보(인사 정보·본인 입력)·목표 후보${GP.isSup(me) ? ', 소속 직원의 로드맵과 기록' : ''}</li></ul>`,
      { title: '처음 상태로 초기화할까요?', foot: '<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="reset-ok">초기화</button>' });
  };
  GP.act['reset-ok'] = async function () {
    GP.closeSheet();
    try { await API.demoReset(); await GP.reload(); dataReset(); GP.go('home'); GP.toast('내 기록을 처음 상태로 돌렸어요'); } catch (err) { GP.fail(err, '초기화하지 못했어요'); }
  };
  GP.jump = async function (stage) {
    const me = GP.me(); if (!me) { GP.toast('로그인한 뒤 단계로 이동할 수 있어요'); return; }
    if (stage === 'comment' && !me.mySupervisor) { GP.toast('내 계획을 보는 부서장이 없는 계정이라 이 단계는 쓸 수 없어요'); render(false); return; }
    GP.toast('시연 데이터를 서버에 만드는 중이에요…');
    try {
      const r = await API.demoJump(stage);
      await GP.reload(); OWN.demoOpen = true; dataReset();
      GP.go(r.entry || 'home', { force: true });
    } catch (err) { GP.fail(err, '단계로 이동하지 못했어요'); render(false); }
  };
  GP.act.logout = async function () {
    try { await GP.flush(); await API.logout(); } catch (e) { /* 이미 끊긴 세션이어도 화면은 로그아웃 */ }
    GP.ACCOUNT = null; GP.TEAM = null; GP.MEMBERS = {}; S = OWN = Object.assign(GP.fresh(), { owner: null, route: 'home' });
    if (!GP.ACCTS.length) { try { const a = await API.accounts(); GP.ACCTS = a.accounts || []; GP.DEMO = a; } catch (e) { GP.ACCTS = []; } }
    GP.closeSheet(); dataReset(); render(true); GP.toast('로그아웃했어요');
  };

  /* ── 에이전트 기록 (서버 메모리 · 본인만) ── */
  GP.act['agent-log'] = async function () {
    const L = await GP.AI.loadLog();
    const tag = m => ({ ollama: '<span class="tag acc">RunPod-Ollama</span>', api: '<span class="tag acc">OpenAI API</span>', mock: '<span class="tag">가데이터</span>', error: '<span class="tag fail">호출 오류 · 실패 안내</span>', sim: '<span class="tag fail">실패 시연</span>', off: '<span class="tag fail">모드 사용 불가 · 실패 안내</span>', stop: '<span class="tag">사용자가 멈춤</span>' }[m]);
    GP.sheet(L.length ? `<div class="log">${L.map(e => `<details class="logi"><summary><span class="muted small num">${esc(e.at)}</span><b>${esc(e.agent)}</b><span class="grow small">${esc(e.task)}${e.model && e.mode !== 'mock' ? ` · ${esc(e.model)}` : ''}</span>${tag(e.mode) || ''}<span class="small muted num">${e.ms}ms</span></summary>
        ${e.error ? `<p class="small" style="color:var(--warn);margin:8px 0">${esc(e.error)}</p>` : ''}<p class="small muted" style="margin-top:8px">입력</p><pre>${esc(e.input)}</pre><p class="small muted">출력</p><pre>${esc(e.output)}</pre></details>`).join('')}</div>`
      : '<p class="muted">아직 호출한 에이전트가 없어요.</p>', { title: '에이전트 동작 기록', sub: '최근 호출이 위에 보여요 · 서버 메모리에만 있어 서버를 다시 켜면 지워져요 (DB에는 처리 시간·결과 같은 기록만 남아요)', wide: true });
  };

  /* ── 좌측 메뉴 ── */
  function modeChip() {
    const AI = GP.AI;
    if (!GP.ACCOUNT) return '<span class="mode"></span>';
    if (!AI || GP.isAdmin()) return `<span class="mode api">${GP.isAdmin() ? '관리자 화면' : ''}</span>`;
    const m = AI.mode();
    if (m === 'off') return `<span class="mode mock">${AI.PROV[AI.choice()]} · 지금 쓸 수 없어요</span>`;
    return `<span class="mode ${m === 'mock' ? 'mock' : 'api'}">${m === 'mock' ? '시연용 가데이터' : `${AI.PROV[m]} · ${esc(AI.modelName('default'))}`}</span>`;
  }
  GP.modeChip = modeChip;
  GP.aimStatus = function () {
    const AI = GP.AI, P = GP.P;
    if (AI.demoMock()) return '<i class="d off"></i><span>시연 도구에서 가데이터로 보는 중</span>';
    if (!AI.live()) {
      const why = AI.unavailableWhy(AI.choice());
      return `<i class="d error"></i><div class="aim-tx">지금 쓸 수 없어요<small>서버 연결과 모델 설정을 확인해 주세요. 자동 대체하지 않아요. 연결한 뒤 다시 시도해 주세요.</small>${P.opsBox([['', { text: why, hint: '.env를 고친 뒤 서버(목업_실행.cmd)를 다시 실행해 주세요. 가데이터로 보려면 시연 도구에서 직접 켜 주세요' }]], 'sm')}</div>`;
    }
    const c = AI.connFor('all'), st = c.state === 'idle' ? 'checking' : c.state;
    const t = { ok: '연결됨', cold: '연결됨 · 모델 준비 중', checking: '연결 확인 중…', error: '연결 안 됨' }[st];
    return `<i class="d ${st}"></i><div class="aim-tx">${t}${st === 'error' ? `<small>${esc(AI.userText(c.kind))}</small>${P.connOps(c, 'sm')}`
      : st === 'cold' ? `<small>첫 응답은 1~2분 걸릴 수 있어요</small>${P.coldOps(c, 'sm')}` : ''}</div>`;
  };
  function aiBox() {
    const AI = GP.AI, cur = AI.choice(), ol = AI.status.ollama || {};
    const opt = (p, l, sub) => `<label class="aim-o"><input type="radio" name="gp-prov" value="${p}" ${cur === p ? 'checked' : ''}><span><b>${l}</b><small>${AI.available(p) ? sub : '지금 쓸 수 없어요'}</small></span></label>`;
    return `<div class="aim" role="radiogroup" aria-label="AI 모델"><span class="lbl">AI 모델</span>
      ${opt('ollama', 'RunPod-Ollama', `로컬 LLM·sLLM · ${esc(ol.model)}${ol.roadmapModel && ol.roadmapModel !== ol.model ? ` 외 1` : ''}`)}
      ${opt('api', 'OpenAI API', esc(AI.status.model))}
      <div class="aim-st" id="aimSt" aria-live="polite">${GP.aimStatus()}</div></div>`;
  }
  GP.onConn = function () { const a = document.getElementById('aimSt'); if (a) a.innerHTML = GP.aimStatus(); if (rib) rib.querySelector('.mode').outerHTML = modeChip(); };
  function modeBox() {
    const AI = GP.AI, st = AI.status;
    const srv = !st.checked ? '확인 중…' : !st.server ? '서버에 연결하지 못했어요' : `RunPod-Ollama ${AI.available('ollama') ? '설정됨' : '없음'} · OpenAI ${AI.available('api') ? '설정됨' : '없음'} (.env)`;
    return `<div class="foot-lbl">에이전트 데이터</div>
      <label class="radio"><input type="checkbox" name="gp-demomock" ${AI.demoMock() ? 'checked' : ''}>가데이터로 보기</label>
      <p class="small muted" style="margin:2px 0 8px 24px;font-size:11.5px;line-height:1.4">${srv}<br>사용자 모드는 좌측 ‘AI 모델’에서 골라요 · 서버가 가데이터 응답을 만들어요</p>
      <div class="foot-lbl" style="margin-top:4px">생성 실패 시연</div>
      ${[['goal', '목표 후보 제안'], ['doc', '기획서 읽기(이미지·요약)'], ['quiz', '사전 점검 문항 생성'], ['diag', '점검 결과(수준 진단)'], ['gen', '로드맵 3안 (A2·A3)'], ['sup', '지원 조건 확인'], ['report', '결과 보고서'], ['reg', '사내 생활 도우미 답변'], ['rev', '수정안 작성']].map(([k, l]) => `<label class="radio"><input type="checkbox" name="gp-fail" value="${k}" ${AI.failSim()[k] ? 'checked' : ''}>${l}</label>`).join('')}
      <p class="small muted" style="margin:2px 0 8px 24px;font-size:11.5px;line-height:1.4">켜 두면 첫 시도만 실패해요</p>`;
  }
  GP.meLine = e => [e.dept, e.grade, e.position].filter(Boolean).join(' · ');
  function sidebar(active) {
    const me = GP.me(), sup = GP.isSup(me);
    const newComment = GP.P && GP.P.recs('active').some(R => GP.P.newComments(R).length);
    const drafting = GP.draftActive && GP.draftActive();
    const items = [['home', '홈', 'home', newComment], [GP.newRoute ? GP.newRoute() : 'new-goal', '새 로드맵 작성', 'pen', drafting, 'new'], ['roadmap', '내 로드맵', 'map'], ['checks', '점검·보고서', 'chart'], ['me', '내 정보', 'user']];
    const link = ([r, l, ic, dot, key]) => `<a href="#${r}" data-go="${r}" class="${active === (key || r) ? 'on' : ''}">${icon(ic)}${l}${dot ? '<span class="dot" aria-label="알림"></span>' : ''}</a>`;
    return `
      <div class="brand"><span class="logo">${icon('logo')}</span>GrowPath</div>
      <a class="me ${active === 'me' ? 'on' : ''}" href="#me" data-go="me" aria-label="내 정보 보기 · ${esc(me.name)}" title="내 정보 보기"><span class="avatar">${esc(me.name.slice(1))}</span><div class="grow"><b>${esc(me.name)}${sup ? '<span class="me-sup">부서장</span>' : ''}</b><small>${esc(GP.meLine(me))}</small></div>${icon('right', 'me-go')}</a>
      <nav class="nav" aria-label="주 메뉴">${items.map(link).join('')}</nav>
      ${sup ? `<nav class="nav nav-appx nav-sup" aria-label="부서장"><span class="lbl">부서장</span>${link(['m-list', '소속 직원 계획', 'users'])}</nav>` : ''}
      <nav class="nav nav-appx" aria-label="부록">
        <span class="lbl">부록</span>
        <a href="#resources" data-go="resources" class="${active === 'resources' ? 'on' : ''}">${icon('book')}학습 자료</a>
      </nav>
      ${aiBox()}
      <div class="side-foot">
        <div><div class="foot-lbl">테마 색상</div>
          <div class="theme" role="group" aria-label="테마 색상">
            ${THEMES.map(([k, n, c]) => `<button style="background:${c}" class="${GP.theme === k ? 'on' : ''}" data-act="theme" data-arg="${k}" title="${n}" aria-label="${n}"></button>`).join('')}
          </div></div>
        <details class="demo" ${S.demoOpen ? 'open' : ''}><summary>${icon('right')}시연 도구</summary>
          ${modeBox()}
          <button class="btn line sm" data-act="agent-log">${icon('cpu')}에이전트 동작 보기</button>
          <select data-jump aria-label="시연 단계로 이동 (내 기록만 바꿈)"><option value="">단계로 바로 이동…</option>${(GP.JUMPS || []).map(([k, l]) => (k === 'comment' && !me.mySupervisor ? `<option value="${k}" disabled>${l} (부서장 없는 계정)</option>` : `<option value="${k}">${l}</option>`)).join('')}</select>
          <p class="small muted" style="margin:2px 0 6px;font-size:11.5px;line-height:1.4">단계 이동·초기화는 로그인한 계정(${esc(me.name)})의 서버 기록만 바꿔요</p>
          <button class="btn line sm" data-act="reset">처음 상태로 초기화</button>
        </details>
        <button class="btn ghost sm logout" data-act="logout" aria-label="로그아웃">${icon('logout')}<span class="lbl">로그아웃</span></button>
      </div>`;
  }
  GP.sidebar = sidebar;
  document.addEventListener('toggle', e => { if (e.target.matches && e.target.matches('details.demo') && S) { S.demoOpen = e.target.open; saveUi(); } }, true);

  /* ── 시작 ── */
  /* 로그인한 뒤에만 읽을 수 있는 값(모델 설정·자격증 목록·규정 묶음)은 계정이 정해질 때 읽는다 */
  GP.setAccount = async function (acct) {
    GP.ACCOUNT = acct;
    if (acct) await Promise.all([GP.AI.checkStatus(), GP.loadCatalog(), GP.AI.loadRegSets()]);
    if (acct && acct.accountType === 'employee') { GP.AI.applySettings(acct); await GP.load(); await GP.loadTeam(true); }
    else S = OWN = Object.assign(GP.fresh(), { owner: acct && acct.admin ? 'admin-' + acct.admin.id : null, route: 'admin' });
  };
  GP.loadCatalog = async function () {
    try {
      D.certGroups = await API.certifications();
      D.certById = {};
      D.certGroups.forEach(g => g.certs.forEach(c => { c.group = g.key; c.issuer = c.issuer || g.issuer; D.certById[c.id] = c; }));
    } catch (e) { D.certGroups = []; D.certById = {}; }
  };
  GP.boot = async function () {
    document.body.insertAdjacentHTML('afterbegin', `
      <header class="ribbon"><b>GrowPath 5차 목업 · Claude</b><span class="vlabel">팀 DB(PostgreSQL) · FastAPI · RunPod-Ollama·OpenAI API 시연</span><span class="mode"></span></header>
      <div class="app"><aside class="side" id="side"></aside><main class="main"><div id="view" class="view"><div class="loading" style="margin:60px auto"><span class="sp"></span><span>서버에서 불러오는 중…</span></div></div></main></div>`);
    side = document.getElementById('side'); view = document.getElementById('view'); rib = document.querySelector('.ribbon');
    let acct = null;
    try { acct = await API.me(); } catch (e) { acct = null; }
    try { await GP.setAccount(acct); } catch (err) { GP.fail(err, '기록을 불러오지 못했어요'); await GP.setAccount(null); }
    if (!acct) { try { const a = await API.accounts(); GP.ACCTS = a.accounts || []; GP.DEMO = a; } catch (e) { GP.ACCTS = []; } }
    const h = decodeURIComponent(location.hash.slice(1));
    if (h && S) S.route = h;
    history.replaceState(null, '', location.pathname + '#' + (S.route || 'home'));
    render(true);
    if (GP.me() && GP.AI.live()) GP.AI.ping();
  };
})();

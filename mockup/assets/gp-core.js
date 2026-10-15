/* GrowPath 4차 목업 (Claude) · 공통 엔진
   계정(가상 사내 DB 직원 · 계정별 기록), 상태 저장, 화면 이동, 입력 연결, 좌측 메뉴, 시연 도구(테마·데이터 모드·에이전트 기록), 가운데 창, 알림 */
(function () {
  'use strict';
  const D = window.GPD;
  const THEMES = [
    ['green', '그린', '#0E7C66'], ['blue', '블루', '#2F5BEA'], ['purple', '퍼플', '#6B4FD8'],
    ['coral', '코랄', '#CF5136'], ['charcoal', '차콜', '#35383E']
  ];
  /* 진행 기록은 계정마다 따로 저장한다(10/15): gp4c.state.<직원 id>. 예전 한 칸 저장(gp4c.state)·목표 후보 프로필 선택(gp4c.profile)은 쓰지 않는다 */
  const KEY = 'gp4c.state', THEME_KEY = 'gp4c.theme', OLD_KEYS = ['gp4c.state', 'gp4c.profile'];
  const keyOf = id => KEY + '.' + id;

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장 불가 환경 */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* 저장 불가 환경 */ } }
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const won = n => (n ? Number(n).toLocaleString('ko-KR') + '원' : '0원');
  const hrs = n => (Number.isInteger(+n) ? +n : Number(n).toFixed(1)) + '시간';

  const P = {
    home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
    plus: 'M12 5v14M5 12h14',
    pen: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z',
    map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14',
    chart: 'M4 20V11M10 20V5M16 20v-6M21 20H3',
    book: 'M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5zM5 19.5A1.5 1.5 0 0 0 6.5 21H19',
    users: 'M16 20v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 20v-1a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8',
    chat: 'M20.5 12a8.5 8.5 0 0 1-12.3 7.6L3.5 21l1.4-4.6A8.5 8.5 0 1 1 20.5 12z',
    scale: 'M12 3v18M5 7h14M7 7l-3 7a3 3 0 0 0 6 0zM17 7l-3 7a3 3 0 0 0 6 0zM8 21h8',
    check: 'M5 12.5l4.5 4.5L19 7',
    left: 'M15 18l-6-6 6-6',
    right: 'M9 6l6 6-6 6',
    arrow: 'M5 12h14M13 6l6 6-6 6',
    x: 'M6 6l12 12M18 6 6 18',
    file: 'M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8zM14 3v5h5',
    spark: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z',
    send: 'M21 3 10 14M21 3l-7 18-4-7-7-4z',
    info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 7.5h.01',
    edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
    flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
    out: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
    alert: 'M12 9v4M12 17h.01M10.3 3.9 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
    history: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2',
    retry: 'M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4',
    stop: 'M7 7h10v10H7z',
    lock: 'M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z',
    eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6',
    logout: 'M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3',
    user: 'M20 21v-1a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
    cpu: 'M9 9h6v6H9zM5 5h14v14H5zM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3',
    logo: 'M4 17l5-5 4 4 7-8M15 8h5v5'
  };
  const icon = (n, cls) => `<svg class="i ${cls || ''}" viewBox="0 0 24 24" aria-hidden="true"><path d="${P[n] || ''}"/></svg>`;

  /* ── 상태 ──
     S: 지금 화면이 쓰는 기록(평소에는 로그인한 계정의 기록 OWN). 부서장 화면은 GP.asState 로 잠깐 소속 직원의 기록을 S 로 둔다.
     기록마다 owner(직원 id)가 있어 저장할 때 그 계정 칸에만 쓴다. 로그인 전에는 owner 없는 빈 기록(저장 안 함) */
  let S = null, OWN = null;
  const saveState = st => { if (st && st.owner) store.set(keyOf(st.owner), JSON.stringify(st)); };
  const save = () => saveState(S);
  const getP = path => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), S);
  function setP(path, val) {
    const ks = path.split('.');
    let o = S;
    ks.slice(0, -1).forEach(k => { if (o[k] == null || typeof o[k] !== 'object') o[k] = {}; o = o[k]; });
    o[ks[ks.length - 1]] = val;
  }

  /* 시연용 로그인 세션 { acct: 직원 id, remember } (실제 인증 없음). '로그인 상태 유지'면 localStorage, 아니면 sessionStorage.
     예전 형식({ role, id } · 김하늘·이서준 시연 계정)은 로그인하지 않은 것으로 본다 */
  const SESS = 'gp4c.session';
  let memSession = null;
  const session = () => { try { const v = sessionStorage.getItem(SESS) || localStorage.getItem(SESS); const o = v ? JSON.parse(v) : memSession; return o && o.acct ? o : null; } catch (e) { return memSession; } };
  const setSession = (v, remember) => {
    memSession = v;
    try { sessionStorage.removeItem(SESS); localStorage.removeItem(SESS); if (v) (remember ? localStorage : sessionStorage).setItem(SESS, JSON.stringify(v)); } catch (e) { /* 저장 불가 환경은 메모리만 */ }
  };

  /* 새로 압축을 푼 폴더에서 처음 실행하면 이 브라우저에 남은 목업 기록(진행 상태·로그인·AI 모델 선택·시연 도구·테마)을 모두 지운다.
     server.py 로 열면 폴더마다 처음 실행 때 만드는 설치 표식(.cache/install-id · 공유 zip 에 안 들어감)으로,
     index.html 을 바로 열면 폴더 경로로 구분한다. 같은 폴더에서 다시 실행하면 이어서 쓴다 */
  const INSTALL_KEY = 'gp4c.install';
  const installId = () => (GP.AI.status.installId ? 'srv:' + GP.AI.status.installId
    : location.protocol === 'file:' ? 'file:' + decodeURIComponent(location.pathname.replace(/[^/]*$/, '')) : null);
  function resetIfNewInstall() {
    const id = installId(); if (!id) return false;
    let removed = 0;
    try {
      if (localStorage.getItem(INSTALL_KEY) === id) return false;
      [localStorage, sessionStorage].forEach(st => Object.keys(st).filter(k => /^gp4c/.test(k)).forEach(k => { if (k !== INSTALL_KEY) removed++; st.removeItem(k); }));
      localStorage.setItem(INSTALL_KEY, id);
    } catch (e) { return false; }
    memSession = null;
    return removed > 0;
  }

  const GP = window.GP = {
    D, THEMES, esc, won, hrs, icon, store,
    /* 기록을 통째로 바꿀 때(단계 이동·초기화)는 로그인한 계정의 기록으로 바꾼다. owner 는 이어 받는다 */
    get S() { return S; }, set S(v) { if (v && !v.owner && OWN) v.owner = OWN.owner; S = v; OWN = v; },
    save, saveState, getP, setP, session, setSession, screens: {}, act: {}, valid: {}, cleanup: null
  };

  /* ── 계정 (10/15) ──
     가상 사내 DB 직원(employees.js · 엑셀 초안 2.7.0)만 계정으로 쓴다. 사번 + 비밀번호(시연 초기 비밀번호 0000)로 로그인하고,
     계정은 로그아웃한 뒤 다시 로그인해야만 바뀐다(시연 도구의 계정 전환 없음).
     부서장 권한·볼 수 있는 직원은 DB 감독 그룹 열에서 정한다(권한 부여는 추후 관리자 기능). 부서장은 자기 감독 그룹 소속 직원의 기록만 본다 */
  GP.PW = '0000';
  GP.accts = () => (window.GPEMP && window.GPEMP.employees) || [];
  GP.acct = id => GP.accts().find(e => e.id === id) || null;
  GP.acctByCode = code => GP.accts().find(e => e.code === String(code || '').trim()) || null;
  /* 내 정보에서 고친 본인 입력(업무 설명·경험·기술 스택·자격·교육·프로젝트)과 평정 학습 사용 동의. 이 브라우저에만 둔다(엑셀 원본 그대로).
     { self: { profile, certs, learning, tech, projects }, consent: { 평정 기간: true/false }, at } */
  const ME_KEY = id => 'gp4c.me.' + id;
  GP.meEdits = id => { try { return JSON.parse(store.get(ME_KEY(id)) || 'null'); } catch (e) { return null; } };
  GP.setMeEdits = (id, v) => (v && (v.self || (v.consent && Object.keys(v.consent).length)) ? store.set(ME_KEY(id), JSON.stringify(v)) : store.del(ME_KEY(id)));
  /* DB 값에 고친 본인 입력을 덮은 프로필. 인사 정보(사번·부서·직급·감독 그룹 등)는 DB 값 그대로 */
  GP.profileOf = id => {
    const e = GP.acct(id); if (!e) return null;
    const x = GP.meEdits(id) || {}, self = x.self, cs = x.consent || {};
    return Object.assign({}, e, self ? { profile: self.profile, certs: self.certs, learning: self.learning, tech: self.tech, projects: self.projects } : {}, {
      evals: (e.evals || []).map(v => (v.period in cs ? Object.assign({}, v, { consent: cs[v.period] }) : v)),
      edited: !!self, editedAt: x.at || null
    });
  };
  GP.me = () => { const ss = session(); return ss ? GP.profileOf(ss.acct) : null; };
  GP.isSup = e => !!(e && e.supervisor && (e.members || []).length);
  GP.members = e => ((e && e.members) || []).map(m => GP.acctByCode(m.code)).filter(Boolean);
  GP.own = () => OWN;

  /* 기록 읽기: 저장된 값을 지금 형식으로 맞춘다 */
  function parseState(raw, owner) {
    let st = null;
    try {
      if (raw) {
        /* 예전(로드맵 하나) 저장 형식이면 로드맵 기록 형식으로 옮긴다(4차 묶음 6 · gp-parts 의 GP.migrateState) */
        st = Object.assign(GP.fresh(), GP.migrateState(JSON.parse(raw)));
        /* 10/13 이전(대화로 받던) 학습 선호 형식이면 작성 중인 로드맵만 새로 시작 */
        if (!st.draft || !st.draft.prefs || !('etc' in st.draft.prefs)) st.draft = GP.freshDraft();
      }
    } catch (e) { st = null; /* 손상된 값 무시 */ }
    st = st || GP.fresh();
    st.owner = owner || null; delete st.role;
    return st;
  }
  /* 로그인한 계정의 기록을 불러온다. id 가 없으면(로그인 전) 저장하지 않는 빈 기록 */
  GP.load = function (id) { S = OWN = parseState(id ? store.get(keyOf(id)) : null, id); };
  /* 다른 계정의 기록(부서장 화면 · 소속 직원). 고친 뒤에는 GP.saveState 로 그 계정 칸에 저장한다 */
  GP.stateOf = id => (OWN && OWN.owner === id ? OWN : parseState(store.get(keyOf(id)), id));
  /* fn 을 도는 동안 S 를 그 기록으로 둔다(로드맵·보고서 화면 조각을 소속 직원 기록으로 그릴 때) */
  GP.asState = (st, fn) => { const prev = S; S = st; try { return fn(); } finally { S = prev; } };

  /* ── 화면 이동 ── */
  GP.go = function (r, opts) {
    /* 화면 쪽에서 이동 전에 확인할 것이 있으면(앞 단계를 고친 채로 넘어가기 등) 멈춘다. force 면 묻지 않고 이동 */
    if (!(opts && opts.force) && GP.beforeGo && GP.beforeGo(r) === false) return;
    if (GP.cleanup) { GP.cleanup(); GP.cleanup = null; }
    GP.prev = S.route;
    S.route = r; save();
    if (decodeURIComponent(location.hash.slice(1)) !== r) history.pushState(null, '', '#' + r);
    render(!(opts && opts.keepScroll));
  };
  window.addEventListener('popstate', () => {
    const r = decodeURIComponent(location.hash.slice(1));
    if (r && r !== S.route) { if (GP.cleanup) { GP.cleanup(); GP.cleanup = null; } S.route = r; save(); render(true); }
  });

  let side, view, rib;
  function render(top) {
    const sess = session(), me = sess && GP.acct(sess.acct);
    document.body.classList.toggle('auth', !me);
    if (!me) {
      if (S && S.owner) GP.load(null);
      side.innerHTML = ''; view.className = 'view login'; view.innerHTML = GP.screens.login.render();
      rib.querySelector('.mode').outerHTML = modeChip(); document.title = 'GrowPath · 로그인';
      if (GP.onRender) GP.onRender(GP.screens.login, 'login');
      GP.screens.login.after(view); refresh(); if (top) window.scrollTo(0, 0);
      return;
    }
    if (!OWN || OWN.owner !== me.id) GP.load(me.id);
    S = OWN;
    let [id, param] = S.route.split(':');
    let sc = GP.screens[id];
    /* 부서장 화면(role: 'mgr')은 부서장 권한이 있는 계정만 */
    if (!sc || (sc.role === 'mgr' && !GP.isSup(me))) {
      id = 'home'; sc = GP.screens[id]; S.route = id; save();
      history.replaceState(null, '', '#' + id);
    }
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
    } else if (el.matches('[data-bind-file]')) {
      if (e.type !== 'change') return;
      const f = el.files && el.files[0];
      setP(el.dataset.bindFile, f ? { name: f.name, size: f.size } : null);
      save(); if (GP.onBindChange) GP.onBindChange(el.dataset.bindFile);
      /* 기획서처럼 내용을 읽어야 하는 파일은 화면 쪽에 파일을 넘긴다(묶음 3) */
      if (GP.onFile) GP.onFile(el.dataset.bindFile, f);
      render(false); return;
    } else if (el.matches('[data-bind]')) {
      if (el.type === 'radio' && !el.checked) return;
      let v = el.value;
      if (el.type === 'number') v = el.value === '' ? '' : Number(el.value);
      setP(el.dataset.bind, v);
      document.querySelectorAll(`[data-act="set"][data-arg^="${el.dataset.bind}="]`).forEach(b => b.classList.toggle('on', b.dataset.arg === `${el.dataset.bind}=${v}`));
      if (GP.onBindChange) GP.onBindChange(el.dataset.bind);
    } else if (el.matches('[data-jump]')) {
      if (e.type === 'change' && el.value) GP.jump(el.value);
      return;
    } else if (el.matches('[name="gp-prov"]')) {
      /* 좌측 'AI 모델': 사용자가 RunPod-Ollama / OpenAI API 중 고른다 */
      if (e.type === 'change') {
        const AI = GP.AI, p = el.value; AI.setChoice(p); AI.resetConn(); render(false);
        GP.toast(AI.demoMock() ? `${AI.PROV[p]}로 바꿨어요 · 지금은 시연 도구에서 가데이터로 보는 중이에요` : AI.available(p) ? `${AI.PROV[p]}로 에이전트를 호출해요` : `${AI.PROV[p]}를 지금 쓸 수 없어 가데이터로 보여요`);
        if (AI.live()) AI.ping();
      }
      return;
    } else if (el.matches('[name="gp-demomock"]')) {
      if (e.type === 'change') { const AI = GP.AI; AI.setDemoMock(el.checked); AI.resetConn(); render(false); GP.toast(el.checked ? '시연용 가데이터로 보여요' : `${AI.PROV[AI.choice()]} 기준으로 돌아왔어요`); if (AI.live()) AI.ping(); }
      return;
    } else if (el.matches('[name="gp-fail"]')) {
      if (e.type === 'change') { GP.AI.setFailSim(el.value, el.checked); GP.toast(el.checked ? '다음 생성의 첫 시도가 실패해요. 다시 시도하면 성공해요' : '실패 시연을 껐어요'); }
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
    clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 2400);
  };

  /* ── 테마 색상 ── */
  function applyTheme(key) {
    const t = THEMES.find(x => x[0] === key) || THEMES[0];
    document.documentElement.style.setProperty('--accent', t[2]);
    return t[0];
  }
  GP.theme = applyTheme(store.get(THEME_KEY) || 'green');
  GP.act.theme = function (key) { GP.theme = applyTheme(key); store.set(THEME_KEY, key); document.querySelectorAll('.theme button').forEach(b => b.classList.toggle('on', b.dataset.arg === key)); };

  /* ── 초기화·단계 이동·로그아웃 (10/15: 로그인한 계정의 기록만) ── */
  /* 초기화·단계 이동·로그아웃 때 화면 밖에 남는 기록(사내 생활 도우미 대화)도 지운다 */
  const dataReset = () => { if (GP.onDataReset) GP.onDataReset(); };
  /* 처음 상태로 초기화: 로그인한 직원의 로드맵·작성 중인 로드맵·점검·보고서·받은 코멘트만 지운다.
     부서장으로 로그인했어도 소속 직원의 기록은 건드리지 않고, 내 정보에서 고친 본인 입력도 그대로 둔다 */
  GP.act.reset = function () {
    const me = GP.me(); if (!me) return;
    GP.sheet(`<p style="margin-top:0"><b>${esc(me.name)}</b> 님의 기록을 모두 지우고 처음 상태로 돌려요.</p>
      <ul class="plain-list small"><li>지우는 것: 확정한 로드맵(진행 중·지난 로드맵), 작성 중인 로드맵, 점검 응답·결과 보고서, 받은 코멘트</li>
      <li>그대로 두는 것: 내 정보(인사 정보·본인 입력)${GP.isSup(me) ? ', 소속 직원의 로드맵과 기록' : ''}</li></ul>`,
      { title: '처음 상태로 초기화할까요?', foot: '<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="reset-ok">초기화</button>' });
  };
  GP.act['reset-ok'] = function () {
    if (!OWN || !OWN.owner) return;
    GP.closeSheet(); GP.S = GP.fresh(); save(); dataReset(); GP.go('home'); GP.toast('내 기록을 처음 상태로 돌렸어요');
  };
  /* 단계로 바로 이동: 로그인한 계정의 기록을 그 단계의 시연 데이터로 바꾼다. 다른 계정의 기록은 만들거나 바꾸지 않는다 */
  GP.jump = function (stage) {
    const me = GP.me(); if (!me) { GP.toast('로그인한 뒤 단계로 이동할 수 있어요'); return; }
    if (stage === 'comment' && !me.mySupervisor) { GP.toast('내 계획을 보는 부서장이 없는 계정이라 이 단계는 쓸 수 없어요'); render(false); return; }
    GP.S = GP.seed(stage); save(); dataReset();
    GP.go(GP.entry[stage] || 'home');
  };
  GP.act.logout = function () { setSession(null); GP.load(null); GP.closeSheet(); dataReset(); render(true); GP.toast('로그아웃했어요'); };

  /* ── 에이전트 기록 ── */
  GP.act['agent-log'] = function () {
    const L = GP.AI.log;
    const tag = m => ({ ollama: '<span class="tag acc">RunPod-Ollama</span>', api: '<span class="tag acc">OpenAI API</span>', mock: '<span class="tag">가데이터</span>', error: '<span class="tag fail">호출 오류 · 실패 안내</span>', sim: '<span class="tag fail">실패 시연</span>', stop: '<span class="tag">사용자가 멈춤</span>' }[m]);
    GP.sheet(L.length ? `<div class="log">${L.map(e => `<details class="logi"><summary><span class="muted small num">${esc(e.at)}</span><b>${esc(e.agent)}</b><span class="grow small">${esc(e.task)}${e.model && e.mode !== 'mock' ? ` · ${esc(e.model)}` : ''}</span>${tag(e.mode)}<span class="small muted num">${e.ms}ms</span></summary>
        ${e.error ? `<p class="small" style="color:var(--warn);margin:8px 0">${esc(e.error)}</p>` : ''}<p class="small muted" style="margin-top:8px">입력</p><pre>${esc(e.input)}</pre><p class="small muted">출력</p><pre>${esc(e.output)}</pre></details>`).join('')}</div>`
      : '<p class="muted">아직 호출한 에이전트가 없어요.</p>', { title: '에이전트 동작 기록', sub: '최근 호출이 위에 보여요 · 이 브라우저 창을 닫으면 지워져요', wide: true });
  };

  /* ── 좌측 메뉴 ── */
  function modeChip() {
    const AI = GP.AI, m = AI ? AI.mode() : 'mock';
    return `<span class="mode ${m === 'mock' ? 'mock' : 'api'}">${m === 'mock' ? '시연용 가데이터' : `${AI.PROV[m]} · ${esc(AI.modelName('default'))}`}</span>`;
  }
  /* 좌측 메뉴 아래 'AI 모델': 사용자가 고르는 모드와 연결 상태 (직원 화면) */
  /* 사용자에게는 쉬운 상태와 할 일만, 원인·조치(.env·Pod·GPU)는 '자세히 보기(운영자용)'에 접어 둔다(10/14) */
  GP.aimStatus = function () {
    const AI = GP.AI, P = GP.P;
    if (AI.demoMock()) return '<i class="d off"></i><span>시연 도구에서 가데이터로 보는 중</span>';
    if (!AI.live()) {
      const why = AI.unavailableWhy(AI.choice());
      return `<i class="d off"></i><div class="aim-tx">지금 쓸 수 없어 가데이터로 보여요${P.opsBox([['', { text: why, hint: AI.status.server ? '.env를 고친 뒤 server.py를 다시 실행해 주세요' : '목업_실행.cmd(server.py)로 열어 주세요' }]], 'sm')}</div>`;
    }
    const c = AI.connFor('all'), st = c.state === 'idle' ? 'checking' : c.state;
    const t = { ok: '연결됨', cold: '연결됨 · 모델 준비 중', checking: '연결 확인 중…', error: '연결 안 됨' }[st];
    return `<i class="d ${st}"></i><div class="aim-tx">${t}${st === 'error' ? `<small>${esc(AI.userText(c.kind))}</small>${P.connOps(c, 'sm')}`
      : st === 'cold' ? `<small>첫 응답은 1~2분 걸릴 수 있어요</small>${P.coldOps(c, 'sm')}` : ''}</div>`;
  };
  function aiBox() {
    const AI = GP.AI, cur = AI.choice(), ol = AI.status.ollama;
    const opt = (p, l, sub) => `<label class="aim-o"><input type="radio" name="gp-prov" value="${p}" ${cur === p ? 'checked' : ''}><span><b>${l}</b><small>${AI.available(p) ? sub : '지금 쓸 수 없어요'}</small></span></label>`;
    return `<div class="aim" role="radiogroup" aria-label="AI 모델"><span class="lbl">AI 모델</span>
      ${opt('ollama', 'RunPod-Ollama', `로컬 LLM·sLLM · ${esc(ol.model)}${ol.roadmapModel && ol.roadmapModel !== ol.model ? ` 외 1` : ''}`)}
      ${opt('api', 'OpenAI API', esc(AI.status.model))}
      <div class="aim-st" id="aimSt" aria-live="polite">${GP.aimStatus()}</div></div>`;
  }
  /* 연결 상태가 바뀌면 좌측 'AI 모델'과 상단 띠를 고친다 (화면별 표시는 gp-app 이 이어 붙임) */
  GP.onConn = function () { const a = document.getElementById('aimSt'); if (a) a.innerHTML = GP.aimStatus(); if (rib) rib.querySelector('.mode').outerHTML = modeChip(); };
  function modeBox() {
    const AI = GP.AI, st = AI.status;
    const srv = !st.checked ? '확인 중…' : !st.server ? 'server.py로 열지 않아 가데이터만 쓸 수 있어요' : `RunPod-Ollama ${st.ollama.configured ? '설정됨' : '없음'} · OpenAI ${st.key ? '설정됨' : '없음'} (.env)`;
    return `<div class="foot-lbl">에이전트 데이터</div>
      <label class="radio"><input type="checkbox" name="gp-demomock" ${AI.demoMock() ? 'checked' : ''}>가데이터로 보기</label>
      <p class="small muted" style="margin:2px 0 8px 24px;font-size:11.5px;line-height:1.4">${srv}<br>사용자 모드는 좌측 ‘AI 모델’에서 골라요</p>
      <div class="foot-lbl" style="margin-top:4px">생성 실패 시연</div>
      ${[['goal', '목표 후보 제안'], ['doc', '기획서 읽기(이미지·요약)'], ['quiz', '사전 점검 문항 생성'], ['diag', '점검 결과(수준 진단)'], ['gen', '로드맵 3안 (A2·A3)'], ['sup', '지원 조건 확인'], ['report', '결과 보고서'], ['reg', '사내 생활 도우미 답변'], ['rev', '수정안 작성']].map(([k, l]) => `<label class="radio"><input type="checkbox" name="gp-fail" value="${k}" ${AI.failSim()[k] ? 'checked' : ''}>${l}</label>`).join('')}
      <p class="small muted" style="margin:2px 0 8px 24px;font-size:11.5px;line-height:1.4">켜 두면 첫 시도만 실패해요</p>`;
  }
  /* 좌측 위 계정 칸: 로그인한 직원. 누르면 내 정보 */
  GP.meLine = e => [e.dept, e.grade, e.position].filter(Boolean).join(' · ');
  function sidebar(active) {
    const me = GP.me(), sup = GP.isSup(me);
    /* 진행 중인 로드맵 중 하나라도 확인하지 않은 부서장 코멘트가 있으면 홈에 점 */
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
          <p class="small muted" style="margin:2px 0 6px;font-size:11.5px;line-height:1.4">단계 이동·초기화는 로그인한 계정(${esc(me.name)})의 기록만 바꿔요</p>
          <button class="btn line sm" data-act="reset">처음 상태로 초기화</button>
        </details>
        <button class="btn ghost sm logout" data-act="logout" aria-label="로그아웃">${icon('logout')}<span class="lbl">로그아웃</span></button>
      </div>`;
  }
  document.addEventListener('toggle', e => { if (e.target.matches && e.target.matches('details.demo')) { S.demoOpen = e.target.open; save(); } }, true);

  /* ── 시작 ── */
  GP.boot = async function () {
    await GP.AI.checkStatus();
    const cleared = resetIfNewInstall();
    if (cleared) GP.theme = applyTheme('green');
    /* 계정별 저장(10/15) 전의 한 칸 기록·목표 후보 프로필 선택은 쓰지 않으므로 지운다(시연 인물 김하늘·이서준 계정이 없어짐) */
    OLD_KEYS.forEach(k => store.del(k));
    const ss = session();
    if (!ss || !GP.acct(ss.acct)) setSession(null);
    GP.load(session() ? session().acct : null);
    document.body.insertAdjacentHTML('afterbegin', `
      <header class="ribbon"><b>GrowPath 4차 목업 · Claude</b><span class="vlabel">3차 v2.8 기반 · RunPod-Ollama·OpenAI API 시연</span><span class="mode"></span></header>
      <div class="app"><aside class="side" id="side"></aside><main class="main"><div id="view" class="view"></div></main></div>`);
    side = document.getElementById('side'); view = document.getElementById('view'); rib = document.querySelector('.ribbon');
    const q = new URLSearchParams(location.search);
    const h = decodeURIComponent(location.hash.slice(1));
    if (h) S.route = h;
    history.replaceState(null, '', location.pathname + '#' + S.route);
    render(true);
    if (q.get('jump')) GP.jump(q.get('jump'));
    if (cleared) GP.toast('새로 압축을 푼 목업이라 이 브라우저에 남아 있던 이전 기록을 지웠어요');
    if (GP.AI.live()) GP.AI.ping();
  };
})();

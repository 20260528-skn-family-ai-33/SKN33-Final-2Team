/* GrowPath 5차 목업 (Claude) · AI 모드·연결 상태·오류 안내 (화면 쪽)
   5차에서 에이전트 지시문·호출·가데이터·실패 시연은 서버(FastAPI app/agents)로 옮겼다(2026-10-21 사용자 결정).
   이 파일은 4차 화면 코드가 쓰던 AI.* 이름을 그대로 두고, 값은 서버에서 받는다:
     모드·모델 이름(/ai/providers) · 사용자가 고른 모드·시연 도구 설정(/me) · 연결 확인(/ai/status) · 규정 조항(응답에 함께 오는 reg 묶음)
   고른 모드가 설정되지 않았으면 'off' — 가데이터나 다른 모드로 자동 대체하지 않는다(설계서 v1.7 그림 12). 다시 시도는 사용자가 누를 때만 */
(function () {
  'use strict';
  const GP = window.GP, D = GP.D, API = window.GPAPI;
  const AI = GP.AI = {};

  /* ── 모드·상태 (서버 값) ── */
  AI.status = { checked: false, providers: {}, docLibs: {} };
  AI.settings = { aiProvider: 'ollama', demoMock: false, failSim: {} };
  AI.PROV = { ollama: 'RunPod-Ollama', api: 'OpenAI API', openai: 'OpenAI API', mock: '가데이터' };
  /* 화면은 4차처럼 'api' 를 OpenAI 로 쓰고, 서버에는 'openai' 로 보낸다 */
  const toUi = p => (p === 'openai' ? 'api' : p);
  const toSrv = p => (p === 'api' ? 'openai' : p);
  AI.choice = () => toUi(AI.settings.aiProvider || 'ollama');
  AI.setChoice = async p => { AI.settings.aiProvider = toSrv(p); await API.setProvider(toSrv(p)); };
  AI.demoMock = () => !!AI.settings.demoMock;
  AI.setDemoMock = async on => { AI.settings.demoMock = !!on; Object.assign(AI.settings, await API.demoSettings({ demoMock: !!on })); };
  const prov = p => AI.status.providers[toSrv(p)] || {};
  AI.available = p => !!prov(p).available;
  AI.unavailableWhy = p => (!AI.status.checked ? '확인 중…' : prov(p).reason || '설정을 확인해 주세요');
  AI.mode = () => (AI.demoMock() ? 'mock' : AI.available(AI.choice()) ? AI.choice() : 'off');
  AI.live = () => AI.mode() === 'ollama' || AI.mode() === 'api';
  AI.off = () => AI.mode() === 'off';
  AI.modelName = role => { const m = (prov(AI.mode()).models || {}); return role === 'vision' ? m.vision || '' : role === 'roadmap' ? m.roadmap || m.default || '' : m.default || ''; };
  AI.visionModel = () => (AI.live() ? (prov(AI.mode()).models || {}).vision || '' : '');
  AI.DOC_CHARS = 6000;
  AI.checkStatus = async function () {
    try {
      const j = await API.providers();
      AI.status = { checked: true, server: true, docLibs: j.docLibs || {}, providers: Object.fromEntries(j.providers.map(p => [p.id, p])) };
      const ol = AI.status.providers.ollama || {};
      AI.status.ollama = { configured: !!ol.available, target: ol.target || '', model: (ol.models || {}).default || '', roadmapModel: (ol.models || {}).roadmap || '', embedModel: (ol.models || {}).embed || '' };
      AI.status.model = ((AI.status.providers.openai || {}).models || {}).default || '';
    } catch (e) { AI.status.checked = true; AI.status.server = false; }
  };
  AI.applySettings = s => { if (s) Object.assign(AI.settings, { aiProvider: s.aiProvider || AI.settings.aiProvider, demoMock: !!s.demoMock, failSim: s.failSim || {} }); };

  /* ── 에이전트 동작 기록 (서버 메모리 · 로그인한 본인만) ── */
  AI.log = [];
  AI.loadLog = async () => { try { AI.log = (await API.aiLog()).log || []; } catch (e) { AI.log = []; } return AI.log; };

  /* ── 연결 상태 (좌측 'AI 모델'·진단 에이전트 창 상단) ── */
  AI.conn = { state: 'idle', provider: '', at: 0 };
  function setConn(state, extra) { AI.conn = Object.assign({ state, provider: AI.mode(), at: Date.now(), ms: 0, loadMs: 0, error: '', raw: '', kind: '', models: AI.conn.models || null }, extra); if (GP.onConn) GP.onConn(); }
  AI.setConn = setConn;
  AI.resetConn = () => { AI.conn = { state: 'idle', provider: '', at: 0 }; };
  AI.ping = async function () {
    const p = AI.mode();
    if (!AI.live() || (AI.conn.state === 'checking' && AI.conn.provider === p)) return;
    setConn('checking', { provider: p, models: AI.conn.provider === p ? AI.conn.models : null });
    const t0 = performance.now();
    try {
      const j = await API.aiStatus(toSrv(p));
      if (AI.mode() !== p) return;
      setConn('ok', { provider: p, ms: Math.round(performance.now() - t0), via: 'ping', models: j.models || null, version: j.version || '' });
    } catch (err) {
      if (AI.mode() !== p) return;
      const c = AI.cause(err); setConn('error', { provider: p, error: c.text, raw: c.raw, kind: c.kind, hint: c.hint, via: 'ping' });
    }
  };
  /* 실제 호출 결과로 연결 상태를 고친다: 연결 문제(서버·설정·Pod·모델·키)만 '연결 안 됨'으로 */
  const CONN_KINDS = ['server', 'config', 'conn', 'model', 'auth'];
  AI.noteResult = (cause, meta) => {
    if (!AI.live()) return;
    if (!cause) { if (AI.conn.state !== 'ok') setConn('ok', { provider: AI.mode(), via: 'call', ms: (meta || {}).ms || 0, loadMs: (meta || {}).loadMs || 0, models: AI.conn.models }); return; }
    if (CONN_KINDS.includes(cause.kind)) setConn('error', { provider: AI.mode(), error: cause.text, raw: cause.raw, kind: cause.kind, hint: cause.hint, via: 'call' });
  };
  AI.connFor = function (role) {
    const c = AI.conn;
    if (c.provider !== AI.mode()) return { state: 'idle' };
    if (c.state !== 'ok' || !c.models) return c;
    let pick = c.models.filter(m => (role === 'all' ? true : m.role === (role || 'default')));
    if (!pick.length) pick = c.models.filter(m => m.role === 'default');
    const miss = pick.find(m => !m.installed);
    if (miss) return Object.assign({}, c, { state: 'error', kind: 'model', error: `‘${miss.name}’ 모델이 Ollama에 없어요`, raw: `설치된 모델 목록(api/tags)에 ${miss.name}이 없음`, hint: 'Pod에서 모델을 받은 뒤(ollama pull) 다시 시도하거나, .env의 모델 이름을 확인해 주세요' });
    const wait = pick.filter(m => m.role !== 'embed' && !m.loaded).map(m => m.name);
    if (wait.length) return Object.assign({}, c, { state: 'cold', waiting: wait });
    return c;
  };

  /* ── 오류 안내: 사용자에게는 쉬운 말과 할 일, 원인·조치·원문은 운영자용(P.opsBox · 10/14) ──
     서버가 원인을 골라 보낸다({kind, cause(원인), hint(조치), raw(원문), message(사용자용)}) */
  const USER_TEXT = {
    off: '고른 AI 모델을 지금 쓸 수 없어요', lost: '진행 중이던 작업을 찾지 못했어요', server: 'AI 서버에 연결하지 못했어요', config: 'AI 모델 설정이 아직 준비되지 않았어요',
    conn: 'AI 모델이 지금 응답하지 않아요', model: 'AI 모델을 아직 쓸 수 없어요', auth: 'AI 모델을 쓸 권한을 확인하지 못했어요', timeout: 'AI 모델의 응답이 너무 오래 걸려 멈췄어요',
    memory: 'AI 모델이 지금 요청을 처리하지 못했어요', limit: '요청이 몰려 AI 모델을 잠시 쓸 수 없어요', format: 'AI가 만든 결과를 화면에 쓸 수 없었어요', other: '처리하는 중에 문제가 생겼어요',
    docfmt: '이 형식의 파일은 읽을 수 없어요', doclib: '이 형식을 읽는 도구가 아직 준비되지 않았어요', docread: '기획서 파일을 읽지 못했어요', docbig: '파일이 너무 커요(15MB까지)',
    visioncfg: '이미지를 볼 수 있는 AI 모델이 준비되지 않았어요'
  };
  AI.userText = kind => USER_TEXT[kind] || USER_TEXT.other;
  AI.userTodo = function (kind) {
    if (kind === 'docbig') return ['15MB 이하로 줄여 다시 골라 주세요.', '기획서 없이 목표만으로 진행해도 돼요.'];
    if (/^doc/.test(kind || '')) return ['DOCX·PPTX·HWPX·PDF·TXT 중 하나로 저장해 다시 골라 주세요.', '기획서 없이 목표만으로 진행해도 돼요.'];
    const other = AI.choice() === 'api' ? 'ollama' : 'api';
    if (kind === 'off') return ['서버 연결과 모델 설정을 확인해 주세요.', '자동 대체하지 않아요. 연결한 뒤 다시 시도해 주세요.'].concat(AI.available(other) ? [`좌측 ‘AI 모델’에서 ${AI.PROV[other]}를 골라 볼 수도 있어요.`] : []);
    if (kind === 'lost') return ['다시 시도하면 새로 만들어요.'];
    const t = [kind === 'format' ? '다시 시도하면 대부분 해결돼요.' : '잠시 뒤 다시 시도해 주세요.'];
    if (kind !== 'server' && !AI.demoMock() && AI.available(other)) t.push(`좌측 ‘AI 모델’에서 ${AI.PROV[other]}를 골라 볼 수도 있어요.`);
    t.push('계속되면 담당자에게 알려 주세요.');
    return t;
  };
  /* 서버 오류(ApiErr) 또는 서버가 저장해 둔 원인 객체 → 화면 원인 {kind, text, hint, raw, user} */
  AI.cause = function (err) {
    if (err && err.kind && (err.text !== undefined || err.user !== undefined)) return err;
    const p = (err && err.payload) || null;
    if (p) {
      const kind = p.kind || ({ AUTH_REQUIRED: 'server' }[p.code]) || 'other';
      return { kind, text: p.cause || p.message || '', hint: p.hint || '', raw: p.raw || '', user: p.message || AI.userText(kind), code: p.code, retryable: !!p.retryable };
    }
    const m = String((err && err.message) || err || '');
    return { kind: 'server', text: m, hint: '서버(목업_실행.cmd)가 켜져 있는지 확인해 주세요', raw: m, user: AI.userText('server') };
  };

  /* ── 생성 실패 시연 (시연 도구 · 서버가 첫 시도만 실패시킨다) ── */
  const SIM_KINDS = ['goal', 'doc', 'quiz', 'diag', 'gen', 'sup', 'report', 'reg', 'rev'];
  AI.failSim = () => Object.assign(Object.fromEntries(SIM_KINDS.map(k => [k, false])), AI.settings.failSim || {});
  AI.setFailSim = async (k, on) => { AI.settings.failSim = Object.assign({}, AI.settings.failSim, { [k]: !!on }); AI.applySettings(await API.demoSettings({ failSim: { [k]: !!on } })); };

  /* ── 세부 사항 문구 (4차 그대로 · 자격증은 서버 자격 목록 D.certById) ── */
  AI.emptyPrefs = () => ({ format: '', cert: '', hours: '', weeks: '', budget: '', etc: '' });
  const blank = v => v === '' || v == null;
  AI.certOf = p => (p && D.certById[p.cert]) || null;
  AI.certNameOf = p => { const c = AI.certOf(p); return c ? c.name : ''; };
  AI.certRes = p => { const c = AI.certOf(p); return c ? c.res : null; };
  AI.prefAuto = (k, p) => (k === 'budget' ? blank(p.budget) : k === 'etc' ? !String(p.etc || '').trim() : k === 'hours' || k === 'weeks' ? !(+p[k] > 0) : k === 'cert' ? !AI.certOf(p) : !p[k]);
  AI.prefText = (k, p) => {
    const v = p[k];
    if (k === 'format') return (D.formatOpts.find(o => o[0] === v) || [])[1] || '알아서';
    if (k === 'cert') { const c = AI.certOf(p); return c ? `${c.name} · 4단계에 준비 활동을 넣어요` : '계획 없음'; }
    if (k === 'hours') return +v > 0 ? `주 ${v}시간` : '알아서 (로드맵 계획 에이전트가 정해요)';
    if (k === 'weeks') return +v > 0 ? `${v}주 안에` : '알아서 (정해진 기간 없음)';
    if (k === 'budget') return blank(v) ? '알아서' : +v > 0 ? GP.won(+v) : '0원 (무료 자료만)';
    if (k === 'etc') return String(v || '').trim() || '없음';
    return '';
  };
  AI.prefSummary = p => Object.fromEntries(D.detailFields.map(([k, l]) => [l, AI.prefText(k, p)]));
  AI.skillLabel = s => D.skills[s] || s;
  const ANS = o => { const x = D.answerOpts.find(y => y[0] === String(o)); return x ? `${x[0]} ${x[1]}` : '미응답'; };
  AI.ansLabel = ANS;
  AI.rose = (pre, post) => +post > +pre;

  /* ── 규정 (서버 묶음 · 조항은 응답에 함께 오는 reg {articles, regs} 를 모아 둔다) ── */
  AI.REG_SETS = {};
  const ART = new Map(), REGS = new Map();
  AI.mergeReg = b => { if (!b) return; Object.values(b.articles || {}).forEach(a => ART.set(a.id, a)); Object.entries(b.regs || {}).forEach(([k, r]) => REGS.set(k, r)); };
  AI.loadRegSets = async () => {
    try {
      AI.REG_SETS = await API.regSets();
      Object.values(AI.REG_SETS).forEach(s => s.regs.forEach(r => { if (!REGS.has(r.key)) REGS.set(r.key, r); }));
    } catch (e) { AI.REG_SETS = {}; }
  };
  AI.article = id => ART.get(id);
  AI.regOf = key => REGS.get(key) || null;
  AI.regSet = () => AI.REG_SETS[(GP.me() || {}).empGroup] || null;
  AI.regApplies = () => !!AI.regSet();
  AI.artName = a => { const n = (AI.regOf(a.reg) || {}).name || ''; return a.title ? `「${n}」 ${a.no}(${a.title})` : `「${n}」 ${a.no}`; };
  AI.missLabel = m => (/[「」]/.test(m) || !/(규정|규칙|세칙|운영기준)$/.test(m) ? String(m) : `「${m}」`);
  AI.regGroups = () => Object.keys(AI.REG_SETS);

  /* ── 목표 후보 (서버가 미리 만들어 둔 것) ── */
  AI.profileOf = () => GP.me();
  AI.profileEnough = e => !!(e && ((e.profile && (e.profile.workDesc || e.profile.expSummary)) || (e.tech || []).length));
})();

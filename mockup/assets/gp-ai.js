/* GrowPath 4차 목업 (Claude) · 에이전트 계층
   진단 에이전트(사전 점검 문항 생성·수준 진단·보고서), 로드맵 계획 에이전트(관점별 A1·A2·A3), 규정 에이전트(규정 RAG)
   모드: 사용자가 좌측 'AI 모델'에서 고른 'ollama' RunPod-Ollama(로컬 LLM·sLLM) 또는 'api' OpenAI API 를 server.py 를 거쳐 호출.
   고른 모드가 설정되지 않았거나 시연 도구에서 '가데이터로 보기'를 켜면 'mock' 시연용 가데이터.
   호출 오류는 가데이터로 대신하지 않고 실패를 알린다. 다시 시도는 사용자가 눌렀을 때만 한다(10/14 · 자동 재시도 없음) */
(function () {
  'use strict';
  const GP = window.GP, D = GP.D, REG = window.GPREG;
  const AI = GP.AI = {};
  const PROV_KEY = 'gp4c.provider', DEMO_KEY = 'gp4c.demomock';
  const S = () => GP.S;
  const clone = o => JSON.parse(JSON.stringify(o));
  const uniq = a => [...new Set(a)];

  /* ── 모드·상태 ── */
  const NO_OLLAMA = { configured: false, target: '', model: '', roadmapModel: '', embedModel: '', timeout: 0 };
  AI.status = { server: false, key: false, model: '', embed: '', checked: false, ollama: NO_OLLAMA, vision: {}, docLibs: {} };
  AI.log = [];
  AI.PROV = { ollama: 'RunPod-Ollama', api: 'OpenAI API', mock: '가데이터' };
  AI.choice = () => (GP.store.get(PROV_KEY) === 'api' ? 'api' : 'ollama');
  AI.setChoice = p => GP.store.set(PROV_KEY, p === 'api' ? 'api' : 'ollama');
  AI.demoMock = () => GP.store.get(DEMO_KEY) === '1';
  AI.setDemoMock = on => GP.store.set(DEMO_KEY, on ? '1' : '0');
  AI.available = p => (p === 'ollama' ? !!AI.status.ollama.configured : p === 'api' ? !!AI.status.key : true);
  AI.unavailableWhy = p => (!AI.status.checked ? '확인 중…' : !AI.status.server ? 'server.py로 열어야 쓸 수 있어요' : p === 'ollama' ? '.env에 OLLAMA_BASE_URL이 없어요' : '.env에 OPENAI_API_KEY가 없어요');
  AI.mode = () => (AI.demoMock() ? 'mock' : AI.available(AI.choice()) ? AI.choice() : 'mock');
  AI.live = () => AI.mode() !== 'mock';
  /* 모델 배정이 확정되지 않아 .env 에서 기본 모델과 로드맵 하위 에이전트 모델을 따로 줄 수 있다 */
  AI.modelName = role => (role === 'vision' ? AI.visionModel() : AI.mode() === 'ollama' ? (role === 'roadmap' ? AI.status.ollama.roadmapModel : AI.status.ollama.model) : AI.mode() === 'api' ? AI.status.model : '');
  AI.checkStatus = async function () {
    if (!/^https?:$/.test(location.protocol)) { AI.status.checked = true; return; }
    try {
      const r = await fetch('/api/status', { cache: 'no-store' });
      const j = await r.json();
      AI.status = { server: true, installId: j.installId || '', key: !!j.key, model: j.model || '', embed: j.embedModel || '', checked: true, ollama: Object.assign({}, NO_OLLAMA, j.ollama || {}), vision: j.vision || {}, docLibs: j.docLibs || {} };
    } catch (e) { AI.status.checked = true; }
  };

  /* signal: 사용자가 '멈추기'를 누르면 기다리던 호출을 끊는다(사내 생활 도우미 · 10/14) */
  async function post(path, body, signal) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
    let j = {};
    try { j = await r.json(); } catch (e) { /* 본문 없음 */ }
    if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  }
  function parseJSON(t) {
    try { return JSON.parse(t); } catch (e) {
      const m = String(t).match(/\{[\s\S]*\}/);
      if (m) return JSON.parse(m[0]);
      throw new Error('모델 응답이 JSON 형식이 아니에요');
    }
  }
  /* role: 'default' 진단·규정·보고서 / 'roadmap' 로드맵 하위 에이전트 (RunPod-Ollama 에서 모델을 나눠 쓸 때) */
  /* images: [{mime, b64}] 를 주면 사용자 메시지에 붙인다(비전 모델 · role 'vision') */
  /* o.history: 앞 대화 메시지([{role, content}])를 system 과 이번 질문 사이에 넣는다 · o.signal: 멈추기 */
  AI.llm = async (system, input, role, images, o) => {
    o = o || {};
    const user = { role: 'user', content: JSON.stringify(input) };
    if (images && images.length) user.images = images;
    const messages = [{ role: 'system', content: system }].concat(o.history || [], [user]);
    const j = await post('/api/chat', { provider: AI.mode() === 'ollama' ? 'ollama' : 'openai', role: role || 'default', json: true, messages }, o.signal);
    AI.lastMeta = { model: j.model || '', loadMs: j.loadMs || 0 };
    return parseJSON(j.content);
  };
  const clip = (v, n) => { const s = typeof v === 'string' ? v : JSON.stringify(v, null, 1); return s.length > (n || 1600) ? s.slice(0, n || 1600) + ' …' : s; };

  /* 연결 상태 (좌측 'AI 모델'과 진단 에이전트 창 상단에 표시)
     처음 열 때·모드를 바꿀 때·세부 사항 확인 화면에 들어올 때 /api/ping 으로 확인하고, 실제 호출 결과로 갱신한다.
     RunPod-Ollama 는 서버 응답 → 설치된 모델 → GPU에 올라간 모델까지 본다(models) */
  AI.conn = { state: 'idle', provider: '', at: 0 };
  function setConn(state, extra) { AI.conn = Object.assign({ state, provider: AI.mode(), at: Date.now(), ms: 0, loadMs: 0, error: '', raw: '', kind: '', models: AI.conn.models || null }, extra); if (GP.onConn) GP.onConn(); }
  AI.resetConn = () => { AI.conn = { state: 'idle', provider: '', at: 0 }; };
  AI.ping = async function () {
    const prov = AI.mode();
    if (prov === 'mock' || (AI.conn.state === 'checking' && AI.conn.provider === prov)) return;
    setConn('checking', { provider: prov, models: AI.conn.provider === prov ? AI.conn.models : null });
    const t0 = performance.now();
    try {
      const r = await fetch('/api/ping?provider=' + (prov === 'ollama' ? 'ollama' : 'openai'), { cache: 'no-store' });
      let j = {};
      try { j = await r.json(); } catch (e) { /* 본문 없음 */ }
      if (r.status === 404 && !/OpenAI|Ollama|RunPod/.test(j.error || '')) throw new Error('server.py가 연결 확인 기능이 없는 이전 버전이에요');
      if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
      if (AI.mode() !== prov) return;
      setConn('ok', { provider: prov, ms: Math.round(performance.now() - t0), via: 'ping', models: j.models || null, version: j.version || '' });
    } catch (err) {
      if (AI.mode() !== prov) return;
      const c = AI.cause(err); setConn('error', { provider: prov, error: c.text, raw: c.raw, kind: c.kind, hint: c.hint, via: 'ping' });
    }
  };
  /* 역할별 연결 상태: 'default' 진단 에이전트 모델, 'roadmap' 로드맵 모델, 'all' 전체.
     Ollama 는 모델이 없으면 error, 설치됐지만 GPU에 올라가 있지 않으면 cold(첫 호출이 느림) */
  AI.connFor = function (role) {
    const c = AI.conn;
    if (c.provider !== AI.mode()) return { state: 'idle' };
    if (c.state !== 'ok' || !c.models) return c;
    let pick = c.models.filter(m => (role === 'all' ? true : m.role === (role || 'default')));
    if (!pick.length) pick = c.models.filter(m => m.role === 'default');
    const miss = pick.find(m => !m.installed);
    if (miss) return Object.assign({}, c, { state: 'error', kind: 'model', error: `‘${miss.name}’ 모델이 Ollama에 없어요`, raw: `설치된 모델 목록(api/tags)에 ${miss.name}이 없음`, hint: CAUSE_HINT.model.ollama });
    const wait = pick.filter(m => m.role !== 'embed' && !m.loaded).map(m => m.name);
    if (wait.length) return Object.assign({}, c, { state: 'cold', waiting: wait });
    return c;
  };

  /* 오류 메시지를 사용자가 읽을 원인(text)·종류(kind)·할 일(hint)로 바꾼다.
     server.py 의 오류 문구 앞머리(Ollama 연결 실패 / Ollama 시간 초과 / RunPod 프록시 / Ollama 404 / OpenAI 401 …)를 본다 */
  const CAUSES = [
    [/기획서 형식/, 'docfmt', '읽을 수 없는 파일 형식이에요'],
    [/pypdf 없음|olefile 없음/, 'doclib', '이 PC에 그 형식을 읽는 도구(pypdf·olefile)가 설치되지 않았어요'],
    [/기획서 읽기 실패/, 'docread', '기획서 파일을 읽지 못했어요'],
    [/요청이 너무 커요/, 'docbig', '파일이 너무 커요 (15MB까지)'],
    [/비전 모델 설정이 없/, 'visioncfg', '.env에 비전 모델(OLLAMA_VISION_MODEL / OPENAI_VISION_MODEL) 설정이 없어요'],
    [/이전 버전/, 'server', 'server.py를 다시 실행해 주세요. 연결 확인 기능이 없는 이전 버전이에요'],
    [/Failed to fetch|NetworkError|Load failed/i, 'server', 'AI 서버(server.py)에 연결하지 못했어요'],
    [/Ollama 설정이 없|OLLAMA_BASE_URL/, 'config', '.env에 Ollama 주소(OLLAMA_BASE_URL)가 없어요'],
    [/임베딩 모델 설정이 없/, 'config', '.env에 Ollama 임베딩 모델(OLLAMA_EMBED_MODEL)이 없어요'],
    [/RunPod 프록시 524/, 'timeout', 'RunPod 프록시의 응답 시간 제한(약 100초)을 넘었어요'],
    [/RunPod 프록시/, 'conn', 'RunPod Pod가 꺼져 있거나 아직 시작 중이에요 (Ollama가 응답하지 않음)'],
    [/Ollama 연결 실패/, 'conn', 'Ollama 서버에 연결하지 못했어요. RunPod Pod가 꺼져 있거나 주소가 맞지 않아요'],
    [/Ollama 시간 초과/, 'timeout', '응답 시간이 초과됐어요 (Ollama)'],
    [/out of memory|more system memory|CUDA error/i, 'memory', 'GPU 메모리가 부족해 모델을 실행하지 못했어요'],
    [/Ollama 404|not found, try pulling/i, 'model', 'Ollama에 지정한 모델이 없어요'],
    [/Ollama 5\d\d/, 'other', 'Ollama 서버에서 오류가 났어요'],
    [/Ollama 4\d\d/, 'other', 'Ollama가 요청을 처리하지 못했어요'],
    [/OpenAI 40[13]/, 'auth', 'API 키가 올바르지 않거나 권한이 없어요'],
    [/OpenAI 404/, 'model', '.env에 설정한 모델을 찾을 수 없어요'],
    [/OpenAI 429/, 'limit', '요청이 많거나 사용 한도를 넘어 잠시 제한됐어요'],
    [/OpenAI 5\d\d/, 'other', 'OpenAI 서버에 일시적인 문제가 있어요'],
    [/OpenAI 시간 초과/, 'timeout', 'OpenAI 응답 시간이 초과됐어요'],
    [/OpenAI 연결 실패/, 'conn', 'OpenAI 서버에 연결하지 못했어요'],
    [/timed? ?out|시간 초과/i, 'timeout', '응답 시간이 초과됐어요'],
    [/JSON|형식/, 'format', '모델 응답 형식(JSON)이 맞지 않았어요'],
    [/너무 적|비어 있/, 'format', '에이전트가 쓸 수 있는 결과를 충분히 만들지 못했어요']
  ];
  const CONN_KINDS = ['server', 'config', 'conn', 'model', 'auth'];
  const CAUSE_HINT = {
    server: { any: 'server.py가 켜져 있는지 확인해 주세요' },
    config: { any: '.env를 고친 뒤 server.py를 다시 실행해 주세요' },
    conn: { ollama: 'RunPod에서 Pod를 켠 뒤 다시 시도하거나, 좌측 ‘AI 모델’에서 다른 모드를 골라 주세요', any: '네트워크 상태를 확인한 뒤 다시 시도해 주세요' },
    timeout: { ollama: '모델을 GPU에 올리는 중이거나 여러 요청이 몰려 차례를 기다렸을 수 있어요. 잠시 뒤 다시 시도해 주세요', any: '잠시 뒤 다시 시도해 주세요' },
    model: { ollama: 'Pod에서 모델을 받은 뒤(ollama pull) 다시 시도하거나, .env의 모델 이름을 확인해 주세요', any: '.env의 OPENAI_MODEL을 확인해 주세요' },
    memory: { any: '더 큰 GPU의 Pod나 더 작게 양자화한 모델이 필요해요. 동시에 처리하는 요청이 줄면 될 수도 있어요' },
    auth: { any: '.env의 OPENAI_API_KEY를 확인해 주세요' },
    limit: { any: '잠시 뒤 다시 시도해 주세요' },
    format: { any: '다시 시도하면 대부분 해결돼요' },
    docfmt: { any: 'DOCX·PPTX·HWPX·PDF·TXT·MD 중 하나로 저장해 다시 고르면 돼요' },
    doclib: { any: 'PDF는 pip install pypdf, HWP는 pip install olefile 뒤 server.py를 다시 실행해 주세요' },
    docread: { any: '파일이 손상됐거나 암호가 걸렸는지, server.py(목업_실행.cmd)로 열었는지 확인해 주세요' },
    docbig: { any: '15MB 이하로 줄이거나 필요한 부분만 따로 저장해 주세요' },
    visioncfg: { any: '.env에 비전 모델을 넣고 server.py를 다시 실행해 주세요' },
    other: { any: '잠시 뒤 다시 시도해 주세요' }
  };
  /* 사용자에게 보이는 안내는 쉬운 말(user)과 할 일(userTodo)만 쓰고,
     원인(text)·조치(hint)·원문 오류(raw)는 운영자용으로 접어 둔다(P.opsBox · 10/14) */
  const USER_TEXT = {
    server: 'AI 서버에 연결하지 못했어요', config: 'AI 모델 설정이 아직 준비되지 않았어요', conn: 'AI 모델이 지금 응답하지 않아요',
    model: 'AI 모델을 아직 쓸 수 없어요', auth: 'AI 모델을 쓸 권한을 확인하지 못했어요', timeout: 'AI 모델의 응답이 너무 오래 걸려 멈췄어요',
    memory: 'AI 모델이 지금 요청을 처리하지 못했어요', limit: '요청이 몰려 AI 모델을 잠시 쓸 수 없어요', format: 'AI가 만든 결과를 화면에 쓸 수 없었어요', other: 'AI 모델에서 문제가 생겼어요',
    docfmt: '이 형식의 파일은 읽을 수 없어요', doclib: '이 형식을 읽는 도구가 아직 준비되지 않았어요', docread: '기획서 파일을 읽지 못했어요',
    docbig: '파일이 너무 커요(15MB까지)', visioncfg: '이미지를 볼 수 있는 AI 모델이 준비되지 않았어요'
  };
  AI.userText = kind => USER_TEXT[kind] || USER_TEXT.other;
  /* 사용자가 할 수 있는 일: 다시 시도 → (쓸 수 있으면) 다른 AI 모델 고르기 → 담당자에게 알리기. 화면을 그릴 때 지금 상태로 만든다 */
  AI.userTodo = function (kind) {
    /* 기획서 파일 문제: 다른 형식으로 저장하거나 기획서 없이 진행 */
    if (kind === 'docbig') return ['15MB 이하로 줄여 다시 골라 주세요.', '기획서 없이 목표만으로 진행해도 돼요.'];
    if (/^doc/.test(kind)) return ['DOCX·PPTX·HWPX·PDF·TXT 중 하나로 저장해 다시 골라 주세요.', '기획서 없이 목표만으로 진행해도 돼요.'];
    const other = AI.choice() === 'api' ? 'ollama' : 'api', t = [kind === 'format' ? '다시 시도하면 대부분 해결돼요.' : '잠시 뒤 다시 시도해 주세요.'];
    if (kind !== 'server' && !AI.demoMock() && AI.available(other)) t.push(`좌측 ‘AI 모델’에서 ${AI.PROV[other]}를 골라 볼 수도 있어요.`);
    t.push('계속되면 담당자에게 알려 주세요.');
    return t;
  };
  AI.cause = function (err) {
    const m = String((err && err.message) || err || '');
    const hit = CAUSES.find(([re]) => re.test(m)) || [null, 'other', '알 수 없는 오류가 났어요'];
    const ollama = /Ollama|RunPod/.test(m) || (AI.mode() === 'ollama' && !/OpenAI/.test(m));
    const h = CAUSE_HINT[hit[1]] || CAUSE_HINT.other, missing = m.match(/model "([^"]+)" not found/);
    return { text: missing ? `‘${missing[1]}’ 모델이 Ollama에 없어요` : hit[2], raw: m, kind: hit[1], hint: (ollama && h.ollama) || h.any, user: AI.userText(hit[1]) };
  };

  /* 생성 실패 시연 (시연 도구): 켜 두면 같은 대상(문항 생성 내용·진단할 응답·질문 등)의 첫 시도만 실패하고, 다시 시도하면 성공한다.
     실패 문구는 좌측 'AI 모델'에서 고른 모드의 실제 오류 문구를 흉내 낸다 */
  const SIM_KEY = 'gp4c.failsim', SIM_KINDS = ['goal', 'doc', 'quiz', 'diag', 'gen', 'sup', 'report', 'reg', 'rev'];
  AI.failSim = () => { const off = Object.fromEntries(SIM_KINDS.map(k => [k, false])); try { return Object.assign(off, JSON.parse(GP.store.get(SIM_KEY) || '{}')); } catch (e) { return off; } };
  /* 시도 횟수는 이 탭 동안 유지한다(새로 고친 뒤 '다시 시도'가 또 첫 시도로 세어져 실패하지 않게). 켜고 끌 때 처음부터 센다 */
  const TRY_KEY = 'gp4c.simtries';
  const readTries = () => { try { return JSON.parse(sessionStorage.getItem(TRY_KEY) || '{}'); } catch (e) { return {}; } };
  const writeTries = t => { try { sessionStorage.setItem(TRY_KEY, JSON.stringify(t)); } catch (e) { /* 저장 불가 환경은 메모리만 */ } };
  AI.setFailSim = (k, on) => { GP.store.set(SIM_KEY, JSON.stringify(Object.assign(AI.failSim(), { [k]: !!on }))); simTries = {}; writeTries(simTries); };
  AI.simError = k => (AI.choice() === 'api'
    ? { goal: 'OpenAI 시간 초과: 90초 안에 응답 없음 (시연용 실패)', quiz: 'OpenAI 연결 실패: 응답 없음 (시연용 실패)', diag: 'OpenAI 429: Rate limit reached (시연용 실패)', A2: 'OpenAI 시간 초과: 90초 안에 응답 없음 (시연용 실패)', A3: '모델 응답이 JSON 형식이 아니에요 (시연용 실패)', report: 'OpenAI 시간 초과: 90초 안에 응답 없음 (시연용 실패)', reg: 'OpenAI 연결 실패: 응답 없음 (시연용 실패)', rev: 'OpenAI 시간 초과: 90초 안에 응답 없음 (시연용 실패)', doc: 'OpenAI 429: Rate limit reached (시연용 실패)', sup: 'OpenAI 연결 실패: 응답 없음 (시연용 실패)' }
    : { goal: 'RunPod 프록시 HTTP 502: Ollama 응답이 아니에요 (시연용 실패)', quiz: 'RunPod 프록시 HTTP 502: Ollama 응답이 아니에요 (시연용 실패)', diag: 'Ollama 시간 초과: 180초 안에 응답 없음 (시연용 실패)', A2: 'Ollama 시간 초과: 180초 안에 응답 없음 (시연용 실패)', A3: 'Ollama 500: CUDA error: out of memory (시연용 실패)', report: 'Ollama 500: CUDA error: out of memory (시연용 실패)', reg: 'RunPod 프록시 HTTP 502: Ollama 응답이 아니에요 (시연용 실패)', rev: 'Ollama 시간 초과: 180초 안에 응답 없음 (시연용 실패)', doc: 'Ollama 시간 초과: 180초 안에 응답 없음 (시연용 실패)', sup: 'Ollama 500: CUDA error: out of memory (시연용 실패)' })[k];
  let simTries = readTries();
  AI.simOnce = (k, subject) => {
    if (!AI.failSim()[k]) return null;
    const id = k + '|' + subject; simTries[id] = (simTries[id] || 0) + 1; writeTries(simTries);
    return simTries[id] === 1 ? AI.simError(k) : null;
  };

  /* 한 번의 에이전트 호출: 모드에 따라 실행하고 기록을 남긴다.
     오류는 가데이터로 대신하지 않고 그대로 던진다. 화면이 실패 안내와 '다시 시도'(사용자가 누를 때만)를 보여 준다.
     opt.simFail 이 있으면 그 메시지로 실패를 시연한다. opt.signal 은 apiFn 에 넘겨 '멈추기'로 끊을 수 있게 한다 */
  AI.run = async function (agent, task, input, mockFn, apiFn, opt) {
    opt = opt || {};
    const mode = AI.mode(), live = mode !== 'mock', role = opt.role || 'default';
    const e = { at: new Date().toLocaleTimeString('ko-KR', { hour12: false }), agent, task, mode, model: AI.modelName(role), input: clip(input) };
    const t0 = performance.now();
    const keep = () => { e.ms = Math.round(performance.now() - t0); AI.log.unshift(e); if (AI.log.length > 80) AI.log.pop(); };
    let out;
    try {
      if (opt.simFail) { e.mode = 'sim'; throw new Error(opt.simFail); }
      out = live ? await apiFn(input, opt.signal) : mockFn(input);
      if (live && AI.mode() === mode && role !== 'vision') {
        /* 성공한 역할의 모델은 GPU에 올라간 것으로 본다 */
        const models = AI.conn.provider === mode && AI.conn.models ? AI.conn.models.map(m => (m.role === role || (role === 'roadmap' && !AI.conn.models.some(x => x.role === 'roadmap') && m.role === 'default') ? Object.assign({}, m, { loaded: true }) : m)) : null;
        setConn('ok', { provider: mode, ms: Math.round(performance.now() - t0), loadMs: (AI.lastMeta || {}).loadMs || 0, via: 'call', models });
      }
    } catch (err) {
      /* 사용자가 멈춘 호출은 오류가 아니다: 연결 상태를 바꾸지 않고 '멈춤'으로만 남긴다 */
      if (err && err.name === 'AbortError') { e.mode = 'stop'; e.error = '사용자가 답변을 멈췄어요'; e.output = '(멈춤)'; keep(); throw err; }
      e.error = err.message;
      /* 연결 상태는 연결 문제(Pod 꺼짐·모델 없음·키·설정)일 때만 '연결 안 됨'으로 바꾼다. 메모리 부족·시간 초과·형식 오류는 실패 화면에서만 안내 */
      if (live && e.mode !== 'sim' && AI.mode() === mode && role !== 'vision') {
        const c = AI.cause(err);
        if (CONN_KINDS.includes(c.kind)) setConn('error', { provider: mode, error: c.text, raw: c.raw, kind: c.kind, hint: c.hint, via: 'call' });
        else if (AI.conn.state === 'error') AI.ping(); /* 연결 문제가 아닌데 '연결 안 됨'이 남아 있으면 다시 확인 */
      }
      if (e.mode !== 'sim') e.mode = 'error';
      e.output = '(결과 없음)'; keep(); throw err;
    }
    e.output = clip(out); keep();
    return out;
  };

  /* ── 공통 도움 ── */
  AI.domainOf = goal => Object.keys(D.domains).find(k => D.domains[k].test.test(goal || '')) || 'rag';
  AI.skillLabel = s => D.skills[s] || s;
  /* 에이전트에게 넘기는 등록 자료 목록. 자격 자료는 사용자가 고른 자격(certRes)만 넣는다(26종 전부 넣으면 sLLM 입력이 길어짐) */
  AI.catalog = certRes => Object.entries(D.res).filter(([id, r]) => r.kind !== '자격' || id === certRes).map(([id, r]) => ({ id, title: r.title, kind: r.kind, format: r.format, hours: r.hours, cost: r.cost, stage: r.stage, real: r.real, skills: r.skills.map(AI.skillLabel) }));

  /* ── 세부 사항(학습 선호 5가지 + 기타 고려 사항) · 10/13: 대화 대신 입력 폼, 빈 칸은 '알아서' ──
     format: '' | video | doc | practice | mixed      cert: '' (계획 없음 · 기본값) | 자격 id (D.certGroups, 분야 → 자격 2단계로 고름)
     hours·weeks·budget: '' 또는 숫자 (budget 0 = 무료 자료만)      etc: 기타 고려 사항(로드맵 계획 에이전트에게 그대로 전달) */
  AI.emptyPrefs = () => ({ format: '', cert: '', hours: '', weeks: '', budget: '', etc: '' });
  const blank = v => v === '' || v == null;
  AI.certOf = p => (p && D.certById[p.cert]) || null;
  AI.certNameOf = p => { const c = AI.certOf(p); return c ? c.name : ''; };
  AI.certRes = p => { const c = AI.certOf(p); return c ? 'cert_' + c.id : null; };
  /* 기본값 표시(흐린 회색): 자격증은 '계획 없음', 나머지는 '알아서' */
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
  /* 에이전트에게 넘길 때는 사람이 읽는 문장으로 */
  AI.prefSummary = p => Object.fromEntries(D.detailFields.map(([k, l]) => [l, AI.prefText(k, p)]));

  /* 진단 에이전트 · 사전 점검 문항 생성 */
  function mockQuestions(inp) {
    const dom = AI.domainOf(inp.goal), take = (k, area) => D.qbank[k].map(q => Object.assign({}, q, { area }));
    const qs = take('ai', D.areas.ai).concat(take('dev', D.areas.dev), take(dom, D.domains[dom].label));
    const cn = AI.certNameOf(inp.prefs);
    if (cn) qs.push({ id: 'ct1', area: D.areas.cert, text: `${cn} 시험 범위를 알고 있다.`, skill: 'cert-scope' });
    return { questions: qs, domain: dom };
  }
  const Q_SYS = `너는 GrowPath의 '진단 에이전트'다. 사용자의 목표, 업무 프로젝트 기획서 요약(projectSummary, 있을 때), 세부 사항(학습 선호·기타 고려 사항)을 보고 현재 수준을 확인할 사전 점검 문항을 만든다.
- 10~14개, 영역 3~4개(예: AI 이해, 개발 경험, 목표 분야 실무. 자격증 계획이 있으면 자격증 영역 1개 추가).
- 사용자는 문항마다 5점 척도(1 전혀 아님, 2 아님, 3 보통이다, 4 그렇다, 5 매우 그렇다)로 답한다.
- 그래서 각 문항은 구체적인 라이브러리·도구·개념을 짚어 "~할 수 있다.", "~를 알고 있다."로 끝나는 서술문으로 쓴다. "~나요?" 같은 질문형으로 쓰지 않는다.
- skill에는 그 문항이 확인하는 역량을 짧은 한국어 명사구로 쓴다.
- projectSummary가 있으면 그 프로젝트를 하는 데 필요한 역량을 확인하는 문항을 목표 분야 영역에 넣는다.
- domain에는 목표가 속한 분야를 짧은 한국어 명사구로 쓴다(예: "RAG·문서 검색", "운영 데이터 분석"). 로드맵 계획 에이전트에게 함께 넘긴다.
JSON 형식: {"domain":"RAG·문서 검색","questions":[{"id":"q1","area":"개발 경험","text":"pandas로 표 데이터를 불러와 가공할 수 있다.","skill":"pandas 데이터 처리"}]}`;
  /* 목표 분야는 진단 에이전트가 정한다(10/14). 키워드로 나누는 AI.domainOf 는 가데이터 시나리오에만 쓴다 */
  async function apiQuestions(inp) {
    const r = await AI.llm(Q_SYS, { goal: inp.goal, projectFile: inp.project, projectSummary: inp.projectSummary || null, details: AI.prefSummary(inp.prefs) });
    const qs = (r.questions || []).filter(q => q && q.text).slice(0, 16).map((q, i) => ({ id: 'q' + (i + 1), area: String(q.area || '기타').slice(0, 20), text: String(q.text).slice(0, 140), skill: String(q.skill || q.text).slice(0, 40) }));
    if (qs.length < 5) throw new Error('문항이 너무 적어요');
    return { questions: qs, domain: String(r.domain || '').trim().slice(0, 30) || null };
  }
  /* ── 기획서 읽기 (10/14) ──
     파일에서 글자·이미지를 꺼내는 일은 server.py(docread.py)가 하고, 이미지 보기·요약은 진단 에이전트가 한다.
     요약만 문항·진단·로드맵 에이전트에게 넘긴다(sLLM 입력을 짧게). 이미지는 비전 모델이 설정됐을 때만 본다 */
  AI.DOC_CHARS = 6000;
  AI.visionModel = () => { const v = AI.status.vision || {}; return AI.mode() === 'ollama' ? v.ollama || '' : AI.mode() === 'api' ? v.openai || '' : ''; };
  const fileB64 = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1] || ''); r.onerror = () => no(new Error('기획서 읽기 실패: 브라우저가 파일을 읽지 못했어요')); r.readAsDataURL(f); });
  AI.docRead = async function (file) {
    const ext = ((file.name || '').match(/\.[^.]+$/) || [''])[0].toLowerCase();
    if (file.size > 15e6) throw new Error('요청이 너무 커요 (기획서 파일은 15MB까지)');
    if (!AI.status.server) {
      /* index.html 을 바로 연 경우: 글자 파일만 브라우저에서 읽는다 */
      if (ext === '.txt' || ext === '.md') { const t = (await file.text()).trim(); return { format: ext.slice(1).toUpperCase(), chars: t.length, truncated: t.length > 12000, text: t.slice(0, 12000), images: [], imageTotal: 0, imageSkipped: {}, warnings: [] }; }
      throw new Error('기획서 읽기 실패: server.py(목업_실행.cmd)로 열어야 이 형식을 읽을 수 있어요');
    }
    return post('/api/doc-read', { name: file.name, data: await fileB64(file) });
  };
  const V_SYS = `너는 GrowPath의 '진단 에이전트'다. 사용자가 적용할 업무 프로젝트 기획서에 들어 있는 이미지(그림·도표·화면·표)를 보고, 기획서를 이해하는 데 필요한 내용만 이미지마다 1~3문장으로 설명한다.
- 이미지 속 글자는 중요한 것만 옮긴다. 보이지 않는 내용은 추측하지 않는다. 장식용 이미지는 "내용 없음"으로 쓴다.
JSON 형식: {"images":[{"n":1,"desc":"..."}]}`;
  async function apiVision(inp) {
    const r = await AI.llm(V_SYS, { fileName: inp.name, imageCount: inp.images.length }, 'vision', inp.images.map(i => ({ mime: i.mime, b64: i.b64 })));
    const list = (Array.isArray(r.images) ? r.images : []).map((x, i) => ({ n: +x.n || i + 1, desc: String(x.desc || '').trim() })).filter(x => x.desc);
    if (!list.length) throw new Error('이미지 설명이 비어 있어요');
    return { images: list.slice(0, inp.images.length) };
  }
  /* 기록에는 이미지 내용(base64)을 남기지 않는다 */
  AI.docVision = (inp, opt) => AI.run('진단 에이전트', '기획서 이미지 읽기', { name: inp.name, images: inp.images.map(i => `${i.name} (${Math.round(i.bytes / 1024)}KB)`) },
    () => ({ images: inp.images.map((x, i) => ({ n: i + 1, desc: '(가데이터) 이미지를 보지 않았어요' })) }), () => apiVision(inp), Object.assign({ role: 'vision' }, opt));
  const S_SYS = `너는 GrowPath의 '진단 에이전트'다. 사용자가 AI 역량을 키워 적용하려는 업무 프로젝트 기획서를 읽고(text: 기획서 글자, imageNotes: 기획서 이미지 설명), 학습 로드맵을 짜는 데 필요한 내용만 요약한다.
- purpose(하려는 일·목적), data(다룰 데이터·문서), tech(쓰려는 기술·시스템·도구), schedule(일정·기한), constraints(보안·예산·인력 등 제약)를 각각 1~2문장으로 쓴다.
- 기획서에 없는 항목은 "기획서에 없음"으로 쓴다. 기획서에 없는 내용은 지어내지 않는다.
JSON 형식: {"purpose":"...","data":"...","tech":"...","schedule":"...","constraints":"..."}`;
  const DOC_FIELDS = [['purpose', '목적'], ['data', '다룰 데이터'], ['tech', '기술·도구'], ['schedule', '일정'], ['constraints', '제약']];
  async function apiDocSummary(inp) {
    const r = await AI.llm(S_SYS, { goal: inp.goal || null, fileName: inp.name, text: String(inp.text || '').slice(0, AI.DOC_CHARS), imageNotes: inp.imageNotes || [] });
    const lines = DOC_FIELDS.map(([k, l]) => [l, String(r[k] || '').trim()]).filter(([, v]) => v);
    if (!lines.length) throw new Error('요약이 비어 있어요');
    return { text: lines.map(([l, v]) => `${l}: ${v}`).join('\n') };
  }
  /* 가데이터: 문서를 이해하지 않고 핵심어가 든 문장을 옮긴다(그렇다고 표시) */
  function mockDocSummary(inp) {
    const lines = String(inp.text || '').split('\n').map(x => x.replace(/^[#>*\-·\s]+/, '').trim()).filter(x => x.length >= 6);
    const key = /(목적|목표|배경|데이터|자료|문서|기술|시스템|도구|일정|기간|기한|예산|보안|제약|범위)/;
    const pick = lines.filter(x => key.test(x)).slice(0, 5), use = (pick.length ? pick : lines.slice(0, 4)).map(x => x.slice(0, 90));
    return { text: ['(가데이터 요약 · 문서를 이해하지 않고 핵심어가 든 문장을 옮겼어요)'].concat(use.map(x => '· ' + x)).join('\n') };
  }
  AI.docSummary = (inp, opt) => AI.run('진단 에이전트', '기획서 요약', { goal: inp.goal, name: inp.name, chars: String(inp.text || '').length, imageNotes: inp.imageNotes || [] },
    () => mockDocSummary(inp), () => apiDocSummary(inp), opt);

  AI.diagQuestions = (inp, opt) => AI.run('진단 에이전트', '사전 점검 문항 생성', inp, mockQuestions, apiQuestions, opt);

  /* 5점 척도 응답 표시('4 그렇다')와 사전→사후 비교 (결과 보고서·진단 지시문 공통) */
  const ans = v => { const o = D.answerOpts.find(x => x[0] === String(v)); return o ? `${o[0]} ${o[1]}` : '미응답'; };
  AI.ansLabel = ans;
  AI.rose = (pre, post) => +post > +pre;

  /* 진단 에이전트 · 수준 진단 (점수는 저장만) */
  AI.levelOf = (questions, answers) => {
    const by = {};
    questions.forEach(q => { (by[q.area] = by[q.area] || []).push(D.answerWeight[answers[q.id]] ?? 0); });
    return Object.fromEntries(Object.entries(by).map(([k, v]) => [k, +(v.reduce((a, b) => a + b, 0) / v.length).toFixed(2)]));
  };
  function mockAssess(inp) {
    const { questions, answers, prefs } = inp, level = AI.levelOf(questions, answers);
    const dom = AI.domainOf(inp.goal), devL = level[D.areas.dev] ?? 0, domL = level[D.domains[dom].label] ?? 0;
    const start = devL >= 0.7 && domL >= 0.7 ? 3 : devL >= 0.7 ? 2 : 1;
    /* 5점 척도에서 4(그렇다)·5(매우 그렇다)로 답한 문항을 '이미 할 수 있는 것'으로 본다 (진단 에이전트 가데이터의 판단 기준) */
    const lab = q => AI.skillLabel(q.skill), can = q => +answers[q.id] >= 4;
    const known = questions.filter(can).map(lab);
    const gapQ = questions.filter(q => !can(q) && q.area !== D.areas.cert && (start === 1 || q.area !== D.areas.dev));
    const devKnown = questions.filter(q => q.area === D.areas.dev && can(q)).map(lab);
    const startReason = start === 1 ? '개발 기초부터 함께 다지도록 기초 단계부터 시작해요.' : start === 2 ? `${devKnown.slice(0, 3).join(', ')} 문항에 그렇다 이상으로 답해 기초 단계는 건너뛰어요.` : '목표 분야 문항에도 그렇다 이상으로 답해 업무 적용부터 시작해요.';
    const gapSkills = gapQ.map(q => q.skill);
    const fmt = prefs.format === 'video' ? '영상' : prefs.format === 'doc' ? '문서' : null;
    const res = Object.entries(D.res).filter(([, r]) => r.kind !== '자격' && r.stage >= start)
      .map(([id, r]) => [id, r.skills.filter(s => gapSkills.includes(s)).length + (fmt && r.format === fmt ? 0.5 : 0) - (r.cost ? 0.3 : 0)])
      .filter(([, s]) => s >= 1).sort((a, b) => b[1] - a[1]).map(([id]) => id);
    const picked = [];
    res.forEach(id => { const r = D.res[id]; if (picked.length < 4 && !picked.some(p => D.res[p].skills.join() === r.skills.join())) picked.push(id); });
    const certId = AI.certRes(prefs);
    if (certId) picked.push(certId);
    const notes = [];
    if (prefs.format === 'practice') notes.push('직접 구현을 선호해 실습 과제 비중을 높여 주세요.');
    if (!blank(prefs.budget) && +prefs.budget === 0) notes.push('예산이 0원이라 무료 자료를 먼저 쓰고, 유료 자료는 비용을 따로 보여 주세요.');
    if (String(prefs.etc || '').trim()) notes.push('사용자 고려 사항: ' + prefs.etc.trim());
    return {
      level, startStage: start, startReason, known: uniq(known), gaps: uniq(gapQ.map(lab)),
      competencies: uniq(gapQ.map(lab)).slice(0, 5), resourceIds: picked, outcome: D.domains[dom].outcome, handoffNotes: notes
    };
  }
  const A_SYS = `너는 GrowPath의 '진단 에이전트'다. 사전 점검 응답(5점 척도: 1 전혀 아님, 2 아님, 3 보통이다, 4 그렇다, 5 매우 그렇다)과 세부 사항(학습 선호·기타 고려 사항)으로 사용자의 현재 수준을 진단하고, 로드맵 계획 에이전트에게 넘길 내용을 정리한다.
- level: 영역별 0~1 값((점수-1)/4 의 평균). 사용자에게 보여주지 않고 사후 점검 비교용으로만 저장한다.
- startStage: 1 기초 다지기 / 2 핵심 이해 / 3 업무 적용 / 4 성과 확인 중 시작 단계. 개발 기초가 충분하면 2, 목표 분야 실무 경험도 충분하면 3.
- startReason: 시작 단계를 고른 이유 한 문장. 점수·숫자는 쓰지 않는다.
- known: 이미 할 수 있다고 답한 것, gaps: 더 익혀야 할 것 (짧은 명사구).
- competencies: 로드맵을 따라가면 익히게 될 역량 3~5개.
- resourceIds: catalog에서 이 사용자에게 맞는 자료 id 3~5개. catalog에 없는 id는 쓰지 않는다. 자격 자료는 자격증 계획이 있을 때만.
- outcome: 로드맵을 마치면 남는 결과물 한 문장. projectSummary(업무 프로젝트 기획서 요약)가 있으면 competencies·outcome을 그 프로젝트에 맞춘다.
- handoffNotes: 로드맵 계획 에이전트가 꼭 알아야 할 점 2~4개(선호, 제약, 기타 고려 사항 반영). '알아서'인 항목은 목표에 맞게 정한다.
JSON 형식: {"level":{"AI 이해":0.6},"startStage":2,"startReason":"...","known":[],"gaps":[],"competencies":[],"resourceIds":[],"outcome":"...","handoffNotes":[]}`;
  async function apiAssess(inp) {
    const r = await AI.llm(A_SYS, { goal: inp.goal, projectFile: inp.project, projectSummary: inp.projectSummary || null, details: AI.prefSummary(inp.prefs), answers: inp.questions.map(q => ({ area: q.area, statement: q.text, answer: ans(inp.answers[q.id]) })), catalog: AI.catalog(AI.certRes(inp.prefs)) });
    const arr = v => (Array.isArray(v) ? v.map(String).filter(Boolean).slice(0, 6) : []);
    const out = {
      level: AI.levelOf(inp.questions, inp.answers), modelLevel: r.level || {}, startStage: Math.min(4, Math.max(1, Math.round(+r.startStage) || 1)), startReason: String(r.startReason || '').trim(),
      known: arr(r.known), gaps: arr(r.gaps), competencies: arr(r.competencies), resourceIds: arr(r.resourceIds).filter(id => D.res[id]),
      outcome: String(r.outcome || '').trim(), handoffNotes: arr(r.handoffNotes)
    };
    /* 미리보기에 꼭 필요한 값이 비면 가데이터로 채우지 않고 실패로 본다 */
    if (!out.competencies.length || !out.outcome || !out.startReason) throw new Error('진단 결과가 비어 있어요');
    return out;
  }
  AI.diagAssess = (inp, opt) => AI.run('진단 에이전트', '수준 진단·전달 내용 정리', inp, mockAssess, apiAssess, opt);

  /* 로드맵 계획 에이전트 · 관점별 하위 에이전트 */
  const altSame = (id, used, fmt) => {
    const r = D.res[id];
    return Object.keys(D.res).find(k => k !== id && !used.has(k) && D.res[k].kind !== '자격' && D.res[k].stage === r.stage && (!fmt || D.res[k].format === fmt) && D.res[k].skills.some(s => r.skills.includes(s))) || null;
  };
  /* 가데이터 · 요청을 받아 다시 쓰기: 고른 칩과 활동만 정해진 규칙으로 반영하고, 바라는 점 문장은 읽지 않는다(그렇다고 적음) */
  function mockRegen(inp) {
    const pid = inp.pid, prev = inp.previousDef, r = inp.request, h = inp.handoff, start = h.startStage, notes = [], done = [];
    let acts = prev.acts.map(a => ({ key: a.id, stage: a.stage, title: a.title, res: a.res, hours: a.hours, how: a.how }));
    const used = () => new Set(acts.map(a => a.res).filter(Boolean));
    const rm = new Set((r.removeActs || []).map(x => x.key));
    if (rm.size) { acts = acts.filter(a => !rm.has(a.key)); done.push(`활동 ${rm.size}개 빼기`); }
    (r.replaceActs || []).forEach(x => {
      const a = acts.find(y => y.key === x.key); if (!a) return;
      const alt = a.res ? altSame(a.res, used(), null) : null;
      if (alt) { a.res = alt; a.title = `${D.res[alt].title} 학습`; }
      else if (!a.res) { a.title = `${a.title.replace(/ \(다른 방식\)$/, '')} (다른 방식)`; a.how = '같은 목표를 다른 방식으로 진행해요.'; }
      else notes.push(`「${x.title}」을 바꿀 비슷한 등록 자료가 없어 그대로 뒀어요.`);
    });
    if ((r.replaceActs || []).length) done.push(`활동 ${r.replaceActs.length}개 바꾸기`);
    const q = new Set(r.quick || []);
    if (q.has('비용 줄이기')) {
      const n = acts.length; acts = acts.filter(a => !(a.res && D.res[a.res].cost > 0 && D.res[a.res].kind !== '자격'));
      if (acts.length < n) done.push(`유료 자료 ${n - acts.length}개 빼기`); else notes.push('뺄 유료 자료가 없었어요.');
    }
    if (q.has('영상 위주') || q.has('문서 위주')) {
      const f = q.has('영상 위주') ? '영상' : '문서'; let n = 0;
      acts.forEach(a => { if (a.res && D.res[a.res].kind !== '자격' && D.res[a.res].format !== f) { const alt = altSame(a.res, used(), f); if (alt) { a.res = alt; a.title = `${D.res[alt].title} 학습`; n++; } } });
      if (n) done.push(`${f} 자료로 ${n}개 바꾸기`); else notes.push(`${f} 자료로 바꿀 등록 자료가 없었어요.`);
    }
    if (q.has('실습 늘리기')) { acts.push({ stage: Math.max(start, 2), title: '배운 내용으로 작은 예제 직접 만들기', res: null, hours: 4, how: '강의·문서에서 본 내용을 작은 예제로 직접 구현해요.' }); done.push('실습 과제 추가'); }
    if (q.has('업무 과제 늘리기')) { acts.push({ stage: Math.max(start, 3), title: '내 업무 문서로 기능 하나 적용해 보기', res: null, hours: 6, how: '담당 업무 문서 몇 건으로 만든 기능을 직접 적용해 봐요.' }); done.push('업무 과제 추가'); }
    if (q.has('더 짧게')) {
      const t = acts.filter(a => !a.res).sort((x, y) => (y.hours || 0) - (x.hours || 0))[0];
      if (t) { t.hours = Math.max(1, Math.round((t.hours || 4) * 0.6)); done.push('가장 긴 과제 시간 줄이기'); }
    }
    if (r.wish) notes.push('가데이터 모드라 바라는 점 문장은 읽지 않았어요. 고른 칩과 활동만 정해진 규칙으로 반영했어요. 실제 모델 모드에서는 문장도 반영해요.');
    const o = finishOption(pid, { tagline: prev.tagline, reason: prev.reason, pros: prev.pros, cons: prev.cons, acts, weeklyHours: prev.weeklyHours || h.prefs.weeklyHours }, 'mock', prev.offDomain);
    return Object.assign(o, { summary: done.join(' · ') || '요청을 살펴봤지만 바꿀 내용이 없었어요', notes: uniq(notes) });
  }
  function mockOption(inp) {
    if (inp.request && inp.previousDef) return mockRegen(inp);
    const pid = inp.pid, t = (inp.variant || 0) % 2 === 1 ? D.templatesAlt[pid] : D.templates[pid], h = inp.handoff;
    const acts = t.acts.map(a => Object.assign({}, a));
    /* 영상 선호면 문서 자료를 비슷한 영상 강좌로 바꾼다. 이미 들어 있는 강좌로는 바꾸지 않는다(같은 강좌가 두 번 들어가지 않게 · 10/14) */
    if (h.prefs.formatKey === 'video') acts.forEach(a => {
      const has = new Set(acts.map(x => x.res).filter(Boolean));
      const v = a.res && Object.keys(D.res).find(k => k !== a.res && !has.has(k) && D.res[k].format === '영상' && D.res[k].kind !== '자격' && D.res[k].stage === D.res[a.res].stage && D.res[a.res].format !== '영상' && D.res[k].skills.some(sk => D.res[a.res].skills.includes(sk)));
      if (v) { a.res = v; a.title = D.res[v].title + ' 수강'; }
    });
    const certId = h.prefs.certRes;
    if (certId) acts.push({ stage: 4, title: `${D.res[certId].title} 준비`, res: certId });
    let reason = t.reason;
    const hoursOf = a => (a.res ? D.res[a.res].hours : a.hours);
    const total = () => acts.filter(a => a.stage >= h.startStage).reduce((s, a) => s + hoursOf(a), 0);
    /* 주당 학습 시간이 '알아서'면 이 에이전트가 정한다: 기간이 있으면 그 안에 끝나게(주 2~12시간), 없으면 기본값 */
    const pickHours = () => (h.prefs.deadlineWeeks ? Math.min(12, Math.max(2, Math.ceil(total() / h.prefs.deadlineWeeks))) : D.autoHours);
    /* 시간 우선안은 정해진 기간 안에 맞춘다: 넘치면 자격 준비를 다음 계획으로 미룬다 */
    const cap = h.prefs.deadlineWeeks ? h.prefs.deadlineWeeks * (h.prefs.weeklyHours || 12) : null;
    if (pid === 'A2' && cap && certId && total() > cap) { acts.pop(); reason += ` ${h.prefs.deadlineWeeks}주 안에 끝내려고 자격 준비는 다음 계획으로 미뤘어요.`; }
    const weeklyHours = h.prefs.weeklyHours || pickHours();
    if (pid === 'A1' && h.prefs.formatKey === 'practice') reason += ' 직접 구현을 선호한다고 해서 실습 과제를 넣었어요.';
    if (pid === 'A2' && h.prefs.budgetWon === 0) reason += ' 예산이 없어 유료 과정 비용은 따로 표시했어요.';
    return finishOption(pid, Object.assign({}, t, { reason, acts, weeklyHours }), 'mock', AI.domainOf(h.goal) !== 'rag');
  }
  function finishOption(pid, raw, source, offDomain) {
    const per = D.perspectives[pid];
    /* 목록에 없는 자료 id는 화면에 그릴 정보가 없어 뺀다 (표시용 처리 · 검사 기능 아님) */
    const acts = (raw.acts || []).map((a, i) => {
      if (a.res && !D.res[a.res]) return null;
      const res = a.res || null, stage = Math.min(4, Math.max(1, Math.round(+a.stage) || 2));
      return { id: `${pid.toLowerCase()}-${i + 1}`, stage, title: String(a.title || (res ? D.res[res].title : '직접 수행 과제')).slice(0, 80), res, task: !res, hours: res ? D.res[res].hours : Math.min(60, Math.max(0.5, +a.hours || 2)), how: String(a.how || '') };
    }).filter(Boolean);
    if (!acts.length) throw new Error('활동이 비어 있어요');
    const list = v => (Array.isArray(v) ? v.map(String).filter(Boolean).slice(0, 4) : []);
    const wh = +raw.weeklyHours;
    return { id: pid, name: per.name, short: per.short, tagline: String(raw.tagline || per.focus).slice(0, 60), reason: String(raw.reason || ''), pros: list(raw.pros), cons: list(raw.cons), scope: String(raw.scope || ''), acts,
      weeklyHours: wh >= 0.5 && wh <= 40 ? Math.round(wh * 2) / 2 : null, source, offDomain: !!offDomain };
  }
  const R_SYS = p => `너는 GrowPath '로드맵 계획 에이전트'의 관점별 하위 에이전트 ${p.id} ${p.name}다. 관점: ${p.focus}.
진단 에이전트가 넘긴 내용(handoff)과 등록 자료 목록(catalog)으로 로드맵 후보 1개를 쓴다.
- 단계: 1 기초 다지기, 2 핵심 이해, 3 업무 적용, 4 성과 확인. handoff.startStage 이전 단계는 넣지 않는다.
- 외부 학습자료는 catalog의 id만 res로 쓴다. catalog에 없는 강좌·도서·자격은 만들지 않는다. 자료를 쓰면 hours는 catalog 값을 따른다.
- 직접 수행하는 실습 과제는 res를 null로 두고 hours(계획 시간)와 how(무엇을 하는지 한 문장)를 쓴다.
- handoff.prefs의 주당 시간(weeklyHours), 기간(deadlineWeeks), 예산(budgetWon)을 넘지 않게 한다. 예산이 0이면 유료 자료는 꼭 필요할 때만 쓰고 cons에 적는다.
- handoff.prefs.format(학습 방식)에 맞는 자료를 먼저 고른다. 영상 강의면 catalog의 format이 "영상"인 자료, 문서·도서 읽기면 "문서"인 자료를 먼저 쓰고, 직접 구현하며 학습이면 실습 과제 비중을 높인다. '알아서'면 관점에 맞게 고른다.
- handoff.prefs.weeklyHours가 null이면 사용자가 '알아서'로 둔 것이다. 관점과 기간에 맞게 주당 학습 시간을 정해 weeklyHours에 쓴다. 값이 있으면 그 값을 그대로 쓴다.
- handoff.prefs.certRes가 있으면 그 자격 자료를 4단계에 넣는다.
- handoff.projectSummary가 있으면 사용자가 적용할 업무 프로젝트 기획서 요약이다. 3 업무 적용 단계 과제를 이 프로젝트에 맞춘다.
- handoff.userNotes는 사용자가 적은 기타 고려 사항이다. 일정·환경 제약으로 보고 반영한다. 값이 '알아서'인 항목은 관점에 맞게 정한다.
- 다른 관점과 차이가 분명하게 쓴다. 문장은 해요체.
JSON 형식: {"tagline":"한 줄 요약","reason":"추천 이유 1~2문장","pros":["..."],"cons":["..."],"scope":"실행 범위 한 줄","weeklyHours":4,"acts":[{"stage":2,"title":"...","res":"v_llm","hours":5,"how":""}]}`;
  async function apiOption(inp) {
    const p = Object.assign({ id: inp.pid }, D.perspectives[inp.pid]);
    /* 다시 만들기: 요청이 없으면 활동 구성이 다른 안, 요청이 있으면 지금 안(previous)을 바탕으로 요청을 반영 */
    const extra = inp.request ? `
- 사용자가 요청(request)과 함께 이 관점의 안을 다시 만들어 달라고 했다. previous(지금 안)를 바탕으로 request를 반영해 고친다.
  · request.removeActs의 활동은 빼고, request.replaceActs의 활동은 catalog의 다른 자료나 다른 실습 과제로 바꾼다. request.quick(빠른 요청)과 request.wish(바라는 점)도 반영한다.
  · 요청과 관계없는 활동은 그대로 둬도 된다. 관점과 한도는 그대로 지킨다.
  · summary에 바꾼 점을 한 문장으로 쓰고, 반영하지 못한 요청은 notes에 쓴다. JSON에 "summary":"...","notes":[] 를 더한다.` : inp.previous ? `
- 사용자가 이 관점의 안을 다시 요청했다. previous와 활동 구성이 분명히 다르게 쓴다. 관점과 한도는 그대로 지킨다.` : '';
    const r = await AI.llm(R_SYS(p) + extra, { handoff: inp.handoff, catalog: AI.catalog(inp.handoff.prefs.certRes), previous: inp.previous || null, request: inp.request || null }, 'roadmap');
    const o = finishOption(inp.pid, r, AI.mode(), false);
    if (inp.request) Object.assign(o, { summary: String(r.summary || '').trim().slice(0, 80), notes: (Array.isArray(r.notes) ? r.notes : []).map(String).filter(Boolean).slice(0, 3) });
    return o;
  }
  /* 기록에는 지금 안 전체(previousDef) 대신 요약만 남긴다 */
  AI.roadmapOption = (inp, opt) => AI.run(`로드맵 계획 · ${inp.pid}`, `${D.perspectives[inp.pid].name} ${inp.request ? '요청 반영해 다시 작성' : inp.variant ? '다시 작성' : '작성'}`,
    Object.assign({}, inp, { previousDef: undefined }), () => mockOption(inp), () => apiOption(inp), Object.assign({ role: 'roadmap' }, opt));

  /* 로드맵 계획 에이전트 · 수정안 (10/14): 확정한 로드맵을 수정 요청(고른 항목 + 요청 문장)에 맞게 고친다.
     로드맵을 쓴 관점의 하위 에이전트가 쓰고, 관점을 바꾸면 새 관점의 하위 에이전트가 새로 쓴다.
     가데이터는 고른 항목만 정해진 규칙으로 반영하고, 요청 문장·코멘트 문장은 읽지 않는다(수정안에 그렇게 적는다) */
  function mockRevise(inp) {
    const { plan, handoff: h, changes: c, pid } = inp, notes = [], done = [], start = h.startStage;
    let acts, base = { tagline: plan.tagline, reason: (plan.def && plan.def.reason) || '', pros: (plan.def && plan.def.pros) || [], cons: (plan.def && plan.def.cons) || [] }, fresh = null;
    if (c.perspective) {
      fresh = mockOption({ pid, handoff: h });
      acts = fresh.acts.map(a => ({ stage: a.stage, title: a.title, res: a.res, hours: a.hours, how: a.how }));
      base = { tagline: fresh.tagline, reason: fresh.reason, pros: fresh.pros, cons: fresh.cons };
      done.push(`${pid} ${D.perspectives[pid].name}으로 다시 쓰기`);
    } else acts = plan.acts.map(a => ({ key: a.id, stage: a.stage, title: a.title, res: a.res, hours: a.hours, how: a.how, done: a.done }));
    const used = () => new Set(acts.map(a => a.res).filter(Boolean));
    if (c.startStage) {
      if (!c.perspective && c.startStage < plan.start) (D.templates[plan.opt] || { acts: [] }).acts.filter(a => a.stage >= c.startStage && a.stage < plan.start && !(a.res && used().has(a.res))).forEach(a => acts.push(Object.assign({}, a)));
      done.push(`${c.startStage}단계부터 시작`);
    }
    const rm = new Set((c.removeActs || []).map(x => x.key));
    if (rm.size) { acts = acts.filter(a => !rm.has(a.key)); done.push(`활동 ${rm.size}개 빼기`); }
    (c.replaceActs || []).forEach(x => {
      const a = acts.find(y => y.key === x.key); if (!a) return;
      const hint = c.replaceHint || '', fmt = /영상/.test(hint) ? '영상' : /(문서|도서|읽)/.test(hint) ? '문서' : null;
      const alt = a.res ? altSame(a.res, used(), fmt) || altSame(a.res, used(), null) : null;
      if (alt) { a.res = alt; a.title = `${D.res[alt].title} 학습`; }
      else if (!a.res) { a.title = `${a.title.replace(/ \(다른 방식\)$/, '')} (다른 방식)`; a.how = '같은 목표를 다른 방식으로 진행해요.'; }
      else notes.push(`「${x.title}」을 바꿀 비슷한 등록 자료가 없어 그대로 뒀어요.`);
    });
    if ((c.replaceActs || []).length) done.push(`활동 ${c.replaceActs.length}개 바꾸기`);
    (c.addResources || []).forEach(id => { if (D.res[id] && !used().has(id)) acts.push({ stage: Math.max(start, D.res[id].stage || 2), title: `${D.res[id].title} 학습`, res: id }); });
    (c.addTasks || []).forEach(t => acts.push({ stage: Math.max(start, 3), title: t.slice(0, 80), res: null, hours: 4, how: '사용자가 추가한 과제예요.' }));
    const added = (c.addResources || []).length + (c.addTasks || []).length;
    if (added) done.push(`활동 ${added}개 추가`);
    if (c.format) {
      const fk = h.prefs.formatKey;
      if (fk === 'video' || fk === 'doc') {
        const f = fk === 'video' ? '영상' : '문서'; let n = 0;
        /* 완료한 활동은 직접 고르지 않았으면 바꾸지 않는다 */
        acts.forEach(a => { if (!a.done && a.res && D.res[a.res].kind !== '자격' && D.res[a.res].format !== f) { const alt = altSame(a.res, used(), f); if (alt) { a.res = alt; a.title = `${D.res[alt].title} 학습`; n++; } } });
        if (!n) notes.push(`${c.format}에 맞는 다른 등록 자료가 없어 자료는 그대로 뒀어요.`);
      }
      if (fk === 'practice' && !acts.some(a => !a.res && /(예제|실습)/.test(a.title))) acts.push({ stage: Math.max(start, 2), title: '배운 내용으로 작은 예제 직접 만들기', res: null, hours: 4, how: '강의·문서에서 본 내용을 작은 예제로 직접 구현해요.' });
      done.push(`학습 방식 ${c.format}`);
    }
    if (c.certification) {
      acts = acts.filter(a => !(a.res && D.res[a.res].kind === '자격'));
      if (h.prefs.certRes) acts.push({ stage: 4, title: `${D.res[h.prefs.certRes].title} 준비`, res: h.prefs.certRes });
      done.push(`자격증 ${c.certification}`);
    }
    if (c.budgetWon != null && h.prefs.budgetWon != null) {
      const cost = () => [...used()].reduce((s, id) => s + (D.res[id].cost || 0), 0);
      let cut = 0;
      while (cost() > h.prefs.budgetWon) {
        const paid = acts.filter(a => !a.done && a.res && D.res[a.res].cost > 0 && D.res[a.res].kind !== '자격').sort((x, y) => D.res[y.res].cost - D.res[x.res].cost)[0];
        if (!paid) break; acts = acts.filter(a => a !== paid); cut++;
      }
      done.push(cut ? `예산에 맞춰 유료 자료 ${cut}개 빼기` : '예산 반영');
    }
    /* 코멘트로 시작했는데 고른 항목이 없으면, 가데이터는 문장을 읽지 못하므로 예시 수정안(3단계 과제 시간 늘리기)을 보여 준다 */
    if (inp.fromComment && !Object.keys(c).length) {
      const t = acts.filter(a => a.stage === 3 && !a.res).pop();
      if (t) { t.hours = (t.hours || 4) + 6; t.title = `${t.title.replace(/ \(점검 확대\)$/, '')} (점검 확대)`; done.push('3단계 과제 시간 늘리기(예시)'); }
    }
    if (c.constraints || inp.request) notes.push('가데이터 모드라 요청 문장(요청 내용·일정·환경 제약)은 읽지 않았어요. 고른 항목만 정해진 규칙으로 반영한 예시 수정안이에요. 실제 모델 모드에서는 문장도 반영해요.');
    const total = () => acts.filter(a => a.stage >= start).reduce((s, a) => s + (a.res ? D.res[a.res].hours : a.hours || 0), 0);
    const fit = () => (h.prefs.deadlineWeeks ? Math.min(12, Math.max(2, Math.ceil(total() / h.prefs.deadlineWeeks))) : D.autoHours);
    const wh = h.prefs.weeklyHours || (c.weeklyHours != null || c.deadlineWeeks != null || c.perspective ? fit() : plan.hours);
    if (c.weeklyHours != null || c.deadlineWeeks != null) done.push(`주당 ${wh}시간${h.prefs.weeklyHours ? '' : '(에이전트가 정함)'}`);
    const o = finishOption(pid, Object.assign({}, base, { acts, weeklyHours: wh }), 'mock', false);
    return Object.assign(o, { summary: done.length ? done.join(' · ') : '요청을 살펴봤지만 바꿀 내용이 없었어요', notes: uniq(notes) });
  }
  const REV_SYS = p => `너는 GrowPath '로드맵 계획 에이전트'의 관점별 하위 에이전트 ${p.id} ${p.name}다. 관점: ${p.focus}.
사용자가 확정한 로드맵(current)을 수정 요청에 맞게 고친 새 로드맵 1개를 쓴다.
- changes의 항목은 반드시 반영한다. request는 사용자가 적은 요청 문장이다(부서장 코멘트에서 옮긴 것일 수 있다). 함께 반영하고, 둘이 부딪히면 changes를 따른다.
- handoff.projectSummary(업무 프로젝트 기획서 요약)가 있으면 바꾸는 과제도 그 프로젝트에 맞춘다.
- 요청과 관계없는 활동과 주당 시간은 그대로 둔다. 완료한 활동(done: true)은 요청이 없으면 빼거나 바꾸지 않는다. 목표는 바꾸지 않는다.
- changes.perspective가 있으면 너의 관점으로 로드맵을 새로 쓴다. current는 참고만 하고, 계속 쓸 자료는 그대로 둔다.
- removeActs의 활동은 뺀다. replaceActs의 활동은 catalog의 다른 자료나 다른 실습 과제로 바꾼다(replaceHint 참고). addResources는 catalog id를 그대로 res로 넣고, addTasks는 실습 과제(res null)로 넣는다.
- 단계: 1 기초 다지기, 2 핵심 이해, 3 업무 적용, 4 성과 확인. handoff.startStage 이전 단계는 넣지 않는다.
- 외부 학습자료는 catalog의 id만 res로 쓴다. 자료를 쓰면 hours는 catalog 값을 따른다. 실습 과제는 res를 null로 두고 hours와 how를 쓴다.
- handoff.prefs의 주당 시간(weeklyHours)·기간(deadlineWeeks)·예산(budgetWon)·학습 방식(format)·자격(certRes)을 지킨다. weeklyHours가 null이면 관점과 기간에 맞게 정해 weeklyHours에 쓴다. certRes가 있으면 그 자격 자료를 4단계에 넣고, 없으면 자격 준비 활동은 뺀다.
- summary: 바꾼 내용 한 문장. notes: 요청 중 반영하지 못한 것과 이유(없으면 빈 배열). 문장은 해요체.
JSON 형식: {"summary":"...","notes":[],"tagline":"한 줄 요약","reason":"...","pros":["..."],"cons":["..."],"weeklyHours":4,"acts":[{"stage":2,"title":"...","res":"v_llm","hours":5,"how":""}]}`;
  async function apiRevise(inp) {
    const p = Object.assign({ id: inp.pid }, D.perspectives[inp.pid]), pl = inp.plan;
    const current = { perspective: `${pl.opt} ${pl.name}`, weeklyHours: pl.hours, startStage: pl.start, acts: pl.acts.map(a => ({ key: a.id, stage: a.stage, title: a.title, res: a.res, hours: a.hours, how: a.how || '', done: a.done })) };
    const r = await AI.llm(REV_SYS(p), { current, handoff: inp.handoff, changes: inp.changes, request: inp.request, catalog: AI.catalog(inp.handoff.prefs.certRes) }, 'roadmap');
    const o = finishOption(inp.pid, r, AI.mode(), false);
    return Object.assign(o, { summary: String(r.summary || '').trim().slice(0, 80), notes: (Array.isArray(r.notes) ? r.notes : []).map(String).filter(Boolean).slice(0, 4) });
  }
  AI.roadmapRevise = (inp, opt) => AI.run(`로드맵 계획 · ${inp.pid}`, inp.changes.perspective ? '관점 바꿔 다시 작성' : '수정안 작성', inp, mockRevise, apiRevise, Object.assign({ role: 'roadmap' }, opt));

  /* 규정 에이전트 · 규정 RAG
     등록 규정 (10/15): 로그인한 직원의 직원 구분으로 규정 묶음을 고른다(사용자 결정).
       일반직 → 일반직 규정 16건(regulation-general.js · 본문 조항만, 부칙·별표·별지 서식 제외)
       실무직 → 「실무직 관리규정」(regulation.js · 지금 실무직 계정은 없음)
     국외근무 규정 2건은 국외근무를 묻는 질문에만 검색한다(국내 근무 직원에게 자동 적용하지 않음 · 받은 안내문). 묶음이 없는 직원 구분은 '적용 대상 아님' */
  const GEN = window.GPREG_GEN || { group: '일반직', regs: [], articles: [] };
  AI.REG_SETS = {
    일반직: { group: '일반직', label: `일반직 규정 ${GEN.regs.length}건`, org: GEN.org || REG.org, regs: GEN.regs, articles: GEN.articles },
    실무직: { group: '실무직', label: `「${REG.name}」`, org: REG.org, regs: [{ key: 'prac', name: REG.name, rev: REG.rev, effective: REG.effective, file: REG.file, overseas: false }],
      articles: REG.articles.map(a => Object.assign({ reg: 'prac' }, a)) }
  };
  const ALL_REGS = Object.values(AI.REG_SETS).flatMap(s => s.regs), ALL_ARTS = new Map(Object.values(AI.REG_SETS).flatMap(s => s.articles).map(a => [a.id, a]));
  AI.article = id => ALL_ARTS.get(id);
  AI.regOf = key => ALL_REGS.find(r => r.key === key) || null;
  AI.regSet = () => AI.REG_SETS[(GP.me() || {}).empGroup] || null;
  AI.regApplies = () => !!AI.regSet();
  /* 조항 이름: 「인재개발규정」 제7조(학습시간 및 필수교육) */
  AI.artName = a => `「${(AI.regOf(a.reg) || {}).name || ''}」 ${a.no}(${a.title})`;
  /* 등록되지 않은 기준 이름: 규정 이름이면 「」로 감싸고, 별표·'따로 정한' 기준은 그대로 */
  AI.missLabel = m => (/[「」]/.test(m) || !/(규정|규칙|세칙|운영기준)$/.test(m) ? String(m) : `「${m}」`);
  const OVERSEAS = /(국외|해외|외국|주재국|국외사무소)\s*(근무|파견|사무소|주재|발령)|국외근무/;
  /* 검색 대상: 내 직원 구분의 규정 묶음(국외근무 규정은 국외근무 질문에만). 묶음이 없으면 등록된 조항 전부(참고로만 씀) */
  AI.regArticles = q => {
    const set = AI.regSet(), arts = set ? set.articles : [...ALL_ARTS.values()], os = OVERSEAS.test(q || '');
    return arts.filter(a => os || !(AI.regOf(a.reg) || {}).overseas);
  };
  const SYN = [
    [/(출장|여비|교통비|숙박|일비)/, ['여비', '출장']], [/(교육|강의|수강|공부|학습|연수|훈련)/, ['교육훈련', '인재개발', '교육', '학습']],
    [/(근무\s*시간|근무 형태|근무형태|교대|통상|야간|출퇴근)/, ['근로자의 종류', '통상근무자', '교대근무자', '근무시간', '통상근무', '복무']], [/(유연|재택|원격|시차)/, ['유연근무', '원격근무', '근무시간선택']],
    [/(휴직|복직)/, ['휴직', '복직']], [/(휴가|연차|병가|경조)/, ['휴가', '연차']],
    [/(평가|평정|등급)/, ['근무성적평정', '평정']], [/(승진|승급)/, ['승진']], [/(월급|보수|연봉|임금|급여|성과급|수당)/, ['보수', '연봉', '수당', '성과급']], [/(전보|부서 이동|파견)/, ['전보']],
    [/(채용|입사|수습)/, ['채용', '수습']], [/(징계|상벌|경고)/, ['상벌', '징계', '경고']], [/(복지|학자금|의료비|경조금)/, ['복지후생', '복지']], [/(퇴직|정년)/, ['정년퇴직', '퇴직금', '퇴직']],
    [/(겸직|부업|외부강의|외부 강의)/, ['부업', '겸직', '외부강의']], [/(전결|결재|승인권)/, ['전결', '결재']], [/(직제|조직|정원)/, ['직제', '기구', '정원']],
    [/(상담|고충|불합리)/, ['인사상담', '고충']], [/(안전|보건)/, ['안전보건', '안전']], [/(재해|보상)/, ['재해보상']], [/(복무|의무)/, ['복무', '의무']], [/(괴롭힘)/, ['괴롭힘']],
    [/(언제|시기|기준일)/, ['시기', '기준일'], 2], [/(점수|배점|등급)/, ['점수', '배점', '등급'], 2], [/(누가|평정자|담당)/, ['평정자', '담당'], 2], [/(신청|절차)/, ['신청', '절차'], 2]
  ];
  AI.retrieve = function (q, k) {
    const terms = SYN.filter(([re]) => re.test(q)).flatMap(([, t, w]) => t.map(x => [x, w || 1]));
    if (!terms.length || !terms.some(([, w]) => w === 1)) return [];
    /* 의도 단어(언제·누가 등, 가중치 2)는 순위만 올리고, 주제 단어가 하나도 없는 조항은 빼낸다 */
    const hit = (a, t) => (a.title.includes(t) ? 3 : 0) + (a.text.includes(t) ? 1 : 0);
    return AI.regArticles(q).filter(a => terms.some(([t, w]) => w === 1 && hit(a, t)))
      .map(a => [a, terms.reduce((s, [t, w]) => s + w * hit(a, t), 0)])
      .sort((x, y) => y[1] - x[1]).slice(0, k || 3).map(([a, s]) => ({ id: a.id, score: s }));
  };
  const firstSentence = t => { const c = t.replace(/<[^>]*>|\[[^\]]*\]/g, '').replace(/\s+/g, ' ').trim(); const m = c.match(/^.*?다\./); return (m ? m[0] : c).slice(0, 170); };
  /* 가데이터 고정 답 (일반직 · 10/15): 시연 질문마다 일반직 규정 원문을 읽고 그 조항에 적힌 내용만 쓴다(사용자 결정).
     조항이 '따로 정한다'·별표로 넘긴 기준은 등록되지 않았으므로 '일부만 확인'으로 두고 미등록 기준을 적는다 */
  const CANNED_GEN = {
    edu: { level: 'ok', summary: '일반직 직원의 교육에 관한 세부사항은 「인재개발규정」이 정해요(「취업규칙」 제76조의2).', apply: '교육은 자체교육과 위탁교육으로 나뉘고, 학습주체별로 인재개발담당부서 주관학습·부서자체학습·개인학습으로 구분돼요(「인재개발규정」 제3조). {이름} 님도 매년 기준학습시간 이상을 이수해야 하고, 개인학습도 학습시간에 포함돼요(제7조).', more: ['직급별 연간 기준학습시간은 별표 1에 있는데, 별표는 등록하지 않아 답할 수 없어요.'], basis: ['emp-76-2', 'dev-3', 'dev-7'], missing: ['「인재개발규정」 별표 1(직급별 연간 기준학습시간)'] },
    support: { level: 'unclear', summary: '교육비를 어떤 기준으로 지원하는지는 등록된 조항에 적혀 있지 않아요. 국내 위탁교육 경비의 지급기준은 사장이 따로 정한다고만 되어 있어요.', apply: '외부 교육기관에 맡기는 과정이면 위탁교육(「인재개발규정」 제17조)에 해당하는지 먼저 봐야 해요. 국내 위탁교육 경비 지급기준은 사장이 따로 정하고(제24조 ①), 교육 신청은 통합교육포털에서 해요(제9조). 그래서 계획의 예상 비용에서 지원금을 빼지 않았어요.', more: ['담당 부서에 물어볼 질문: 온라인 유료 과정도 위탁교육 경비 지원 대상인가요?'], basis: ['dev-17', 'dev-24', 'dev-9'], missing: ['국내 위탁교육 경비 지급기준(사장이 따로 정함)'] },
    travel: { level: 'ok', summary: '교육명령을 받은 교육에 가면 교육출장 명령을 받고, 「여비규정」으로 정한 출장여비를 받아요(「인재개발규정」 제11조 ③).', apply: '편도 40킬로미터를 넘고 전체 80킬로미터를 넘는 다른 행정단위로 가면 운임·일비·식비는 정액, 숙박비는 실비로 받아요(「여비규정」 제8조 ①). 가까운 곳은 사장이 정하는 바에 따라 예산 범위에서 근거리출장비를 받을 수 있고(「여비규정」 제13조의2), 근거리 교육출장 여비는 인재개발 담당부서의 장이 따로 정해요. 지금 계획의 교육은 모두 온라인이라 출장이 생기지 않을 수도 있어요.', more: ['정액 금액은 「여비규정」 별표 1에 있는데, 별표는 등록하지 않아 금액은 답할 수 없어요.'], basis: ['dev-11', 'emp-47', 'trip-8', 'trip-13-2'], missing: ['「여비규정」 별표 1(국내여비 지급표)'] },
    hours: { level: 'unclear', summary: '근무시간 중에 하는 개인 학습을 근무로 인정하는지는 등록된 조항에 적혀 있지 않아요. 확인되는 부분까지 알려드릴게요.', apply: '{이름} 님이 통상근무자라면 기본 근무시간은 09시부터 18시까지이고, 1주 근로시간은 휴게시간을 빼고 40시간이에요(「취업규칙」 제12조). 교육명령을 받은 교육은 교육출장 명령을 받아 참석해요(「인재개발규정」 제11조 ③). 학습시간의 세부 인정기준과 절차는 인재개발담당부서의 장이 따로 정해요(제7조 ②).', more: ['근무시간 중 온라인 강의를 들어도 되는지', '개인학습 시간이 기준학습시간으로 인정되는 방법'], basis: ['emp-12', 'dev-11', 'dev-7'], missing: ['학습시간 인정기준(인재개발담당부서의 장이 따로 정함)'] },
    eval: { level: 'ok', summary: '정기평정은 매년 10월 말일을 기준으로 그 전 1년간을 평정해요(「인사규정시행세칙」 제27조).', apply: '수시평정은 정기평정 이후 사장이 특히 필요하다고 인정할 때 해요. 평정 전에 {이름} 님은 인사시스템의 본인기술서와 업무실적평가표를 입력하고, 1차·2차 평정자가 인사시스템으로 평정해요(제29조의3).', more: ['평정기준일에 휴직·파견·교육 중이라 본인기술서를 쓰지 못할 것 같으면 미리 본사 인사담당부서장에게 낼 수 있어요(제29조의3 제2호).'], basis: ['hrd-27', 'hrd-29-3'], missing: [] },
    promo: { level: 'ok', summary: '승진은 상위직 결원 범위 안에서 차하위 직급자 중에서 근무성적, 경력, 그 밖의 능력의 실증에 따라요(「인사규정」 제22조).', apply: '직급마다 승진소요최저연수가 있어요(예: 5급에서 4급 2년, 4급에서 3급 3년 · 제23조). 3급 이상은 승진후보자 명부에 오른 사람 중에서, 4급과 6급 이하는 승진소요최저연수가 지난 사람 중에서 임용하고, 세부 방법은 세칙으로 정해요(제24조). {이름} 님이 승진할 수 있는지는 예측하지 않아요.', more: ['종합근무평정과 승진후보자 명부 작성 기준은 「인사규정시행세칙」 제5장에 있어요.'], basis: ['hr-22', 'hr-23', 'hr-24'], missing: [] }
  };
  /* 이어 묻기 고정 답(일반직): 앞 답 주제 + 이번 질문 뜻. 조항에 없는 기한은 짐작하지 않는다 */
  const FOLLOW_GEN = [
    ['support', /(신청|언제|기한|마감|어디)/, { level: 'unclear', summary: '교육 신청은 통합교육포털에서 해요(「인재개발규정」 제9조). 신청 마감일은 조항에 정해져 있지 않아요.', apply: '선정된 교육대상자는 교육명령이 확정되기 전까지 통합교육포털에서 취소신청을 할 수 있고(제10조 ②), 교육명령은 교육 시작 1주 전까지 내려요(제11조 ①). 과정마다 신청 기간은 통합교육포털 공지에서 확인해 주세요.', more: [], basis: ['dev-9', 'dev-10', 'dev-11'], missing: [] }],
    ['travel', /(금액|얼마|일비|식비|숙박)/, { level: 'missing', summary: '출장 여비 정액은 「여비규정」 별표 1에 있는데, 별표는 등록하지 않아 금액은 답할 수 없어요.', apply: '조항에는 운임·일비·식비는 별표 1에 따른 정액, 숙박비는 별표 1의 범위에서 실비로 준다고만 적혀 있어요(「여비규정」 제8조 ①).', more: ['여비 담당 부서에 별표 1의 금액을 확인해 주세요.'], basis: ['trip-8'], missing: ['「여비규정」 별표 1(국내여비 지급표)'] }]
  ];
  /* 가데이터 고정 답 (실무직 · 10/14): 「실무직 관리규정」만 근거. 실무직 묶음에는 일반직 규정(인재개발규정 등)을 넣지 않았다(10/15 사용자 결정) */
  const CANNED = {
    edu: { level: 'ok', summary: '실무직의 교육훈련은 「인재개발규정」을 따라요.', apply: '{이름} 님은 실무직이라 이 조항이 적용돼요. 교육 신청·승인, 비용 지원, 교육 인정 조건은 「인재개발규정」에서 확인해야 해요.', more: ['「인재개발규정」은 실무직 규정 묶음에 들어 있지 않아 세부 조건은 답할 수 없어요.'], basis: ['a3', 'a35'], missing: ['인재개발규정'] },
    support: { level: 'missing', summary: '교육비 지원 여부는 지금 등록된 자료로는 확인할 수 없어요.', apply: '교육훈련은 「인재개발규정」을 따르는데(제35조), 실무직 규정 묶음에는 그 규정이 없어요. 그래서 계획의 예상 비용에서 지원금을 빼지 않았어요.', more: ['담당 부서에 물어볼 질문: 온라인 유료 과정도 교육비 지원 대상인가요?', '사전 승인이 필요하다면 언제까지 신청해야 하나요?'], basis: ['a35'], missing: ['인재개발규정'] },
    travel: { level: 'missing', summary: '교육 출장 여비는 「여비규정」을 따르는데, 실무직 규정 묶음에 없어 지급 여부를 확인할 수 없어요.', apply: '실무직의 업무 수행에 따른 여비는 「여비규정」을 준용해요(제34조). 지금 계획의 교육은 모두 온라인이라 출장이 생기지 않을 수도 있어요.', more: ['교육 참석 출장이 ‘업무 수행’에 해당하는지', '「여비규정」의 지급 기준과 사전 승인 절차'], basis: ['a34'], missing: ['여비규정'] },
    hours: { level: 'unclear', summary: '근무시간 중 수강이 되는지는 확정할 수 없어요. 확인되는 부분까지 알려드릴게요.', apply: '{이름} 님이 통상근무자라면 휴게시간을 빼고 1주 40시간·1일 8시간 근무해요(제4조). 복무는 「취업규칙」, 교육훈련은 「인재개발규정」을 따르는데 두 규정은 실무직 규정 묶음에 없어요.', more: ['근무시간 중 교육 참여에 승인이 필요한지', '교육 시간이 근무시간으로 인정되는지'], basis: ['a4', 'a15', 'a35'], missing: ['취업규칙', '인재개발규정'] }
  };
  /* 사내 생활 도우미 (4차 묶음 7 · NFR-01): 별도 분류 모델 없이 규정 에이전트의 LLM 지시문으로 질문을 분류하고, 유형에 맞게만 답한다(호출 한 번).
     regulation 규정 질문(승진·발령·보수·성과급 포함) — 등록된 조항에 명시된 경우에만 근거와 함께 답하고, 없으면 답하지 않고 담당 부서 안내
     general    업무·사내 생활 질문 — 사내 생활은 가상 사내 홈페이지 메뉴 안내(D.intranet) 안에서만, 업무·학습은 일반 답변, 앱 사용법은 메뉴 안내
     out        업무·사내 생활과 관련 없는 질문(주식·날씨·스포츠 등) — 답하지 않는다
     clarify    어느 쪽인지 정하기 어려울 때 — 되묻고 고를 수 있는 질문을 보여 준다(NFR-01 '불확실한 분류는 사용자에게 확인')
     가데이터 모드는 같은 유형을 키워드 규칙으로 흉내 낸다(분류 모델 아님) */
  const REG_HINT = /(규정|조항|교육비|지원금|여비|출장|근무\s*시간|근무\s*형태|교대|복무|휴가|휴직|복직|평정|보수|급여|월급|수당|성과급|승진|발령|전보|징계|상벌|퇴직|정년|복지 제도|채용|수습|교육\s*인정|교육훈련|유연근무|재택|원격근무|겸직|부업|외부\s*강의|연차|병가|직제|전결|국외근무)/;
  /* 승진·발령·성과급: 규정에 그 내용이 '명시'된 경우에만 규정 답변. 근거 조항 원문에 이 말이 없으면 답하지 않는다 */
  const HR_TERMS = /(승진|발령|성과급|상여)/;
  const OUT_HINT = /(주식|주가|코스피|코스닥|나스닥|비트코인|코인 시세|가상화폐|환율|날씨|기온|미세먼지|비가 와|눈이 와|야구|축구|농구|배구|골프 대회|경기 결과|스코어|월드컵|올림픽|로또|연예인|아이돌|드라마|예능)/;
  const GENERAL = [
    [/(로드맵|계획).*(기간|바꾸|수정|늘리|줄이)|수정 요청/, { source: 'app', summary: '로드맵은 내 로드맵의 ‘수정 요청’에서 바꿀 수 있어요.', apply: '주당 시간·기간·예산·학습 방식·자격증·일정 제약·시작 단계·관점·활동 빼기·바꾸기·추가를 여러 개 고르거나 요청을 문장으로 적으면, 로드맵을 쓴 관점의 에이전트가 수정안을 먼저 보여 주고 확정해야 로드맵이 바뀌어요.', links: [['roadmap', '내 로드맵']] }],
    [/(사후|점검 결과|보고서)/, { source: 'app', summary: '로드맵을 마무리하려면 점검·보고서에서 사후 점검을 시작하세요.', apply: '사전 점검과 같은 문항에 다시 답하면 진단 에이전트가 결과 보고서를 만들어 드려요.', links: [['checks', '점검·보고서']] }],
    [/(rag|래그|검색\s*증강)/i, { source: 'work', summary: 'RAG는 질문과 관련된 문서를 먼저 찾아서, 그 내용을 근거로 LLM이 답하게 하는 방식이에요.', apply: '문서를 잘게 나눠 임베딩으로 색인하고, 질문과 가까운 조각을 찾아 프롬프트에 함께 넣어요. 지금 로드맵의 ‘핵심 이해’ 단계에서 다뤄요.', more: ['더 알고 싶으면 학습 자료의 LangChain 공식 문서를 참고하세요.'], links: [['resources', '학습 자료']] }],
    [/(임베딩|벡터)/, { source: 'work', summary: '임베딩은 문장을 숫자 벡터로 바꿔, 뜻이 비슷한 문장끼리 가까이 놓이게 하는 방법이에요.', apply: '벡터 DB에 문서 조각의 임베딩을 넣어 두면, 질문과 가까운 조각을 빠르게 찾을 수 있어요.' }],
    [/(파이썬|python)/i, { source: 'work', summary: 'Python은 공식 튜토리얼로 기본 문법부터 익히는 게 빨라요.', apply: '학습 자료의 ‘The Python Tutorial’에서 필요한 장만 골라 읽어도 충분해요.', links: [['resources', '학습 자료']] }]
  ];
  /* 가데이터 되묻기 예시: 무엇을 묻는지 갈리는 짧은 질문 */
  const AMBIG = [
    [/점수/, q => !/(평정|점검|자격|시험)/.test(q), ['근무성적평정 점수는 어떻게 구성되나요?', '사전·사후 점검 결과는 어디서 보나요?']],
    [/^(어디서|어떻게)\s*신청/, q => q.length <= 14, ['교육 과정 신청은 어디서 하나요?', '휴가 신청은 어디서 하나요?', '통근버스 탑승 신청은 어디서 하나요?']]
  ];
  const ANS = (o) => Object.assign({ kind: 'general', level: 'general', source: '', summary: '', apply: '', more: [], basis: [], missing: [], intranet: [], question: '', options: [], retrieved: [] }, o);
  /* 가상 사내 홈페이지 안내에서 질문과 맞는 메뉴 (키워드) */
  AI.intranetHits = q => { const t = String(q || '').toLowerCase(); return D.intranet.map(x => [x, x.keys.filter(k => t.includes(k.toLowerCase())).length]).filter(([, n]) => n).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([x]) => x.id); };
  function mockGeneral(q) {
    const hit = GENERAL.find(([re]) => re.test(q));
    const base = hit ? hit[1] : { source: 'work', summary: '가데이터 모드라 이 질문에는 준비된 답이 없어요.', apply: '좌측 ‘AI 모델’에서 RunPod-Ollama나 OpenAI API를 쓰면 업무·학습 질문에도 답해요. 업무·사내 생활과 관계없는 질문에는 답하지 않아요.' };
    return ANS(clone(base));
  }
  /* 이어 묻기(10/14): '그럼 신청은 언제까지?'처럼 주제 단어 없이 앞 대화에 기대는 질문 */
  const FOLLOW = /^(그럼|그러면|그건|그거|그게|그때|그런데|근데|이건|이거|거기|그 ?다음|또|그리고|혹시|아까|방금)/;
  /* 고정 답 주제. 내 규정 묶음에 그 주제의 고정 답이 있을 때만 쓴다(평정·승진은 일반직만) */
  const TOPICS = [['travel', /(여비|출장비 지급|출장 여비)/], ['hours', /(근무\s*시간|수강|복무|근무\s*형태|교대|통상)/], ['support', /(교육비|지원금|지원을 받)/],
    ['edu', /(교육\s*인정|교육훈련|교육.*규정|규정.*교육)/], ['eval', /(근무성적평정|평정).*(언제|시기|기준일|하나요|해요)|언제.*평정/], ['promo', /승진.*(기준|요건|조건|어떻게|하려면|궁금|방법)/]];
  const cannedSet = () => ((AI.regSet() || {}).group === '일반직' ? CANNED_GEN : CANNED);
  const topicOf = q => { const t = TOPICS.find(([, re]) => re.test(q)); return t && cannedSet()[t[0]] ? t[0] : null; };
  const isFollow = (q, prev) => !!prev && !topicOf(q) && !AI.intranetHits(q).length && (FOLLOW.test(q) || (q.length <= 16 && !REG_HINT.test(q) && !GENERAL.some(([re]) => re.test(q)) && !AMBIG.some(([re, ok]) => re.test(q) && ok(q))));
  const named = (o, topic) => ANS(Object.assign({ kind: 'regulation', topic }, JSON.parse(JSON.stringify(o).replace(/\{이름\}/g, meName()))));
  /* 가데이터 이어 묻기: 준비한 이어 묻기 답이 있으면 그것을, 없으면 앞 답변의 근거 조항과 미등록 기준만 다시 말한다(조항에 없는 내용은 짐작하지 않음) */
  function mockFollow(q, prev) {
    const a = prev.a, head = `앞에서 물으신 ‘${prev.q}’에 이어서 답할게요.`;
    if (a.kind !== 'regulation' || a.level === 'none' || a.level === 'scope') return ANS({ source: 'work', summary: head, apply: '가데이터 모드라 이어지는 질문에 쓸 답은 준비돼 있지 않아요. 좌측 ‘AI 모델’에서 RunPod-Ollama나 OpenAI API를 쓰면 앞 대화를 이어 받아 답해요.' });
    /* 앞 답의 주제는 앞 질문으로 다시 알아낸다(앞 대화로 넘기는 답에는 주제를 싣지 않음) */
    const tp = a.topic || topicOf(prev.q), f = (AI.regSet() || {}).group === '일반직' && FOLLOW_GEN.find(([t, re]) => t === tp && re.test(q));
    if (f) { const o = named(f[2], tp); o.summary = `${head} ${o.summary}`; return o; }
    const arts = (a.basis || []).map(id => AI.article(id)).filter(Boolean), nos = arts.map(x => `${x.no}(${x.title})`).join('·');
    if ((a.missing || []).length) {
      const ms = a.missing.map(AI.missLabel).join('·');
      return ANS({ kind: 'regulation', level: 'missing', summary: `${head} ‘${q}’도 지금 등록된 자료로는 확인할 수 없어요.`, apply: `앞 답변의 근거 조항${nos ? `(${nos})` : ''}은 ${ms}에 기준을 넘기고 있는데, 그 내용이 등록되지 않았어요. 원문에 없는 기한·절차를 짐작해서 답하지 않을게요.`, more: [`담당 부서에 물어볼 질문: ${q}`], basis: a.basis || [], missing: a.missing.slice() });
    }
    return ANS({ kind: 'regulation', level: 'none' });
  }
  /* 근거 조항 원문(제목·본문)에 그 인사 용어가 있어야 '명시'로 본다 */
  const hrStated = (q, ids) => { const m = q.match(HR_TERMS); return !m || ids.some(id => { const a = AI.article(id); return a && (a.title + a.text).includes(m[1]); }); };
  /* 다른 규정을 따르라는 조항: 가리킨 규정이 내 규정 묶음에 등록돼 있으면 미등록으로 보지 않는다 */
  const regNames = () => new Set(((AI.regSet() || {}).regs || []).map(r => r.name));
  function mockReg(inp) {
    const q = inp.question, hits = AI.retrieve(q, 3), prev = (inp.history || []).slice(-1)[0];
    if (OUT_HINT.test(q)) return ANS({ kind: 'out', level: 'out' });
    if (isFollow(q, prev)) return mockFollow(q, prev);
    const topic = topicOf(q);
    if (topic) return Object.assign(named(cannedSet()[topic], topic), { retrieved: hits });
    if (HR_TERMS.test(q) && !hrStated(q, hits.map(h => h.id))) return ANS({ kind: 'regulation', level: 'none' });
    const intra = AI.intranetHits(q);
    if (intra.length) return ANS({ source: 'intranet', intranet: intra });
    const amb = AMBIG.find(([re, ok]) => re.test(q) && ok(q));
    if (amb) return ANS({ kind: 'clarify', level: 'clarify', question: '어떤 내용을 물어보신 건지 골라 주세요.', options: amb[2] });
    if (!REG_HINT.test(q)) return mockGeneral(q);
    if (!hits.length) return ANS({ kind: 'regulation', level: 'none' });
    const a = AI.article(hits[0].id), reg = AI.regOf(a.reg) || {}, set = AI.regSet() || {}, have = regNames();
    const refs = uniq((a.text.match(/「([^」]+)」/g) || []).map(x => x.slice(1, -1))).filter(n => !/법$|법률|시행령$/.test(n) && !have.has(n));
    if (/준용/.test(a.text) && refs.length) {
      return ANS({ kind: 'regulation', level: 'missing', summary: `${AI.artName(a)}는 「${refs[0]}」을 따르도록 정하고 있어요. 그 원문이 아직 등록되지 않아 자세한 기준은 확인할 수 없어요.`, apply: `${set.group || ''} 대상으로 등록된 규정에서 찾은 조항이에요.`, more: [`「${refs[0]}」 원문 확인`], basis: hits.map(h => h.id), missing: refs, retrieved: hits });
    }
    const os = reg.overseas ? ' 국외근무 직원 대상 규정이라 국내에서 근무하면 적용되지 않아요.' : '';
    return ANS({ kind: 'regulation', level: 'ok', summary: `${AI.artName(a)}: ${firstSentence(a.text)}`, apply: `${meName()} 님은 ${set.group || ''}이라 「${reg.name || ''}」 조항으로 답했어요.${os} 자세한 내용은 아래 ‘규정 근거 보기’에서 원문을 확인하세요.`, more: ['내 상황에 그대로 적용되는지는 담당 부서에 확인해 주세요.'], basis: hits.map(h => h.id), retrieved: hits });
  }
  const REG_SYS = `너는 GrowPath '사내 생활 도우미'의 규정 에이전트다. 사용자(이름·직원 구분·직급·부서)는 입력의 user에 있다. 사용자에게 적용되는 등록 규정은 user.registeredRegulation(직원 구분·규정 이름 목록)이다. 먼저 질문을 아래 네 유형 중 하나로 분류하고, 그 유형에 맞게만 답한다.
1) kind="regulation": 기관 규정·인사 제도에 관한 질문(교육훈련·복무·근무시간·휴가·휴직·여비·보수·근무성적평정·승진·발령·성과급·전보·징계·퇴직 등).
  · 입력의 articles(사용자에게 적용되는 등록 규정에서 검색된 조항 · regulation은 규정 이름)에 그 내용이 명시된 경우에만 답하고, basis에 근거 조항 id를 넣는다. 문장에 규정 이름과 조 번호를 함께 쓴다(예: 「인재개발규정」 제7조).
  · articles에 관련 내용이 없으면 답을 쓰지 않고 level="none", basis=[]로 둔다. 일반 상식·다른 기관 사례·짐작으로 채우지 않는다.
  · 조항이 등록되지 않은 규정·별표·별지나 '사장이(담당 부서의 장이) 따로 정한다'는 기준으로 넘기면 그 내용은 모른다. 짐작하지 말고 level="unclear"(일부만 확인) 또는 "missing"으로 하고 missing에 그 규정·별표·기준 이름을 넣는다.
  · 조항의 금액·시간·정원·기준을 사용자 개인의 급여·의무로 확정해서 말하지 않는다. 숫자는 조항에 적힌 그대로만 쓴다.
  · 같은 규정 안에 다른 직군(전문직·운영직·특정직 등)이나 국외근무 직원의 내용이 있으면 사용자에게 해당하는 조항만 근거로 쓴다. 국외근무 규정은 사용자가 국외근무를 물을 때만 쓴다.
  · '제가 승진할 수 있나요'처럼 개인의 결과를 묻는 질문은 예측하지 않고, 조항에 적힌 기준만 알려 준다.
  · level: ok(조항으로 답함) / unclear(일부만 확인) / missing(따르라는 규정·별표·기준 미등록) / none(등록된 규정에 관련 내용 없음).
2) kind="general": 업무·사내 생활과 관련 있지만 규정에는 없는 질문. source를 정한다.
  · source="intranet": 식당·통근버스·주차·회의실·복지몰·건강검진·증명서·휴가 신청 화면·IT 지원·교육 신청 창구처럼 사내 홈페이지에서 확인하는 것.
    입력의 intranet(가상 사내 홈페이지 메뉴 안내)에서 맞는 항목 id만 intranet 배열에 넣는다(최대 2개). 식단·시간표·금액·잔액 같은 구체적인 값은 쓰지 않는다. 맞는 항목이 없으면 intranet=[].
  · source="work": 업무 방법·기술 개념·학습 질문. 일반 지식으로 답하되 기관 규정처럼 단정하지 않는다.
  · source="app": GrowPath 사용법(로드맵 수정, 사후 점검 등). 해당 메뉴를 안내한다.
3) kind="out_of_scope": 업무나 사내 생활과 관련 없는 질문(주식·코인 시세, 날씨, 스포츠 경기 결과, 연예, 개인 쇼핑 등). 답을 쓰지 않는다.
4) kind="clarify": 위 유형 중 어디인지 정할 수 없을 만큼 질문이 애매할 때만. question에 되묻는 1문장, options에 사용자가 고를 수 있는 구체적인 질문 2~3개를 쓴다.
- 앞 대화(이전 user·assistant 메시지)가 있으면 이번 질문을 그 대화에 이어지는 질문으로 보고 분류·답변한다. 예: 앞에서 교육비 지원을 물었고 이번에 '그럼 신청은 언제까지?'라고 하면 교육비 지원 신청 기한을 묻는 것이다.
  · 이어지는 질문이어도 규정 근거는 이번 입력의 articles에 있는 조항만 쓴다. 앞 답변에 나온 내용이라도 articles에 없으면 근거로 대지 않는다.
- summary: 답변 요약 1~2문장. apply: 사용자 상황(user의 직원 구분·직급, 진행 중인 로드맵)에 맞춘 설명. user.regulationApplies가 false면 등록된 규정이 사용자에게 적용된다고 쓰지 않는다. more: 추가로 확인할 것 0~3개. 해요체로 쓴다.
JSON 형식: {"kind":"regulation","level":"ok","source":"","summary":"...","apply":"...","more":[],"basis":["dev-7"],"missing":[],"intranet":[],"question":"","options":[]}`;
  /* 앞 대화는 질문과 답(유형·요약·설명·근거 id)만 넘긴다. 앞 질문 때 찾은 조항 원문은 다시 넣지 않고, 이번 검색 결과(articles)에 합친다 */
  const histMsgs = h => h.flatMap(t => [{ role: 'user', content: t.q }, { role: 'assistant', content: JSON.stringify(t.a) }]);
  /* 에이전트에게 넘기는 조항: 규정 이름을 붙이고, 아주 긴 조항은 앞 2,000자만(입력 길이 관리) */
  const ART_MAX = 2000;
  const artIn = a => ({ id: a.id, regulation: (AI.regOf(a.reg) || {}).name || '', no: a.no, title: a.title, chapter: a.chapter, text: a.text.length > ART_MAX ? a.text.slice(0, ART_MAX) + ' …(뒤 생략)' : a.text });
  /* 규정 검색: 임베딩(서버) 또는 키워드(브라우저). 서버에는 내 직원 구분과 국외근무 질문 여부만 넘기고, 서버가 그 규정 묶음 안에서만 찾는다.
     RunPod-Ollama 에 임베딩 모델이 없으면 키워드 검색으로 한다 */
  AI.regSearch = (q, k, signal) => {
    const ollama = AI.mode() === 'ollama', vec = !ollama || !!AI.status.ollama.embedModel;
    if (!vec) return Promise.resolve(AI.retrieve(q, k));
    return post('/api/reg-search', { query: q, k, provider: ollama ? 'ollama' : 'openai', group: (AI.regSet() || {}).group || '', overseas: OVERSEAS.test(q) }, signal).then(r => r.hits);
  };
  /* 지어낸 숫자 막기 (10/15): 답 문장에 나온 숫자(점·년·개월·일·시간·% 등)가 근거 조항 원문에 없으면 모델 문장을 쓰지 않는다 */
  const NUM_RE = /(\d+(?:\.\d+)?)\s*(점|년|개월|일|시간|분|퍼센트|%|만원|원|킬로미터|km|급|회|명)/g;
  /* extra: 입력으로 넘긴 숫자(안의 비용·시간 등)는 조항에 없어도 된다. 천 단위 쉼표는 떼고 비교한다 */
  const numsOk = (txt, basis, extra) => {
    const src = basis.map(id => (AI.article(id) || {}).text || '').join(' ').replace(/\s+/g, '').replace(/(\d),(?=\d{3})/g, '$1'), ok = new Set(extra || []);
    /* 숫자는 앞뒤가 다른 숫자와 붙지 않은 것만 같은 숫자로 본다(예: '90'은 '1990'에 있어도 없는 것) */
    const has = n => new RegExp(`(?<![\\d.])${n.replace('.', '\\.')}(?![\\d])`).test(src);
    return [...String(txt).replace(/(\d),(?=\d{3})/g, '$1').matchAll(NUM_RE)].every(m => ok.has(m[1]) || has(m[1]));
  };
  async function apiReg(inp, signal) {
    /* 이어 묻기는 질문만으로 검색이 안 되므로(예: '그럼 신청은 언제까지?') 앞 질문을 붙인 검색도 한 번 더 하고, 앞 답변의 근거 조항도 함께 넣는다 */
    const prev = inp.history.slice(-1)[0];
    const [alone, joined] = await Promise.all([AI.regSearch(inp.question, 4, signal), prev ? AI.regSearch(`${prev.q} ${inp.question}`, 4, signal) : Promise.resolve([])]);
    const mix = []; for (let i = 0; i < Math.max(alone.length, joined.length); i++) { if (joined[i]) mix.push(joined[i].id); if (alone[i]) mix.push(alone[i].id); }
    const arts = uniq(((prev && prev.a.basis) || []).concat(mix)).map(id => AI.article(id)).filter(Boolean).slice(0, 7);
    const r = await AI.llm(REG_SYS, {
      question: inp.question, user: inp.context, articles: arts.map(artIn),
      intranet: D.intranet.map(x => ({ id: x.id, title: x.title, menu: x.menu, covers: x.covers }))
    }, 'default', null, { history: histMsgs(inp.history), signal });
    const ids = arts.map(a => a.id), list = (v, n) => (Array.isArray(v) ? v : []).map(String).map(x => x.trim()).filter(Boolean).slice(0, n || 3);
    const kind = String(r.kind || '').replace('out_of_scope', 'out');
    /* 범위 밖: 모델이 답을 써 와도 쓰지 않는다 */
    if (kind === 'out') return ANS({ kind: 'out', level: 'out', retrieved: ids });
    if (kind === 'clarify') {
      const options = list(r.options, 3);
      return ANS({ kind: 'clarify', level: 'clarify', question: String(r.question || '').trim() || '어떤 내용을 물어보신 건지 조금 더 알려 주세요.', options, retrieved: ids });
    }
    if (kind === 'general') {
      const source = ['intranet', 'work', 'app'].includes(r.source) ? r.source : 'work';
      /* 사내 생활은 안내 자료의 메뉴만 보여 준다(모델 문장은 쓰지 않음 · 값을 지어내지 않게) */
      if (source === 'intranet') return ANS({ source, intranet: list(r.intranet, 2).filter(id => D.intranet.some(x => x.id === id)), retrieved: ids });
      if (!String(r.summary || '').trim()) throw new Error('답변이 비어 있어요');
      return ANS({ source, summary: String(r.summary), apply: String(r.apply || ''), more: list(r.more), retrieved: ids });
    }
    /* 규정: 등록된 조항에 명시된 경우에만 답한다. 근거 조항이 없거나, 승진·발령·성과급인데 근거 원문에 그 말이 없으면 답하지 않는다 */
    const basis = list(r.basis, 7).filter(id => ids.includes(id));
    const level = ['ok', 'missing', 'unclear'].includes(r.level) ? r.level : 'none';
    if (level === 'none' || !basis.length || !hrStated(inp.question, basis)) return ANS({ kind: 'regulation', level: 'none', retrieved: ids });
    if (!String(r.summary || '').trim()) throw new Error('답변이 비어 있어요');
    /* 근거 조항에 없는 숫자를 쓴 답은 문장을 버리고 원문을 직접 보도록 안내한다(지어내지 않기) */
    if (!numsOk(`${r.summary} ${r.apply || ''}`, basis)) {
      return ANS({ kind: 'regulation', level: 'unclear', summary: '관련 조항은 찾았지만, 답변 문장의 숫자가 조항 원문과 맞지 않아 그대로 보여 드리지 않아요.', apply: '아래 ‘규정 근거 보기’에서 원문을 직접 확인해 주세요.', more: [], basis, missing: [], retrieved: ids, dropped: true });
    }
    return ANS({ kind: 'regulation', level, summary: String(r.summary), apply: String(r.apply || ''), more: list(r.more), basis, missing: level === 'ok' ? [] : list(r.missing), retrieved: ids });
  }
  /* history: 앞 대화 중 답을 받은 질문·답 [{q, a}] (대화 전체 · 10/14 사용자 결정) */
  const meName = () => (GP.me() || {}).name || '사용자';
  /* 규정 질문인데 내 직원 구분에 맞는 등록 규정이 없으면: 다른 직군 조항을 근거로 '적용된다'고 하지 않는다. 찾은 조항은 참고로만 접어 둔다 */
  function scopeAns(a) {
    const me = GP.me() || {}, grp = me.empGroup || '직원 구분이 확인되지 않은 직원', has = Object.keys(AI.REG_SETS).join('·');
    return ANS({ kind: 'regulation', level: 'scope', summary: `등록된 규정은 ${has} 대상이라, ${grp}인 ${me.name || '사용자'} 님에게 적용되는 규정이 아직 없어요.`,
      apply: `${grp}의 인사·복무·교육훈련 기준은 ${grp} 대상 규정을 따르는데, 아직 GrowPath에 등록되지 않아 답할 수 없어요. 인사 담당 부서(인재경영실 · 가상)에 확인해 주세요.`,
      more: [], basis: [], ref: (a.basis || []).slice(0, 3), retrieved: a.retrieved || [] });
  }
  AI.regAnswer = async (question, history, opt) => {
    const a = await AI.run('규정 에이전트', `사내 생활 질문 분류·답변${history && history.length ? ` (앞 대화 ${history.length}턴 포함)` : ''}`, { question, context: AI.regContext(), history: history || [] }, mockReg, apiReg, opt);
    return a.kind === 'regulation' && !AI.regApplies() ? scopeAns(a) : a;
  };

  /* ── 진단 에이전트 · 목표 후보 제안 (4차 묶음 7 · FR-05) ──
     목표를 적기 전에 보여 주는 후보 3개. 사용자 프로필(가상 사내 DB 형식)만 보고 만든다. 목표 칸·기획서는 넣지 않는다(나중 입력에 영향받지 않게).
     본인 입력(업무 설명·경험 요약·기술 스택)이 하나도 없으면 판단 근거가 부족하므로 에이전트를 부르지 않고 AI 활용 업무 기본 후보 3개.
     평정은 학습 사용에 동의한 것만 참고로 넘기고, 평정으로 목표를 정하거나 문장에 쓰지 않게 한다(FR-05 '평정은 선택 참고') */
  /* 로그인한 직원의 프로필(내 정보에서 고친 본인 입력·평정 동의 반영 · 10/15). 시연 도구의 프로필 선택은 없앴다 */
  AI.profileOf = () => GP.me();
  AI.profileEnough = e => !!(e && ((e.profile && (e.profile.workDesc || e.profile.expSummary)) || (e.tech || []).length));
  const G_LABEL = { job: '직무', task: '담당 업무', workDescription: '업무 설명', experience: '경험 요약', techStack: '기술 스택', certifications: '보유 자격', learning: '교육 이력', projects: '프로젝트', evaluations: '평정(학습 사용 동의)' };
  AI.goalInput = e => {
    const p = e.profile || {}, evals = (e.evals || []).filter(x => x.consent).map(x => ({ period: x.period, result: [x.grade, x.score].filter(Boolean).join(', ') }));
    const profile = { grade: e.grade, department: e.dept, parentDepartment: e.parentDept, job: e.job, task: e.task, position: e.position,
      workDescription: p.workDesc || null, experience: p.expSummary || null, developmentYears: p.devYears == null ? null : p.devYears,
      techStack: e.tech || [], certifications: e.certs || [], learning: e.learning || [], projects: e.projects || [], evaluations: evals };
    const used = Object.keys(G_LABEL).filter(k => (Array.isArray(profile[k]) ? profile[k].length : !!profile[k]));
    return { profile, used: ['직급·부서'].concat(used.map(k => G_LABEL[k])), areas: Object.values(D.domains).map(d => d.label) };
  };
  const G_SYS = `너는 GrowPath의 진단 에이전트다. 직원이 목표를 적기 전에, 입력의 profile(가상 사내 DB의 직원 프로필)만 보고 AI 역량 성장 목표 후보 3개를 제안한다.
- 후보는 그 직원의 담당 업무에 AI(생성형 AI·RAG·데이터 분석·업무 자동화 등)를 활용하는 학습 목표다. 직원이 쓴 것처럼 '~하고 싶어요.'로 끝나는 한 문장으로 쓴다.
- 세 후보는 서로 다른 방향이어야 한다. avoid에 있는 목표와 같은 후보는 내지 않는다. 프로필에 없는 업무·경력·자격·프로젝트를 지어내지 않는다.
- why: 프로필의 어떤 내용 때문에 이 후보를 골랐는지 1문장(해요체). basis: 근거로 쓴 항목 이름만(직무, 담당 업무, 업무 설명, 경험 요약, 기술 스택, 보유 자격, 교육 이력, 프로젝트).
- evaluations(근무성적평정)는 본인이 학습 사용에 동의한 것만 들어온다. 목표의 난이도를 가늠하는 참고로만 쓰고, 평정으로 목표를 정하거나 goal·why에 등급·점수·평정을 쓰지 않는다.
- areas는 GrowPath가 로드맵을 만들 수 있는 분야다. 후보는 이 분야와 이어지면 좋다.
- 근거가 부족한 부분이 있으면 note에 1문장으로 적는다(없으면 빈 문자열).
JSON 형식: {"candidates":[{"goal":"...하고 싶어요.","why":"...","basis":["업무 설명"]}],"note":""}`;
  const G_BASIS = ['직무', '담당 업무', '업무 설명', '경험 요약', '기술 스택', '보유 자격', '교육 이력', '프로젝트'];
  /* 평정을 문장에 쓰거나 점수로 목표를 정한 흔적은 버린다 */
  const EVAL_RE = /(평정|\d+\s*\/\s*50|점수|등급|인사평가)/;
  function cleanGoals(list, avoid) {
    const seen = new Set((avoid || []).map(x => x.replace(/\s/g, '')));
    return (Array.isArray(list) ? list : []).map(c => ({ goal: String((c && c.goal) || '').trim(), why: String((c && c.why) || '').trim(), basis: (Array.isArray(c && c.basis) ? c.basis : []).map(String).filter(b => G_BASIS.includes(b)) }))
      .filter(c => c.goal.length >= 8 && c.goal.length <= 160 && !EVAL_RE.test(c.goal) && !seen.has(c.goal.replace(/\s/g, '')) && (seen.add(c.goal.replace(/\s/g, '')) || true))
      .map(c => (EVAL_RE.test(c.why) ? Object.assign(c, { why: '프로필의 업무 내용을 바탕으로 골랐어요.' }) : c)).slice(0, 3);
  }
  async function apiGoals(inp) {
    const r = await AI.llm(G_SYS, { profile: inp.profile, areas: inp.areas, avoid: inp.avoid || [] });
    const candidates = cleanGoals(r.candidates, inp.avoid);
    if (candidates.length < 2) throw new Error('목표 후보가 너무 적어요');
    return { candidates, note: String(r.note || '').trim() };
  }
  /* 가데이터: 프로필 문장에서 업무 단서를 찾아 정해진 후보로 바꾼다(실제 추론 아님) */
  const GOAL_RULES = [
    [/(규정|매뉴얼|문서|검색|근거)/, '사내 규정·매뉴얼 문서에서 근거를 찾아 주는 RAG 검색 도구를 만들고 싶어요.'],
    [/(API|백엔드|FastAPI|서비스)/, '사내 서비스 API에 생성형 AI 기능을 연결하고 응답 품질을 점검하고 싶어요.'],
    [/(데이터|지표|정제|pandas|누락|적재)/, '운영 데이터의 이상값을 AI로 찾아내고 결과를 검증하는 역량을 기르고 싶어요.'],
    [/(로그|장애|배포|서버)/, '운영 로그를 생성형 AI로 요약하고 장애 원인 후보를 찾는 도구를 만들고 싶어요.'],
    [/(화면|UI|React|TypeScript|대시보드|포털)/, '업무 포털 화면에 AI 도우미 기능을 넣고 사용성을 점검하고 싶어요.'],
    [/(인사|엑셀|현황 표|계정)/, '엑셀로 하던 현황 정리를 생성형 AI와 간단한 자동화로 줄이고 싶어요.'],
    [/(Python|파이썬|스크립트)/, 'Python 업무 스크립트에 생성형 AI API를 붙여 반복 작업을 줄이고 싶어요.']
  ];
  function mockGoals(inp) {
    const p = inp.profile, avoid = (inp.avoid || []).map(x => x.replace(/\s/g, ''));
    const fields = [['업무 설명', p.workDescription], ['담당 업무', p.task], ['경험 요약', p.experience], ['기술 스택', p.techStack.join(' ')], ['프로젝트', p.projects.join(' ')], ['직무', p.job]];
    const out = [];
    GOAL_RULES.forEach(([re, goal]) => {
      if (out.length >= 3 || avoid.includes(goal.replace(/\s/g, '')) || out.some(c => c.goal === goal)) return;
      const f = fields.find(([, v]) => v && re.test(v));
      if (f) out.push({ goal, why: `${f[0]}에 ‘${f[1].match(re)[0]}’ 관련 내용이 있어요.`, basis: [f[0]] });
    });
    D.goalDefaults.forEach(x => { if (out.length < 3 && !out.some(c => c.goal === x.goal) && !avoid.includes(x.goal.replace(/\s/g, ''))) out.push({ goal: x.goal, why: '프로필에서 더 구체적인 단서를 찾지 못해 AI 활용 업무 기본 후보를 더했어요.', basis: [] }); });
    const note = !p.techStack.length ? '기술 스택 정보가 없어 난이도는 업무 설명만 보고 가늠했어요.' : '';
    return { candidates: out.slice(0, 3), note };
  }
  AI.goalCandidates = (inp, opt) => AI.run('진단 에이전트', inp.avoid && inp.avoid.length ? '목표 후보 제안 (다른 후보)' : '목표 후보 제안', inp, mockGoals, apiGoals, opt);

  /* 안별 지원 조건 확인 (10/14): 3안이 정해진 뒤 한 번에 묻는다. 근거는 내 직원 구분에 맞는 등록 규정 조항만(웹 검색·일반 상식 금지)
     일반직(10/15)은 「인재개발규정」·「취업규칙」 등 일반직 규정 16건, 실무직은 「실무직 관리규정」 */
  const SUP_QUERY = { 일반직: '위탁교육 교육경비 지급 교육신청 학습시간 인정 개인학습 근무시간 교육출장', 실무직: '교육훈련 교육비 지원 근무시간 학습 인정 복무' };
  const SUP_SYS = `너는 GrowPath '규정 에이전트'다. 로드맵 후보(plans)마다 교육비 지원과 근무시간 중 학습 인정을 받을 수 있는지, 입력의 articles(사용자에게 적용되는 등록 규정에서 찾은 조항 · regulation은 규정 이름)만 근거로 확인한다.
- articles에 쓰인 내용만 근거로 쓴다. 지원 여부·금액·한도·절차·승인 주체를 조항에 없는데 추측하거나 지어내지 않는다.
- 일반 상식, 다른 기관 사례, 인터넷·웹 검색 정보로 답하지 않는다.
- 조항이 등록되지 않은 규정·별표나 '사장이(담당 부서의 장이) 따로 정한다'는 기준으로 넘기면 그 기준은 모른다. level은 unclear 또는 missing으로 하고 missing에 그 규정·별표·기준 이름을 넣는다.
- level: ok(조항으로 확인됨) / unclear(일부만 확인) / missing(관련 자료 미확보). ok나 unclear면 basis에 근거 조항 id를 넣는다.
- summary: 그 안의 유료 자료·비용·자격을 짚어, 무엇을 확인해야 하는지 1~2문장(해요체). 규정 이름과 조 번호를 함께 쓰고, 확인되지 않은 것을 확정처럼 쓰지 않는다.
JSON 형식: {"plans":[{"pid":"A1","level":"unclear","summary":"...","basis":["dev-24"],"missing":["국내 위탁교육 경비 지급기준"]}]}`;
  /* 가데이터: 안의 유료 자료·자격만 보고, 조항에 적힌 사실과 등록되지 않은 기준만 쓴다(지원 여부를 짐작하지 않음) */
  function mockSupportOne(x) {
    const paid = x.paidResources || [], total = paid.reduce((t, r) => t + (r.costWon || 0), 0);
    if ((AI.regSet() || {}).group === '일반직') {
      const head = paid.length
        ? `이 안의 유료 자료 ${paid.length}개(${GP.won(total)})는 외부 교육기관 과정이라 위탁교육(「인재개발규정」 제17조)에 해당하는지 먼저 확인해야 해요. 국내 위탁교육 경비의 지급기준은 사장이 따로 정한다고만 되어 있어(제24조) 지원 여부와 금액은 확인할 수 없어요.`
        : '이 안은 유료 자료 없이 짜여 교육비가 들지 않아요. 개인학습도 학습시간에 포함되지만(「인재개발규정」 제7조 ②), 세부 인정기준은 인재개발담당부서의 장이 따로 정해 근무시간 중 학습 인정은 확인이 필요해요.';
      return { level: 'unclear', summary: head + (x.certification ? ' 자격 응시료 지원은 등록된 조항에서 찾지 못했어요.' : ''), basis: paid.length ? ['dev-17', 'dev-24'] : ['dev-7'], missing: paid.length ? ['국내 위탁교육 경비 지급기준(사장이 따로 정함)'] : ['학습시간 인정기준(인재개발담당부서의 장이 따로 정함)'] };
    }
    const head = paid.length
      ? `이 안의 유료 자료 ${paid.length}개(${GP.won(total)})가 교육비 지원 대상인지는 「인재개발규정」을 따르는데(제35조), 실무직 기준은 확인할 수 없어요.`
      : '이 안은 유료 자료 없이 짜여 교육비가 들지 않아요. 근무시간 중 학습 인정은 「취업규칙」(제15조)·「인재개발규정」(제35조)을 따르는데 실무직 기준은 확인할 수 없어요.';
    return { level: 'missing', summary: head + (x.certification ? ' 자격 응시료 지원도 같은 이유로 확인이 필요해요.' : ''), basis: paid.length ? ['a35'] : ['a15', 'a35'], missing: paid.length ? ['인재개발규정'] : ['취업규칙', '인재개발규정'] };
  }
  const mockSupport = inp => Object.fromEntries(inp.plans.map(x => [x.pid, mockSupportOne(x)]));
  async function apiSupport(inp) {
    const hits = await AI.regSearch(SUP_QUERY[(AI.regSet() || {}).group] || SUP_QUERY.일반직, 6);
    const arts = hits.map(h => AI.article(h.id)).filter(Boolean), ids = arts.map(a => a.id);
    const r = await AI.llm(SUP_SYS, { plans: inp.plans, user: AI.regContext(), articles: arts.map(artIn) });
    const out = {};
    (Array.isArray(r.plans) ? r.plans : []).forEach(x => {
      const pid = String(x.pid || ''); if (!inp.plans.some(p => p.pid === pid)) return;
      const basis = (x.basis || []).map(String).filter(id => ids.includes(id));
      let level = ['ok', 'unclear', 'missing'].includes(x.level) ? x.level : 'missing', summary = String(x.summary || '').trim();
      /* 근거 조항 없이 확인됐다고 하면 믿지 않는다: 모델 문장은 버리고 '관련 자료 미확보'로 낮춘다(근거 없는 내용을 화면에 보이지 않게) */
      if (level !== 'missing' && !basis.length) { level = 'missing'; summary = '등록된 규정에서 이 안의 지원 조건을 뒷받침하는 조항을 찾지 못해 확인할 수 없어요. 담당 부서에 확인해 주세요.'; }
      /* 조항에 없는 숫자(금액·한도 등)를 쓴 문장도 버린다(10/15) */
      else if (basis.length && !numsOk(summary, basis, JSON.stringify(inp.plans.find(q => q.pid === pid) || {}).match(/\d+/g))) { level = 'unclear'; summary = '관련 조항은 찾았지만, 확인 문장의 숫자가 조항 원문과 맞지 않아 그대로 보여 드리지 않아요. 근거 조항 원문을 확인해 주세요.'; }
      if (summary) out[pid] = { level, summary, basis, missing: (x.missing || []).map(String).filter(Boolean).slice(0, 3) };
    });
    if (!Object.keys(out).length) throw new Error('지원 조건 확인 결과가 비어 있어요');
    return out;
  }
  /* 내 직원 구분에 맞는 등록 규정이 없으면 규정 에이전트를 부르지 않고 안마다 '적용 대상 아님'으로 둔다 */
  AI.supportScope = () => {
    const me = GP.me() || {}, grp = me.empGroup || '직원 구분이 확인되지 않은 직원';
    return { level: 'scope', summary: `등록된 규정은 ${Object.keys(AI.REG_SETS).join('·')} 대상이라, ${grp}인 ${me.name || '사용자'} 님의 교육비 지원·근무시간 중 학습 인정은 확인할 수 없어요. ${grp} 대상 규정이 등록되면 확인할 수 있어요.`, basis: [], missing: [] };
  };
  AI.supportCheck = (inp, opt) => (AI.regApplies() ? AI.run('규정 에이전트', '안별 지원 조건 확인', inp, mockSupport, apiSupport, opt)
    : Promise.resolve(Object.fromEntries(inp.plans.map(x => [x.pid, AI.supportScope()]))));
  /* 규정 에이전트가 볼 사용자 상황: 로그인한 직원(직원 구분·직급 · 10/15), 진행 중인 로드맵 전부(여러 개 동시 진행 · 4차 묶음 6)와 작성 중인 안 */
  AI.regContext = () => {
    const P = GP.P, dp = S().draftPlan, set = AI.regSet();
    const plans = P && P.recs ? P.recs('active').map(R => ({ goal: R.plan.goal, name: R.plan.name, weeklyHours: R.plan.hours, costWon: R.plan.cost })) : [];
    const me = GP.me() || {};
    return { name: me.name || null, employeeGroup: me.empGroup || null, grade: me.grade || null, department: me.dept || null, job: me.job || null,
      registeredRegulation: set ? { appliesTo: set.group, regulations: set.regs.filter(r => !r.overseas).map(r => r.name), overseasOnly: set.regs.filter(r => r.overseas).map(r => r.name) } : { appliesTo: Object.keys(AI.REG_SETS), regulations: [] },
      regulationApplies: AI.regApplies(),
      plans, drafting: dp ? { name: dp.name, weeklyHours: dp.hours, costWon: dp.cost } : null };
  };

  /* 진단 에이전트 · 결과 보고서 문장. 사전→사후 응답이 오른 것 / 그대로이거나 내려간 것으로 나눈다 */
  function mockReport(inp) {
    const gained = inp.items.filter(x => AI.rose(x.pre, x.post)), still = inp.items.filter(x => !AI.rose(x.pre, x.post));
    const good = [], improve = [];
    if (gained.length) good.push(`응답이 오른 것: ${gained.slice(0, 3).map(x => x.skill).join(', ')}.`);
    if (inp.doneTitles.length && inp.doneTitles.length >= inp.total - 1) good.push('계획한 활동을 거의 모두 완료로 기록했어요.');
    else if (inp.doneTitles.length) good.push(`「${inp.doneTitles[0]}」 등 활동을 완료로 기록했어요.`);
    if (still.length) improve.push(`응답이 그대로이거나 내려간 것: ${still.slice(0, 3).map(x => x.skill).join(', ')}. 필요하면 다음 계획에서 다시 다뤄 보세요.`);
    if (inp.restTitles.length) improve.push('아직 진행 중인 활동이 있어요. 완료로 기록하지 않았다고 해서 하지 않은 것으로 보지는 않아요.');
    if (!improve.length) improve.push('업무에 적용하며 어려웠던 점을 다음 목표에 반영해 보세요.');
    const next = inp.domain === 'rag' && inp.opt === 'A3'
      ? { goal: '만든 시제품을 부서 실제 질문 20건에 적용하고 답변 품질을 점검하고 싶어요.', why: '시제품을 만들었으니 실제 질문으로 품질을 확인하는 단계로 넘어가요.' }
      : { goal: '사내 규정 문서로 근거 조항을 보여주는 질의응답 시제품을 만들고 싶어요.', why: '핵심을 익혔으니 업무 문서에 적용하는 단계로 넘어가요.' };
    return { good, improve, next };
  }
  const REP_SYS = `너는 GrowPath '진단 에이전트'다. 사전·사후 점검 응답(5점 척도: 1 전혀 아님 ~ 5 매우 그렇다) 변화와 실행 기록으로 결과 보고서 문장을 쓴다.
- 잘된 점은 응답이 오른 문항을, 보완할 점은 응답이 그대로이거나 내려간 문항을 중심으로 쓴다.
- 점수, 개수, 비율 같은 숫자는 쓰지 않는다. 자기보고이며 실제 역량 판정이나 인사평가가 아님을 전제로 쓴다. 해요체.
JSON 형식: {"good":["잘된 점"],"improve":["보완할 점"],"next":{"goal":"다음 로드맵 목표 한 문장","why":"이유 한 문장"}}`;
  async function apiReport(inp) {
    const r = await AI.llm(REP_SYS, { goal: inp.goal, plan: inp.planName, items: inp.items.map(x => ({ area: x.area, question: x.text, before: ans(x.pre), after: ans(x.post) })), completed: inp.doneTitles, notCompleted: inp.restTitles, goalSelf: inp.goalSelf });
    const arr = v => (Array.isArray(v) ? v.map(String).filter(Boolean).slice(0, 4) : []);
    /* 빈 항목을 가데이터 문장으로 채우지 않는다(10/14) */
    const out = { good: arr(r.good), improve: arr(r.improve), next: r.next && String(r.next.goal || '').trim() ? { goal: String(r.next.goal), why: String(r.next.why || '') } : null };
    if (!out.good.length || !out.improve.length || !out.next) throw new Error('보고서 문장이 비어 있어요');
    return out;
  }
  AI.diagReport = (inp, opt) => AI.run('진단 에이전트', '결과 보고서 작성', inp, mockReport, apiReport, opt);

  /* 시연 단계 이동에서 바로 쓰는 가데이터 함수 */
  AI.mock = { questions: mockQuestions, assess: mockAssess, option: mockOption, reg: mockReg, report: mockReport,
    /* 시연 단계 이동용: 안 하나의 지원 조건 */
    support: (pid, o) => (!AI.regApplies() ? AI.supportScope() : mockSupportOne({ pid, paidResources: [...new Set(o.acts.filter(a => a.res && D.res[a.res].cost > 0).map(a => a.res))].map(id => ({ title: D.res[id].title, costWon: D.res[id].cost })), certification: o.acts.some(a => a.res && D.res[a.res].kind === '자격') })) };
})();

/* GrowPath 5차 목업 (Claude) · 사내 생활 도우미 (우측 하단 · API-09)
   서버의 규정 에이전트가 LLM 지시문으로 질문을 분류해 유형에 맞게만 답한다(4차 묶음 7 · NFR-01, 별도 분류 모델 없음).
     규정 질문 → 내 직원 구분의 팀 DB 규정(RAG · 조·항·별표 청크) 근거 조항과 함께(규정에 없으면 답하지 않고 담당 부서 안내)
              직원 구분별 규정 묶음은 서버가 정한다(/regulations/sets). 맞는 규정 묶음이 없는 직원 구분이면 '적용 대상 아님'
     일반 질문 → 사내 생활은 가상 사내 홈페이지 메뉴 안내, 업무·학습은 일반 답변, 앱 사용법은 메뉴 안내
     범위 밖(주식·날씨·스포츠 등) → 답하지 않음 · 애매하면 되묻기
   로드맵 계획 에이전트가 확인한 지원 조건도 같은 규정 에이전트가 답한다.
   4차 묶음 5 (10/14 사용자 결정)
   · 이어 묻기: 답을 받은 앞 대화 전체를 에이전트에 넘긴다
   · 기록: 탭을 닫을 때까지 남는다(sessionStorage). 새로 고쳐도, 화면을 옮겨도 이어진다. '새 대화'로 지운다
   · 답을 쓰는 동안: 입력창은 그대로 쓸 수 있고 보내기 자리에 '멈추기'가 나온다. 써 둔 질문은 지우지 않는다 */
(function () {
  'use strict';
  const GP = window.GP, D = GP.D, AI = GP.AI, P = GP.P, API = GP.API, { esc, icon } = GP;
  /* 내 규정 묶음 이름(예: '일반직 규정 18건') · 조항의 규정 이름과 개정 차수 */
  const setLabel = () => (AI.regSet() || {}).label || '규정';
  const regOfArt = a => AI.regOf(a.reg) || {};
  const artHead = (a, lead) => `${lead ? `${lead} · ` : ''}「${esc(regOfArt(a).name || '')}」 ${a.no}(${esc(a.title)})${a.chapter ? ` · ${esc(a.chapter)}` : ''}`;
  /* 출처 줄: 근거 조항이 나온 규정마다 이름 · 개정 차수 · 원문 쪽 */
  const srcLine = arts => {
    const by = new Map(); arts.forEach(a => { const k = a.reg; if (!by.has(k)) by.set(k, []); by.get(k).push(a.page); });
    return [...by.entries()].map(([k, pages]) => { const r = AI.regOf(k) || {}; return `「${esc(r.name || '')}」 ${esc(r.rev || '')}${r.effective ? ` · 시행 ${esc(r.effective)}` : ''} · 원문 ${[...new Set(pages)].join('·')}쪽`; }).join(' / ');
  };
  const missName = m => esc(AI.missLabel(m));
  const LV = { ok: ['근거 확인', 'acc'], missing: ['관련 자료 미확보', 'warn'], unclear: ['일부만 확인', 'warn'] };
  const SUGS = ['교육비 지원을 받을 수 있나요?', '통근버스 시간표는 어디서 봐요?', '승진 기준이 궁금해요', '근무성적평정은 언제 하나요?', 'RAG가 뭐예요?', '로드맵 기간을 바꾸고 싶어요'];
  /* 대화가 이만큼 길어지면 '새 대화'를 권한다(넘기는 양은 줄이지 않음) */
  const LONG_TURNS = 10;

  /* ── 탭 동안만 보관 (sessionStorage) ──
     말풍선: {me, t} 내 질문 · {q, a} 답 · {q, wait} 답 쓰는 중 · {q, fail} 실패 · {q, stop, cut} 멈춤(cut: 새로 고쳐 끊김) */
  const LOG_KEY = 'gp5c.reglog', DRAFT_KEY = 'gp5c.regdraft', OPEN_KEY = 'gp5c.regopen';
  const ss = {
    get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* 저장 불가 환경은 메모리만 */ } },
    del(k) { try { sessionStorage.removeItem(k); } catch (e) { /* 저장 불가 환경 */ } }
  };
  let log = null;
  /* 답을 쓰는 중에 새로 고쳤으면 그 답은 '끊김'으로 바꾼다. 다시 보내지 않는다(다시 시도는 사용자가 누를 때만) */
  function load() {
    try {
      const v = JSON.parse(ss.get(LOG_KEY) || '[]');
      return Array.isArray(v) ? v.filter(Boolean).map(m => (m.wait ? { q: m.q, stop: true, cut: true } : m)) : [];
    } catch (e) { return []; }
  }
  const L = () => log || (log = load());
  const keep = () => ss.set(LOG_KEY, JSON.stringify(L()));
  /* 지금 답을 쓰는 중인 말풍선 {i, ctrl} */
  let run = null;

  const list = (h, arr) => (arr && arr.length ? `<h4>${h}</h4><ul>${arr.map(m => `<li>${esc(m)}</li>`).join('')}</ul>` : '');
  /* 일반 답변 카드: 규정 근거 없이 요약 → 설명 → 더 볼 것 → 바로 가기 */
  function generalCard(a) {
    const links = (a.links || []).map(([r, l]) => `<button class="link" data-go="${r}">${esc(l)} ${icon('right')}</button>`).join(' ');
    return `<div class="ans">
      <div class="who">${icon('chat')}사내 생활 도우미 <span class="tag">${a.source === 'app' ? '사용법 안내' : '일반 답변'}</span></div>
      <h4>답변 요약</h4><p class="sum">${esc(a.summary)}</p>
      ${a.apply ? `<p>${esc(a.apply)}</p>` : ''}${list('더 알아볼 것', a.more)}
      ${links ? `<p class="go">${links}</p>` : ''}
      <p class="src">규정 근거가 아닌 일반 답변이에요. 기관 기준이 필요한 내용은 담당 부서에 확인해 주세요.</p>
    </div>`;
  }

  /* 범위 밖: 업무·사내 생활과 관련 없는 질문에는 답하지 않는다 */
  const outCard = () => `<div class="ans">
      <div class="who">${icon('chat')}사내 생활 도우미 <span class="tag line">범위 밖</span></div>
      <p class="sum">업무·사내 생활과 관련 없는 질문이라 답하지 않아요.</p>
      <p class="small muted">규정, 사내 생활(사내 홈페이지 안내), 업무·학습, GrowPath 사용법에 대해 물어봐 주세요.</p></div>`;
  /* 규정 주제인데 등록된 규정에 명시된 내용이 없음: 답하지 않고 담당 부서 안내(승진·발령·성과급 등) */
  const noneCard = a => `<div class="ans">
      <div class="who">${icon('scale')}규정 에이전트 <span class="tag warn">등록된 규정에서 확인 불가</span></div>
      <p class="sum">${a && a.summary ? esc(a.summary) : `등록된 ${esc(setLabel())}에 이 내용이 명시돼 있지 않아 답하지 않아요.`}</p>
      <p>인사 제도에 관한 내용은 인사 담당 부서(인재경영실 · 가상)에 문의해 주세요.</p>
      <p class="src">등록된 규정 원문에 있는 내용에만 답해요. 짐작이나 다른 기관 사례로 답하지 않아요.</p></div>`;
  /* 적용 대상 아님 (10/15): 내 직원 구분에 맞는 등록 규정이 없으면 다른 직군 조항으로 답하지 않는다. 찾은 조항은 참고로만 접어 둔다 */
  function scopeCard(a) {
    const refs = (a.ref || []).map(id => AI.article(id)).filter(Boolean);
    return `<div class="ans">
      <div class="who">${icon('scale')}규정 에이전트 <span class="tag warn">적용 대상 아님</span></div>
      <h4>답변 요약</h4><p class="sum">${esc(a.summary)}</p>
      ${a.apply ? `<p>${esc(a.apply)}</p>` : ''}
      ${refs.length ? `<details><summary>${icon('right')}참고로 찾은 조항 (적용 대상 아님)</summary><div class="basis">
        ${refs.map(x => `<div class="art"><b>${artHead(x)}</b>${esc(x.text)}</div>`).join('')}
        <p class="src">${srcLine(refs)}</p></div></details>` : ''}
      <p class="src">등록된 규정의 적용 대상이 아닌 직원에게는 그 규정으로 답하지 않아요.</p></div>`;
  }
  /* 받침에 맞는 조사 (은/는) */
  const eun = w => { const c = String(w).charCodeAt(String(w).length - 1); return c >= 0xAC00 && c <= 0xD7A3 ? ((c - 0xAC00) % 28 ? '은' : '는') : '은(는)'; };
  /* 사내 생활: 가상 사내 홈페이지 메뉴 안내만 보여 준다(구체적인 값은 지어내지 않음) */
  function intraCard(a) {
    const items = (a.intranet || []).map(id => D.intranet.find(x => x.id === id)).filter(Boolean);
    return `<div class="ans">
      <div class="who">${icon('chat')}사내 생활 도우미 <span class="tag">사내 생활 안내</span></div>
      ${items.length ? `<h4>답변 요약</h4><p class="sum">${esc(items[0].title)}${eun(items[0].title)} 사내 홈페이지(가상) › ${esc(items[0].menu)}에서 확인할 수 있어요.</p>
        <ul class="intra">${items.map(x => `<li><b>${esc(x.menu)}</b><span>${esc(x.covers)}</span><small>문의 · ${esc(x.dept)}</small></li>`).join('')}</ul>`
        : '<p class="sum">사내 홈페이지(가상) 안내 자료에서 맞는 메뉴를 찾지 못했어요.</p><p>공지사항을 확인하거나 담당 부서에 문의해 주세요.</p>'}
      <p class="src">가상 사내 홈페이지의 메뉴 안내예요. 식단·시간표·금액 같은 실제 내용은 사내 홈페이지에서 확인해 주세요.</p></div>`;
  }
  /* 되묻기: 어떤 질문인지 갈릴 때 고를 수 있는 질문을 보여 준다. 누르면 그 질문을 보낸다 */
  const clarifyCard = a => `<div class="ans">
      <div class="who">${icon('chat')}사내 생활 도우미 <span class="tag">확인 필요</span></div>
      <p class="sum">${esc(a.question)}</p>
      ${a.options && a.options.length ? `<div class="clar">${a.options.map(o => `<button class="chip" data-act="reg-pick" data-arg="${esc(o)}">${esc(o)}</button>`).join('')}</div>` : ''}
      <p class="small muted">아니면 조금 더 구체적으로 적어 주세요.</p></div>`;

  /* 규정 답변 카드: 요약 → 내 상황 → 추가 확인 → (펼침) 규정 근거 */
  P.regCard = function (a, from) {
    if (a.kind === 'out') return outCard();
    if (a.kind === 'clarify') return clarifyCard(a);
    if (a.kind === 'regulation' && a.level === 'scope') return scopeCard(a);
    if (a.kind === 'regulation' && a.level === 'none') return noneCard(a);
    if (a.kind === 'general' && a.source === 'intranet') return intraCard(a);
    if (a.kind === 'general' || a.inScope === false) return generalCard(a);
    const [lvT, lvC] = LV[a.level] || LV.unclear;
    const arts = (a.basis || []).map(id => AI.article(id)).filter(Boolean);
    /* 실무직 관리규정 제3조(다른 규정과의 관계)는 근거에 있으면 '기본 원칙'으로 표시한다 */
    const base = arts.find(x => x.no === '제3조' && regOfArt(x).name === '실무직 관리규정') || null;
    return `<div class="ans">
      <div class="who">${icon('scale')}${from ? `${esc(from)} → ` : ''}규정 에이전트 <span class="tag ${lvC}">${lvT}</span></div>
      <h4>답변 요약</h4><p class="sum">${esc(a.summary)}</p>
      ${a.apply ? `<h4>내 상황에 적용</h4><p>${esc(a.apply)}</p>` : ''}
      ${list('추가로 확인할 것', a.more)}
      ${arts.length ? `<details><summary>${icon('right')}규정 근거 보기</summary><div class="basis">
        ${arts.map(x => `<div class="art"><b>${artHead(x, base && x.id === base.id ? '기본 원칙' : '')}</b>${esc(x.text)}</div>`).join('')}
        ${a.missing && a.missing.length ? `<div class="art"><b>등록되지 않은 기준</b>${a.missing.map(missName).join(', ')} — 원문·별표가 등록되지 않아 내용은 답할 수 없어요.</div>` : ''}
        <p class="src">${esc((AI.regSet() || {}).org || '한국수자원공사')} ${srcLine(arts)}</p>
      </div></details>` : ''}
    </div>`;
  };

  /* 답변 실패 (10/14): 가데이터로 대신하지 않고 실패 말풍선을 보여 준다. '다시 시도'를 눌러야만 같은 질문을 다시 보낸다 */
  const failCard = (m, i) => `<div class="ans fail">
      <div class="who">${icon('alert')}사내 생활 도우미 <span class="tag fail">답변 실패</span></div>
      <p class="sum">답변을 받지 못했어요.</p><p>${esc(P.errText(m.fail))}</p>
      ${P.opsBox([['', m.fail]])}
      <p class="go"><button class="btn line sm" data-act="reg-retry" data-arg="${i}">${icon('retry')}다시 시도</button></p></div>`;
  /* 멈춘 답: 사용자가 '멈추기'를 눌렀거나, 답을 쓰는 중에 새로 고쳐 끊긴 경우 */
  const stopCard = (m, i) => `<div class="ans stop">
      <p class="sum">${m.cut ? '답을 받는 중에 페이지를 새로 고쳐 답이 끊겼어요.' : '답변을 멈췄어요.'}</p>
      <p class="go"><button class="btn line sm" data-act="reg-retry" data-arg="${i}">${icon('retry')}다시 시도</button></p></div>`;
  const waitCard = () => `<div class="plain muted wait">${AI.live() ? '답을 쓰고 있어요. 규정 질문이면 원문도 찾아볼게요…' : '답변을 찾고 있어요…'}</div>`;
  const intro = () => `<div class="msg bot"><div class="plain">업무·학습·사내 생활에 대해 물어보세요. 교육 지원·근무시간·보수처럼 규정에 관한 질문은 등록된 원문의 근거 조항과 함께, 식당·통근버스·복지몰 같은 사내 생활은 사내 홈페이지(가상) 메뉴로 안내해 드려요. 업무와 관계없는 질문(주식·날씨·스포츠 등)에는 답하지 않아요. 앞 이야기에 이어서 물어봐도 돼요.</div></div>`;
  const bubble = (m, i) => (m.me ? `<div class="msg me">${esc(m.t)}</div>`
    : `<div class="msg bot">${m.a ? P.regCard(m.a) : m.fail ? failCard(m, i) : m.stop ? stopCard(m, i) : waitCard()}</div>`);
  const turns = () => L().filter(m => m.a).length;

  function paint() {
    const b = document.getElementById('regLog'); if (!b) return;
    b.innerHTML = intro() + L().map(bubble).join('');
    b.scrollTop = b.scrollHeight;
    const long = document.getElementById('regLong'); if (long) long.hidden = turns() < LONG_TURNS;
  }
  /* 답을 쓰는 동안: 보내기 → 멈추기, 추천 질문은 잠깐 쉼. 입력창은 계속 쓸 수 있다 */
  function busyUI() {
    const on = !!run, send = document.getElementById('regSend'), stop = document.getElementById('regStop');
    if (!send) return;
    send.hidden = on; stop.hidden = !on;
    document.querySelectorAll('#regPanel .sugs .chip').forEach(c => { c.disabled = on; });
    if (!on) hint('');
  }
  /* 안내 줄이 생기면 대화 칸이 줄어드니, 마지막 말풍선이 가려지지 않게 아래로 맞춘다 */
  function hint(t) {
    const h = document.getElementById('regHint'); if (!h) return;
    h.textContent = t; h.hidden = !t;
    const b = document.getElementById('regLog'); if (b) b.scrollTop = b.scrollHeight;
  }

  /* 이 말풍선(i) 앞까지 답을 받은 질문·답만 넘긴다. 실패·멈춘 질문은 답이 없어 넘기지 않는다 */
  const brief = a => ({ kind: a.kind, level: a.level, source: a.source || '', summary: a.summary, apply: a.apply, more: a.more || [], basis: a.basis || [], missing: a.missing || [], intranet: a.intranet || [], question: a.question || '', options: a.options || [] });
  const historyBefore = i => L().slice(0, i).filter(m => m.a && m.a.kind !== 'out').map(m => ({ q: m.q, a: brief(m.a) }));

  /* i 번째 말풍선 자리에 답을 채운다 (다시 시도하면 그 자리에 그대로).
     서버 작업으로 묻고(202 jobId) 끝날 때까지 기다린다. 멈추면 기다리기를 그만두고 서버 작업도 멈춘다 */
  async function answer(q, i) {
    const ctrl = new AbortController();
    run = { i, ctrl, job: null }; L()[i] = { q, wait: true }; keep(); paint(); busyUI();
    let a = null, err = null;
    try {
      const j = await API.call('POST', '/assistant/ask', { question: q, history: historyBefore(i) }, { async: true, wait: false, signal: ctrl.signal });
      if (run && run.ctrl === ctrl) run.job = j.jobId;
      const out = await API.job(j.jobId, { signal: ctrl.signal });
      AI.mergeReg(out.reg); a = out.answer;
      AI.noteResult(null, out.meta);
    } catch (e) { err = e; if (e && e.name !== 'AbortError') AI.noteResult(AI.cause(e)); }
    /* 멈췄거나 새 대화를 시작했으면 늦게 온 답은 버린다 */
    if (ctrl.signal.aborted || !run || run.ctrl !== ctrl) return;
    run = null;
    L()[i] = err ? { q, fail: AI.cause(err) } : { q, a };
    keep(); paint(); busyUI();
    const p = document.getElementById('regPanel'), f = document.getElementById('regFab');
    if (p && p.hidden && f) f.classList.add('new');
  }
  /* 보내기. 답을 쓰는 중이면 보내지 않고 입력창에 남겨 둔다(지우지 않음) */
  function ask(q) {
    q = String(q || '').trim(); if (!q) return false;
    if (run) { hint('지금 앞 질문의 답을 쓰고 있어요. 다 쓰면 보낼 수 있어요. 멈추려면 ■를 누르세요.'); return false; }
    L().push({ me: true, t: q }); L().push({ q, wait: true });
    answer(q, L().length - 1);
    return true;
  }
  function stop() {
    if (!run) return;
    const { i, ctrl, job } = run; run = null; ctrl.abort();
    if (job) API.cancelJob(job).catch(() => {});
    const m = L()[i]; if (m) L()[i] = { q: m.q, stop: true };
    keep(); paint(); busyUI();
  }
  function setInput(v) { const i = document.getElementById('regIn'); if (!i) return; i.value = v; ss.set(DRAFT_KEY, v); }

  function ensure() {
    if (document.getElementById('regFab')) return;
    document.body.insertAdjacentHTML('beforeend', `
      <button class="fab" id="regFab" data-act="reg-open" aria-label="사내 생활 도우미 열기">${icon('chat')}<span>사내 생활 도우미</span></button>
      <section class="regp" id="regPanel" hidden aria-label="사내 생활 도우미">
        <div class="sheet-h"><span class="avatar">${icon('chat')}</span><div><b>사내 생활 도우미</b><small id="regSub">업무·사내 생활 질문에 답해요 · 규정 질문은 등록된 규정 원문에서 근거를 찾아요</small></div>
          <button class="btn ghost sm reg-new" data-act="reg-new" title="지금 대화를 지우고 새로 시작">${icon('plus')}새 대화</button>
          <button class="x" data-act="reg-close" aria-label="닫기">${icon('x')}</button></div>
        <div class="reg-confirm" id="regConfirm" hidden role="alert"><p>지금 대화를 지우고 새로 시작할까요? 지운 대화는 다시 볼 수 없어요.</p>
          <div><button class="btn line sm" data-act="reg-new-no">취소</button><button class="btn pri sm" data-act="reg-new-ok">새로 시작</button></div></div>
        <div class="chat-b" id="regLog" aria-live="polite"></div>
        <div class="chat-f"><p class="reg-long" id="regLong" hidden>대화가 길어졌어요. 앞 대화를 모두 함께 보내서 답이 느려질 수 있고, 모델에 따라 앞부분을 놓칠 수 있어요. 주제가 바뀌었다면 ‘새 대화’로 시작해 보세요.</p>
          <div class="sugs">${SUGS.map(s => `<button class="chip" data-act="reg-sug">${esc(s)}</button>`).join('')}</div>
          <form class="chat-in" id="regForm"><input class="input" id="regIn" placeholder="업무·사내 생활에 대해 물어보세요" autocomplete="off" aria-label="질문">
            <button class="btn pri" id="regSend" aria-label="보내기">${icon('send')}</button>
            <button type="button" class="btn line stop" id="regStop" data-act="reg-stop" aria-label="답변 멈추기" title="답변 멈추기" hidden>${icon('stop')}</button></form>
          <p class="reg-hint" id="regHint" role="status" hidden></p></div>
      </section>`);
    const inp = document.getElementById('regIn');
    inp.value = ss.get(DRAFT_KEY) || '';
    inp.addEventListener('input', () => ss.set(DRAFT_KEY, inp.value));
    document.getElementById('regForm').addEventListener('submit', e => { e.preventDefault(); if (ask(inp.value)) setInput(''); });
    if (ss.get(OPEN_KEY) === '1' && fabAllowed()) open(true);
  }
  function open(silent) {
    ensure();
    const p = document.getElementById('regPanel'), f = document.getElementById('regFab');
    p.hidden = false; f.hidden = true; f.classList.remove('new'); ss.set(OPEN_KEY, '1');
    paint(); busyUI();
    if (!silent) setTimeout(() => { const i = document.getElementById('regIn'); if (i) i.focus(); }, 30);
  }
  /* 우측 하단 버튼: 로그인한 뒤 모든 화면에 보인다(10/15: 부서장도 직원이라 부서장 화면에서도 쓴다) */
  const fabAllowed = () => !!GP.me();
  function close() {
    const p = document.getElementById('regPanel'); if (p) p.hidden = true;
    const f = document.getElementById('regFab'); if (f) f.hidden = !fabAllowed();
    ss.set(OPEN_KEY, '0');
  }
  /* 대화 지우기: 쓰는 중인 답은 멈추고, 입력창에 써 둔 글은 남긴다 */
  function clearLog() {
    if (run) { run.ctrl.abort(); if (run.job) API.cancelJob(run.job).catch(() => {}); run = null; }
    log = []; keep(); paint(); busyUI();
  }

  GP.act['reg-open'] = () => open();
  GP.act['reg-close'] = close;
  GP.act['reg-sug'] = (a, el) => { if (!run) ask(el.textContent); };
  /* 되묻기에서 고른 질문을 보낸다(답을 쓰는 중이면 입력창에 넣어 둠) */
  GP.act['reg-pick'] = q => { if (!run) { ask(q); return; } const i = document.getElementById('regIn'); if (i && !i.value.trim()) setInput(q); hint('앞 질문의 답을 쓰는 중이에요. 다 쓰면 보내 주세요.'); };
  GP.act['reg-stop'] = stop;
  GP.act['reg-retry'] = i => {
    const m = L()[+i]; if (!m || !(m.fail || m.stop)) return;
    if (run) { hint('지금 다른 질문의 답을 쓰고 있어요. 다 쓴 뒤에 다시 시도해 주세요.'); return; }
    answer(m.q, +i);
  };
  /* 다른 화면의 '도우미에게 묻기': 답을 쓰는 중이면 보내지 않고 입력창에 넣어 둔다(써 둔 글이 있으면 그대로 둠) */
  GP.act['reg-ask'] = q => {
    open();
    if (!run) { ask(q); return; }
    const i = document.getElementById('regIn');
    if (i && !i.value.trim()) { setInput(q); hint('앞 질문의 답을 쓰는 중이라 질문을 입력창에 넣어 뒀어요. 다 쓰면 보내 주세요.'); }
    else hint('앞 질문의 답을 쓰는 중이에요. 입력 중인 글은 그대로 뒀어요.');
  };
  GP.act['reg-new'] = () => {
    if (!L().length) { GP.toast('이미 새 대화예요'); return; }
    document.getElementById('regConfirm').hidden = false;
  };
  GP.act['reg-new-no'] = () => { document.getElementById('regConfirm').hidden = true; };
  GP.act['reg-new-ok'] = () => {
    document.getElementById('regConfirm').hidden = true; clearLog();
    GP.toast('새 대화를 시작했어요');
    const i = document.getElementById('regIn'); if (i) i.focus();
  };
  /* 시연 데이터 초기화·단계 이동·로그아웃: 다른 사람·다른 상황의 대화가 남지 않게 지운다 */
  const prevReset = GP.onDataReset;
  GP.onDataReset = function () { if (prevReset) prevReset(); clearLog(); setInput(''); close(); };

  /* 화면마다 보이기: 로그인한 뒤 모든 화면. 로그인 화면에는 보이지 않는다 */
  const prev = GP.onRender;
  GP.onRender = function (sc, id) {
    if (prev) prev(sc, id);
    ensure();
    const hide = !fabAllowed();
    document.getElementById('regFab').hidden = !fabAllowed() || !document.getElementById('regPanel').hidden;
    if (hide) document.getElementById('regPanel').hidden = true;
  };
})();

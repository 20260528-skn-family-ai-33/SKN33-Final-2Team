/* GrowPath 5차 목업 (Claude) · 관리자 화면 (2026-10-21 사용자 요구 2)
   관리자 전용 계정으로 로그인하면 이 화면만 보인다. 인적 데이터(직원·인사이동·부서장 권한)·규정 데이터(도우미 RAG)·교육 데이터(도서·강좌·자격증)를
   SQL·DBMS 없이 관리한다. 한 건은 표에서 행을 골라 오른쪽 패널에서 고치고(저장 전 확인 창 한 번 · 2026-10-22 사용자 결정),
   여러 건은 엑셀·CSV로: 내려받기 → 고치기 → 올리기 → 미리보기(행마다 추가·변경·삭제·오류) → 반영.
   어느 쪽이든 서버가 같은 규칙으로 검사하고, 오류가 하나라도 있으면 저장하지 않는다. 관리자는 직원 기록(로드맵·보고서)을 보지 않는다 */
(function () {
  'use strict';
  const GP = window.GP, API = GP.API, AI = GP.AI, { esc, icon } = GP;
  const S = () => GP.S;
  const ADM = API.admin;
  const DS = {
    hr: { title: '인적 데이터', icon: 'users', lead: '부서·직원·근무성적평정. 인사이동은 직원의 ‘부서 코드’를, 부서장 권한은 ‘부서장’을 고쳐요. 직원은 지우지 않고 퇴직 처리해요.', sheets: ['직원', '부서', '평정'] },
    regulations: { title: '규정 데이터', icon: 'scale', lead: '사내 생활 도우미와 지원 조건 확인이 근거로 쓰는 규정과 조항(RAG 검색 단위). 조항을 고치면 그 규정은 새 버전으로 저장되고 이전 버전은 남아요.', sheets: ['규정', '조항'] },
    education: { title: '교육 데이터', icon: 'book', lead: '로드맵 추천에 쓰는 강좌·도서·자격증. 학습 형식·시간·단계·비용은 팀 DB에 없어 규칙으로 채운 ‘추정’ 값이 있고, 고치면 추정 표시가 빠져요.', sheets: ['강좌', '도서', '자격증'] }
  };
  const ACT = { add: ['추가', 'acc'], update: ['변경', 'line'], delete: ['삭제', 'warn'], error: ['오류', 'fail'], skip: ['건너뜀', 'line'], same: ['그대로', 'line'] };
  const UP_ST = { previewed: ['미리보기', 'line'], applied: ['반영함', 'ok'], rejected: ['취소함', 'line'], expired: ['시간 지남', 'line'] };
  const st = { tab: {}, q: {}, page: {}, cache: {}, overview: null, previews: {}, filter: 'all', history: null, busy: false, edit: null, pending: null, bulk: false };
  const PAGE = 50;

  /* ── 좌측 메뉴 ── */
  function sidebar(active) {
    const a = GP.ACCOUNT.admin || {};
    const link = (r, l, ic, key) => `<a href="#${r}" data-go="${r}" class="${active === (key || r) ? 'on' : ''}">${icon(ic)}${l}</a>`;
    return `<div class="brand"><span class="logo">${icon('logo')}</span>GrowPath</div>
      <div class="me adm"><span class="avatar">관</span><div class="grow"><b>${esc(a.name || '관리자')}</b><small>관리자 전용 계정 · 데이터 관리</small></div></div>
      <nav class="nav" aria-label="관리자 메뉴">${link('admin', '개요', 'db')}${link('admin-ds:hr', DS.hr.title, 'users', 'hr')}${link('admin-ds:regulations', DS.regulations.title, 'scale', 'regulations')}${link('admin-ds:education', DS.education.title, 'book', 'education')}${link('admin-history', '변경 이력', 'history')}</nav>
      <div class="side-foot">
        <div><div class="foot-lbl">테마 색상</div><div class="theme" role="group" aria-label="테마 색상">${GP.THEMES.map(([k, n, c]) => `<button style="background:${c}" class="${GP.theme === k ? 'on' : ''}" data-act="theme" data-arg="${k}" title="${n}" aria-label="${n}"></button>`).join('')}</div></div>
        <button class="btn ghost sm logout" data-act="logout" aria-label="로그아웃">${icon('logout')}<span class="lbl">로그아웃</span></button>
      </div>`;
  }

  const page = o => GP.P.page(o);
  const note = t => GP.P.note(t);
  const loading = t => GP.P.loading(t);
  const failBox = (err, what) => `<div class="callout soft" role="alert">${icon('alert')}<div><b>${esc(what)}</b><br><span class="small">${esc(AI.cause(err).user)}</span>${GP.P.opsBox([['', AI.cause(err)]], 'sm')}</div></div>`;
  const num = (l, v) => `<div><small>${esc(l)}</small><b>${v == null ? '-' : esc(String(v))}</b></div>`;

  /* ── 개요 ── */
  async function loadOverview() {
    try { st.overview = await ADM.overview(); } catch (err) { st.overview = { error: err }; }
    if (S().route === 'admin') GP.render(false);
  }
  function overview() {
    const o = st.overview;
    if (!o) { loadOverview(); return page({ eyebrow: '관리자', title: '데이터 관리', body: loading('지금 데이터를 불러오는 중…') }); }
    if (o.error) return page({ eyebrow: '관리자', title: '데이터 관리', body: failBox(o.error, '개요를 불러오지 못했어요') + '<div class="actions"><button class="btn line" data-act="adm-reload">다시 불러오기</button></div>' });
    const e = o.education, g = o.goals || {}, vec = o.regulations.vectors;
    const pv = o.regulations.providers;
    const card = (ds, body) => `<div class="card"><div class="sec-h"><h2 class="st">${icon(DS[ds].icon)} ${DS[ds].title}</h2><button class="link" data-go="admin-ds:${ds}">관리 ${icon('right')}</button></div>${body}</div>`;
    return page({
      eyebrow: '관리자', title: '데이터 관리', lead: '인적·규정·교육 데이터를 화면에서 한 건씩 고치거나, 여러 건은 엑셀·CSV로 내려받아 고친 뒤 다시 올려요. 어느 쪽이든 같은 규칙으로 검사하고, 오류가 있으면 저장하지 않아요.',
      body: `<div class="adm-grid">
        ${card('hr', `<div class="adm-num">${num('재직', o.hr.active)}${num('퇴직', o.hr.retired)}${num('부서', o.hr.departments)}${num('부서장', o.hr.heads)}${num('평정', o.hr.evaluations)}</div>
          ${o.hr.noNumber ? `<p class="small muted" style="margin:0">사번이 없는 팀 테스트 계정 ${o.hr.noNumber}명은 엑셀로 다루지 않아요.</p>` : ''}
          ${o.hr.transfers.length ? `<p class="small" style="margin:8px 0 0"><b>최근 인사이동·권한 변경</b></p><ul class="plain-list small">${o.hr.transfers.map(t => `<li>${esc(t.at)} · ${esc(t.name)} · ${esc(t.from || '없음')} → ${esc(t.to || '없음')}${t.headBefore !== t.headAfter ? ` · ${t.headAfter ? '부서장 지정' : '부서장 해제'}` : ''}</li>`).join('')}</ul>` : ''}`)}
        ${card('regulations', `<div class="adm-num">${num('검색하는 조항', o.regulations.chunks)}${o.regulations.sets.map(s => num(s.group, `${s.count}건`)).join('')}</div>
          <p class="small muted" style="margin:0">벡터 색인: ${vec.length ? vec.map(v => `${esc(v.model)} ${v.count}개`).join(' · ') : '없음'} · 벡터가 없는 조항은 키워드 검색으로 찾아요</p>
          <div class="actions" style="margin-top:10px"><button class="btn line sm" data-act="adm-index">${icon('spark')}규정 색인 만들기</button></div>`)}
        ${card('education', `<div class="adm-num">${['course', 'book', 'cert'].map(k => num({ course: '강좌', book: '도서', cert: '자격증' }[k], (e[k] || {}).count)).join('')}</div>
          <p class="small muted" style="margin:0">추정 값이 남은 자료: ${['course', 'book', 'cert'].map(k => `${{ course: '강좌', book: '도서', cert: '자격증' }[k]} ${(e[k] || {}).estimated || 0}`).join(' · ')}</p>`)}
        <div class="card"><div class="sec-h"><h2 class="st">${icon('spark')} 목표 후보</h2></div>
          <div class="adm-num">${num('준비됨', g.ready || 0)}${num('기본 후보', g.default || 0)}${num('만드는 중', g.running || 0)}${num('실패', g.failed || 0)}</div>
          <p class="small muted" style="margin:0">직원 데이터가 바뀌면(이 화면의 저장·반영, 직원의 내 정보 저장) 그 직원의 후보를 서버가 미리 다시 만들어요.</p>
          <div class="actions" style="margin-top:10px"><button class="btn line sm" data-act="adm-goals">${icon('retry')}모두 다시 만들기</button></div></div>
      </div>
      <div class="sec"><div class="sec-h"><h2 class="st">최근 변경</h2><button class="link" data-go="admin-history">전체 이력 ${icon('right')}</button></div>${uploadList(o.uploads)}</div>
      ${note(`RunPod-Ollama ${pv.ollama.available ? '설정됨' : '설정 안 됨'}${pv.ollama.embed ? ` (임베딩 ${esc(pv.ollama.embed)})` : ''} · OpenAI API ${pv.openai.available ? '설정됨' : '설정 안 됨'}${pv.openai.embed ? ` (임베딩 ${esc(pv.openai.embed)})` : ''}. 관리자 계정은 직원의 로드맵·점검·보고서를 보지 않아요.`)}`
    });
  }
  const uploadList = list => (list && list.length ? `<div class="list">${list.map(u => {
    const [t, c] = UP_ST[u.status] || [u.status, 'line'], sm = u.summary || {}, form = sm.source === 'form';
    return `<button class="li" data-go="admin-preview:${u.uploadId}"><span class="idx">${icon(form ? 'edit' : u.fileName.toLowerCase().endsWith('.csv') ? 'file' : 'upload')}</span><div class="tx"><b>${esc(u.fileName)}</b><small>${esc(DS[u.dataset] ? DS[u.dataset].title : u.dataset)} · ${esc(u.createdAt)}${u.admin ? ` · ${esc(u.admin)}` : ''}${form ? '' : ` · 바뀌는 행 ${sm.changeRows ?? '-'}${sm.errorRows ? ` · 오류 ${sm.errorRows}` : ''}`}</small></div><span class="end"><span class="tag ${c}">${form ? '저장함' : t}</span>${icon('right')}</span></button>`;
  }).join('')}</div>` : '<p class="muted small">아직 변경 기록이 없어요.</p>');
  GP.act['adm-reload'] = () => { st.overview = null; GP.render(false); };
  GP.act['adm-goals'] = () => GP.sheet(`<p style="margin-top:0">재직 중인 모든 직원의 목표 후보를 다시 만들어요. 본인 입력이 없는 직원은 AI 활용 업무 기본 후보로 바로 저장해요.</p>
      <div class="stack"><label class="radio"><input type="radio" name="admGoalMode" value="mock" checked>시연용 가데이터로 만들기 <span class="small muted">· 비용 없음 · 바로 끝나요</span></label>
      <label class="radio"><input type="radio" name="admGoalMode" value="employee">각 직원이 고른 AI 모드로 만들기 <span class="small muted">· 실제 모델 호출(OpenAI API는 비용이 들어요) · 모드가 설정되지 않은 직원은 실패로 남아요</span></label></div>`,
  { title: '목표 후보를 모두 다시 만들까요?', foot: '<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="adm-goals-ok">다시 만들기</button>' });
  GP.act['adm-goals-ok'] = async () => {
    const m = (document.querySelector('input[name="admGoalMode"]:checked') || {}).value;
    GP.closeSheet();
    try { const r = await ADM.goalsAll(m === 'mock' ? 'mock' : null); GP.toast(`직원 ${r.employees}명 · 작업 ${r.started}개 시작 · 기본 후보 ${r.defaults}명 저장`); st.overview = null; setTimeout(() => { if (S().route === 'admin') GP.render(false); }, 1500); }
    catch (err) { GP.fail(err, '목표 후보를 다시 만들지 못했어요'); }
  };
  GP.act['adm-index'] = () => {
    const pv = (st.overview && st.overview.regulations.providers) || {};
    const opts = ['openai', 'ollama'].filter(p => pv[p] && pv[p].available && pv[p].embed);
    if (!opts.length) { GP.sheet(`<p style="margin-top:0">임베딩 모델이 설정된 AI 모드가 없어요. 지금은 도우미가 키워드 검색으로 조항을 찾아요.</p>${note('.env에 OPENAI_API_KEY와 OPENAI_EMBED_MODEL(팀 DB 벡터와 같은 text-embedding-3-small), 또는 OLLAMA_BASE_URL과 OLLAMA_EMBED_MODEL을 넣고 서버를 다시 실행하면 색인을 만들 수 있어요.')}`, { title: '규정 색인을 만들 수 없어요' }); return; }
    GP.sheet(`<p style="margin-top:0">벡터가 없는 조항만 임베딩해서 저장해요(1536차원이면 팀 DB 표, 아니면 보조 표). 조항 수만큼 임베딩 모델을 호출해요.</p>
      <div class="stack">${opts.map((p, i) => `<label class="radio"><input type="radio" name="admIdx" value="${p}" ${i ? '' : 'checked'}>${p === 'openai' ? 'OpenAI API' : 'RunPod-Ollama'} · ${esc(pv[p].embed)}</label>`).join('')}</div>`,
    { title: '규정 색인을 만들까요?', foot: '<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="adm-index-ok">만들기</button>' });
  };
  GP.act['adm-index-ok'] = async () => {
    const p = (document.querySelector('input[name="admIdx"]:checked') || {}).value; GP.closeSheet();
    GP.toast('규정 색인을 만드는 중이에요…');
    try { const j = await ADM.buildIndex(p); const r = await API.job(j.jobId); GP.toast(`규정 색인: 새로 ${r.added}개 · 전체 ${r.total}개 (${r.dimensions}차원)`); st.overview = null; if (S().route === 'admin') GP.render(false); }
    catch (err) { GP.fail(err, '규정 색인을 만들지 못했어요'); }
  };

  /* ── 데이터 화면: 내려받기 · 올리기 · 지금 데이터 표 ── */
  const ck = (ds, sheet) => `${ds}|${sheet}|${st.q[ds + sheet] || ''}|${st.page[ds + sheet] || 0}`;
  async function loadRows(ds, sheet) {
    const k = ck(ds, sheet);
    st.cache[k] = { loading: true };
    try { st.cache[k] = await ADM.rows(ds, sheet, { q: st.q[ds + sheet] || '', limit: PAGE, offset: (st.page[ds + sheet] || 0) * PAGE }); }
    catch (err) { st.cache[k] = { error: err }; }
    if (S().route === 'admin-ds:' + ds) GP.render(false);
  }
  const curSheet = ds => st.tab[ds] || DS[ds].sheets[0];
  const keyOf = (cols, r) => Object.fromEntries(cols.filter(c => c.key).map(c => [c.field, r[c.field] || '']));
  const sameKey = (a, b) => !!(a && b) && Object.keys(a).every(f => String(a[f]) === String(b[f]));
  function table(d, ds) {
    const cols = d.columns, ed = st.edit && st.edit.ds === ds && st.edit.mode === 'edit' && st.edit.sheet === d.sheet ? st.edit : null;
    return `<div class="adm-tbl"><table><thead><tr>${cols.map(c => `<th class="${c.readonly ? 'ro' : ''}${c.key ? ' key' : ''}" title="${esc(c.help || '')}">${esc(c.header)}${c.required && !c.key ? ' *' : ''}</th>`).join('')}</tr></thead>
      <tbody>${d.rows.map((r, i) => `<tr data-act="adm-edit" data-arg="${ds}|${i}" tabindex="0" title="눌러서 고치기" class="${ed && sameKey(ed.key, keyOf(cols, r)) ? 'on' : ''}">${cols.map(c => { const v = r[c.field] || ''; return `<td class="${c.readonly ? 'ro' : ''}${c.key ? ' key' : ''}"><span class="clip" title="${esc(v)}">${esc(v)}</span></td>`; }).join('')}</tr>`).join('') || `<tr><td colspan="${cols.length}" class="muted">행이 없어요</td></tr>`}</tbody></table></div>`;
  }
  /* 여러 건 고치기(엑셀·CSV): 한 건은 표에서 고치므로 접어 둔다. 펼친 상태는 st.bulk 에 기억한다 */
  function bulk(ds, sheet) {
    const D = DS[ds];
    return `<details class="card adm-bulk" id="admBulk" ${st.bulk || st.busy ? 'open' : ''}><summary><span class="adm-bulk-t">${icon('upload')}<b>엑셀·CSV로 여러 건 한꺼번에 고치기</b></span><span class="small muted">내려받아 고친 파일을 올리면 미리보기를 거쳐 반영해요</span></summary>
        <div class="adm-bulk-b"><h3 class="adm-h3">1. 내려받기</h3>
          <div class="adm-bar"><a class="btn pri sm" href="${ADM.downloadUrl(ds, 'xlsx')}" download>${icon('download')}엑셀로 내려받기 (시트 ${D.sheets.length}개)</a>
            <a class="btn line sm" href="${ADM.templateUrl(ds, 'xlsx')}" download>빈 양식</a><span class="grow"></span>
            <select class="input" id="admCsvSheet" aria-label="CSV로 내려받을 시트">${D.sheets.map(s => `<option ${s === sheet ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select>
            <button class="btn line sm" data-act="adm-csv" data-arg="${ds}">${icon('download')}CSV로 내려받기</button></div>
          <p class="small muted" style="margin:8px 0 0">엑셀 첫 시트 ‘안내’에 열 설명과 규칙이 있어요. 초록 머리글은 꼭 적는 열, 회색 머리글은 참고용이에요. CSV는 시트 하나씩이에요.</p>
          <h3 class="adm-h3">2. 고친 파일 올리기</h3>
          <label class="drop adm-drop"><input type="file" id="admFile" accept=".xlsx,.csv"><span class="ico">${icon('upload')}</span><span><b>엑셀(.xlsx) 또는 CSV 파일 고르기</b><small>올리면 바로 바뀌지 않고 미리보기를 먼저 보여 줘요 · 20MB까지</small></span></label>
          <div class="adm-bar" style="margin-top:8px"><span class="small muted">CSV의 시트</span><select class="input" id="admUpSheet" aria-label="CSV 시트"><option value="">머리글로 알아서 찾기</option>${D.sheets.map(s => `<option>${esc(s)}</option>`).join('')}</select>
            ${st.busy ? `<span class="small">${loading('미리보기를 만드는 중…')}</span>` : ''}</div>
          ${note('파일에 없는 행은 그대로 둬요. 지우려면 ‘삭제’ 열에 Y를 적어요. 오류가 하나라도 있으면 반영할 수 없어요.')}</div></details>`;
  }
  function dataset(ds) {
    const D = DS[ds]; if (!D) return page({ title: '없는 데이터예요' });
    const sheet = curSheet(ds), k = ck(ds, sheet), d = st.cache[k];
    if (!d) loadRows(ds, sheet);
    const pg = st.page[ds + sheet] || 0;
    const ed = st.edit && st.edit.ds === ds && st.edit.sheet === sheet ? st.edit : null;
    const ready = d && !d.loading && !d.error;
    const body = !d || d.loading ? loading('불러오는 중…') : d.error ? failBox(d.error, '데이터를 불러오지 못했어요') : `${table(d, ds)}
      <div class="adm-pager"><span class="grow small">행을 누르면 오른쪽에서 고칠 수 있어요</span>${d.total}행 중 ${d.total ? pg * PAGE + 1 : 0}~${Math.min(d.total, (pg + 1) * PAGE)}
        <button class="btn line sm" data-act="adm-page" data-arg="${ds}|-1" ${pg ? '' : 'disabled'} aria-label="이전 쪽">${icon('left')}</button>
        <button class="btn line sm" data-act="adm-page" data-arg="${ds}|1" ${(pg + 1) * PAGE < d.total ? '' : 'disabled'} aria-label="다음 쪽">${icon('right')}</button></div>`;
    return page({
      eyebrow: '관리자 · 데이터 관리', title: D.title, lead: D.lead,
      body: `<div class="adm-split${ed ? ' has-panel' : ''}"><div class="adm-main">${bulk(ds, sheet)}
        <div class="sec"><div class="sec-h"><h2 class="st">지금 데이터</h2><button class="btn pri sm" data-act="adm-new" data-arg="${ds}" ${ready ? '' : 'disabled'}>${icon('plus')}${esc(sheet)} 추가</button></div>
          <div class="adm-tabs">${D.sheets.map(s => `<button class="chip ${s === sheet ? 'on' : ''}" data-act="adm-tab" data-arg="${ds}|${esc(s)}">${esc(s)}</button>`).join('')}</div>
          <div class="adm-bar" style="margin-bottom:10px"><input class="input sm" id="admQ" value="${esc(st.q[ds + sheet] || '')}" placeholder="이 시트에서 찾기" aria-label="찾기"><button class="btn line sm" data-act="adm-q" data-arg="${ds}">찾기</button></div>
          ${body}</div></div>${ed ? panel(ed) : ''}</div>`
    });
  }
  GP.act['adm-tab'] = arg => { const [ds, s] = arg.split('|'); guard(() => { st.tab[ds] = s; if (st.edit && st.edit.ds === ds) st.edit = null; GP.render(false); }); };
  GP.act['adm-page'] = arg => { const [ds, dir] = arg.split('|'), s = st.tab[ds] || DS[ds].sheets[0]; st.page[ds + s] = Math.max(0, (st.page[ds + s] || 0) + +dir); GP.render(false); };
  GP.act['adm-q'] = ds => { const s = st.tab[ds] || DS[ds].sheets[0], i = document.getElementById('admQ'); st.q[ds + s] = i ? i.value.trim() : ''; st.page[ds + s] = 0; GP.render(false); };
  GP.act['adm-csv'] = ds => { const s = (document.getElementById('admCsvSheet') || {}).value; location.href = ADM.downloadUrl(ds, 'csv', s); };
  async function upload(ds, file) {
    if (!file || st.busy) return;
    st.busy = true; GP.render(false);
    try {
      const r = await ADM.preview(ds, file, (document.getElementById('admUpSheet') || {}).value || '');
      st.previews[r.uploadId] = Object.assign(r, { status: 'previewed' }); st.filter = r.errorRows ? 'error' : 'all';
      st.busy = false; GP.go('admin-preview:' + r.uploadId);
    } catch (err) { st.busy = false; GP.render(false); GP.sheet(failBox(err, '파일을 읽지 못했어요'), { title: '미리보기를 만들지 못했어요' }); }
  }

  /* ── 한 건씩 고치기: 오른쪽 패널 → 확인(서버가 엑셀과 같은 검사) → 확인 창 → 저장 (2026-10-22) ──
     칸 값은 표·엑셀과 같은 글자(Y/N, 2024-03-02, 세미콜론 목록)로 다루고 서버가 같은 규칙으로 읽는다.
     고칠 때는 바뀐 칸만, 추가할 때는 적은 칸만 보낸다. 확인 창에서 본 내용(token)이 저장 때와 다르면 서버가 저장하지 않는다 */
  const LONG = { text: 8, summary: 4, description: 4, task: 3, subjects: 2 };
  const norm = v => String(v == null ? '' : v).split(/[;\n]/).map(x => x.trim()).filter(Boolean).join('; ');
  const splitList = v => String(v || '').split(/[;\n]/).map(x => x.trim()).filter(Boolean);
  const DEL_ASK = { '퇴직 처리': '퇴직 처리할까요?', '삭제': '삭제할까요?', '검색에서 빼기': '도우미 검색에서 뺄까요?' };
  function openEdit(ds, sheet, d, r) {
    const orig = Object.fromEntries(d.columns.map(c => [c.field, r ? (r[c.field] || '') : (c.default || '')]));
    st.edit = { ds, sheet, mode: r ? 'edit' : 'add', cols: d.columns, info: d.sheetInfo || {}, key: r ? keyOf(d.columns, r) : null,
                orig, vals: Object.assign({}, orig), errs: {}, msgs: [], busy: false, extra: null, enter: true };
    GP.render(false);
    st.edit.enter = false;   // 열릴 때만 미끄러져 들어온다(다시 그릴 때는 그대로)
    const f = document.querySelector('.adm-panel [data-ef]'); if (f) f.focus({ preventScroll: true });
  }
  /* 새 규정은 조항이 하나 이상 있어야 해서(서버 검사) 첫 조항 칸을 같은 패널에 둔다 */
  async function loadFirstArticle(ed) {
    try {
      const d = await ADM.rows('regulations', '조항', { limit: 1 });
      if (st.edit !== ed) return;
      const cols = d.columns.filter(c => !c.readonly && !c.key && c.field !== 'reg');
      ed.extra = { cols, vals: Object.fromEntries(cols.map(c => [c.field, c.default || ''])), errs: {} };
    } catch (err) { ed.msgs = [`첫 조항 칸을 불러오지 못했어요 · ${AI.cause(err).user}`]; }
    paintPanel();
  }
  const dirty = ed => !!ed && (ed.cols.some(c => !c.readonly && norm(ed.vals[c.field]) !== norm(ed.orig[c.field])) ||
    !!(ed.extra && ed.extra.cols.some(c => norm(ed.extra.vals[c.field]) !== norm(c.default))));
  /* 저장하지 않은 칸이 있으면 버릴지 먼저 묻는다 */
  let afterDiscard = null;
  function guard(fn) {
    if (!dirty(st.edit)) { fn(); return; }
    afterDiscard = fn;
    GP.sheet('<p style="margin-top:0">오른쪽 패널에 저장하지 않은 내용이 있어요. 버리고 넘어갈까요?</p>',
      { title: '고친 내용을 버릴까요?', foot: '<button class="btn line" data-act="sheet-close">계속 고치기</button><button class="btn pri" data-act="adm-discard-edit">버리기</button>' });
  }
  GP.act['adm-discard-edit'] = () => { GP.closeSheet(); st.edit = null; const fn = afterDiscard; afterDiscard = null; if (fn) fn(); else GP.render(false); };
  GP.act['adm-edit'] = arg => {
    const [ds, i] = arg.split('|'), d = st.cache[ck(ds, curSheet(ds))], r = d && d.rows && d.rows[+i];
    if (!r) return;
    if (st.edit && st.edit.mode === 'edit' && st.edit.ds === ds && sameKey(st.edit.key, keyOf(d.columns, r))) return;
    guard(() => openEdit(ds, curSheet(ds), d, r));
  };
  GP.act['adm-new'] = ds => {
    const sheet = curSheet(ds), d = st.cache[ck(ds, sheet)];
    if (!d || !d.columns) return;
    guard(() => { openEdit(ds, sheet, d, null); if (ds === 'regulations' && sheet === '규정') loadFirstArticle(st.edit); });
  };
  GP.act['adm-close'] = () => guard(() => { st.edit = null; GP.render(false); });

  function fieldHtml(c, v, err, scope) {
    const id = `ef-${scope}-${c.field}`, name = `${scope}.${c.field}`, o = c.options || {}, items = o.items || [];
    let input, labelFor = true;
    if (c.kind === 'bool') {
      labelFor = false;
      input = `<div class="chips" role="radiogroup" aria-label="${esc(c.header)}">${[['Y', '예'], ['N', '아니요']].map(([x, l]) => `<label class="chip"><input type="radio" name="${id}" data-ef="${name}" value="${x}" ${v === x ? 'checked' : ''}>${l}</label>`).join('')}</div>`;
    } else if (c.kind === 'list' && o.strict) {
      labelFor = false;
      const on = splitList(v), known = new Set(items.map(x => x.value));
      const all = items.concat(on.filter(x => !known.has(x)).map(x => ({ value: x })));
      input = `<div class="chips adm-multi" role="group" aria-label="${esc(c.header)}">${all.map(x => `<label class="chip"><input type="checkbox" data-ef="${name}" value="${esc(x.value)}" ${on.includes(x.value) ? 'checked' : ''}>${esc(x.label || x.value)}</label>`).join('')}</div>`;
    } else if (c.kind === 'choice' || (o.strict && items.length)) {
      const opts = c.kind === 'choice' ? c.choices.map(x => ({ value: x })) : items, has = opts.some(x => x.value === v);
      input = `<select class="input" id="${id}" data-ef="${name}">${!c.required || !v ? `<option value="">${c.required ? '골라 주세요' : '(비움)'}</option>` : ''}${v && !has ? `<option selected>${esc(v)}</option>` : ''}${opts.map(x => `<option value="${esc(x.value)}" ${x.value === v ? 'selected' : ''}>${esc(x.label ? `${x.value} · ${x.label}` : x.value)}</option>`).join('')}</select>`;
    } else if (c.kind === 'date') {
      input = `<input class="input" type="date" id="${id}" data-ef="${name}" value="${esc(v)}">`;
    } else if (LONG[c.field] || c.kind === 'list') {
      input = `<textarea class="textarea" id="${id}" data-ef="${name}" rows="${LONG[c.field] || 2}">${esc(v)}</textarea>`;
    } else {
      input = `<input class="input" id="${id}" data-ef="${name}" value="${esc(v)}" autocomplete="off" ${c.kind === 'int' || c.kind === 'num' ? 'inputmode="decimal"' : ''} ${items.length ? `list="${id}-dl"` : ''}>${items.length ? `<datalist id="${id}-dl">${items.map(x => `<option value="${esc(x.value)}">${esc(x.label || '')}</option>`).join('')}</datalist>` : ''}`;
    }
    const help = [c.help, c.kind === 'list' && !o.strict ? '여러 개는 세미콜론(;)으로 구분해요' : ''].filter(Boolean).join(' · ');
    const lab = `${esc(c.header)}${c.required || c.key ? ' <span class="req" aria-hidden="true">*</span>' : ''}`;
    return `<div class="adm-f${err ? ' bad' : ''}">${labelFor ? `<label for="${id}">${lab}</label>` : `<span class="flabel">${lab}</span>`}${input}
      ${err ? `<p class="adm-ferr">${icon('alert')}${esc(err)}</p>` : ''}${help ? `<p class="adm-fhelp">${esc(help)}</p>` : ''}</div>`;
  }
  function panel(ed) {
    const keyCols = ed.cols.filter(c => c.key), add = ed.mode === 'add';
    const short = v => (String(v).length > 20 ? String(v).slice(0, 8) + '…' : v);
    const title = add ? `${ed.sheet} 추가` : [ed.orig.no, ed.orig.name, ed.orig.title].filter(Boolean).join(' · ') || `${ed.sheet} 고치기`;
    const sub = add ? `${ed.info.autoKey ? `${keyCols.map(c => c.header).join(' · ')}는 저장할 때 정해져요 · ` : ''}* 표시 칸은 꼭 적어요`
      : `${ed.sheet} · ${keyCols.map(c => `${c.header} ${short(ed.orig[c.field])}`).join(' · ')}`;
    const fields = ed.cols.filter(c => !c.readonly && (add ? !(c.key && ed.info.autoKey) : !c.key));
    const ro = add ? [] : ed.cols.filter(c => c.readonly && ed.orig[c.field]);
    const ex = ed.extra;
    return `<aside class="adm-panel${ed.enter ? ' enter' : ''}" aria-label="${esc(title)}">
      <div class="adm-ph"><div class="grow"><b>${esc(title)}</b><small>${esc(sub)}</small></div><button class="x" data-act="adm-close" aria-label="패널 닫기">${icon('x')}</button></div>
      <div class="adm-pb">${ed.msgs.map(m => `<p class="adm-msg e">${icon('alert')} ${esc(m)}</p>`).join('')}
        ${ro.length ? `<dl class="adm-ro">${ro.map(c => `<dt>${esc(c.header)}</dt><dd>${esc(ed.orig[c.field])}</dd>`).join('')}</dl>` : ''}
        ${fields.map(c => fieldHtml(c, ed.vals[c.field] || '', ed.errs[c.header], 'row')).join('')}
        ${add && ed.ds === 'regulations' && ed.sheet === '규정' ? `<h3 class="adm-h3">첫 조항</h3><p class="adm-fhelp" style="margin:0 0 10px">새 규정은 조항이 하나 이상 있어야 해요. 나머지 조항은 저장한 뒤 ‘조항’에서 추가해요.</p>
          ${ex ? ex.cols.map(c => fieldHtml(c, ex.vals[c.field] || '', ex.errs[c.header], 'art')).join('') : loading('조항 칸을 불러오는 중…')}` : ''}</div>
      <div class="adm-pf">${!add && ed.info.deletable ? `<button class="btn line sm adm-del" data-act="adm-del">${esc(ed.info.deleteLabel || '삭제')}</button>` : ''}<span class="grow"></span>
        <button class="btn line sm" data-act="adm-close">취소</button>
        <button class="btn pri sm" data-act="adm-save" ${ed.busy ? 'disabled' : ''}>${ed.busy ? '<span class="sp"></span>확인하는 중…' : `${icon('check')}${add ? '추가' : '저장'}`}</button></div></aside>`;
  }
  /* 패널만 다시 그린다(표 스크롤·찾기 칸을 그대로 두기 위해) */
  function paintPanel() {
    const el = document.querySelector('.adm-panel');
    if (!el || !st.edit) { GP.render(false); return; }
    el.outerHTML = panel(st.edit);
    bindPanel(document.querySelector('.adm-panel'));
  }
  function bindPanel(el) {
    if (!el) return;
    const upd = e => {
      const t = e.target, f = t.dataset && t.dataset.ef, ed = st.edit;
      if (!f || !ed) return;
      const [scope, field] = f.split('.'), box = scope === 'art' ? ed.extra && ed.extra.vals : ed.vals;
      if (!box) return;
      if (t.type === 'checkbox') box[field] = [...el.querySelectorAll(`input[type="checkbox"][data-ef="${f}"]:checked`)].map(x => x.value).join('; ');
      else if (t.type === 'radio') { if (t.checked) box[field] = t.value; } else box[field] = t.value;
      const wrap = t.closest('.adm-f');
      if (wrap && wrap.classList.contains('bad')) { wrap.classList.remove('bad'); const m = wrap.querySelector('.adm-ferr'); if (m) m.remove(); }
    };
    el.addEventListener('input', upd);
    el.addEventListener('change', upd);
  }
  function editRows(ed, del) {
    if (del) return [{ sheet: ed.sheet, key: ed.key, delete: true }];
    const pick = (cols, box, base) => {
      const out = {};
      cols.forEach(c => { if (base ? norm(box[c.field]) !== norm(base[c.field]) : norm(box[c.field]) !== '') out[c.field] = box[c.field] || ''; });
      return out;
    };
    if (ed.mode === 'edit') return [{ sheet: ed.sheet, key: ed.key, values: pick(ed.cols.filter(c => !c.readonly && !c.key), ed.vals, ed.orig) }];
    const rows = [{ sheet: ed.sheet, key: null, values: pick(ed.cols.filter(c => !c.readonly && !(c.key && ed.info.autoKey)), ed.vals) }];
    if (ed.extra) rows.push({ sheet: '조항', key: null, values: Object.assign({ reg: ed.vals.short || '' }, pick(ed.extra.cols, ed.extra.vals)) });
    return rows;
  }
  /* 서버 오류를 칸 옆에 붙인다. 칸이 없는 오류(열쇠·시트 사이 검사)는 패널 위에 */
  function placeErrors(ed, rows) {
    ed.errs = {}; ed.msgs = []; if (ed.extra) ed.extra.errs = {};
    rows.forEach((r, i) => {
      const scope = i === 0 || !ed.extra ? { cols: ed.cols, errs: ed.errs } : { cols: ed.extra.cols, errs: ed.extra.errs };
      const shown = new Set(scope.cols.filter(c => !c.readonly && (ed.mode === 'add' ? !(c.key && ed.info.autoKey) : !c.key)).map(c => c.header));
      (r.errors || []).forEach(e => { if (shown.has(e.col) && !scope.errs[e.col]) scope.errs[e.col] = e.msg; else ed.msgs.push(`${e.col} · ${e.msg}`); });
    });
  }
  async function submitEdit(del) {
    const ed = st.edit; if (!ed || ed.busy) return;
    if (ed.extra === null && ed.mode === 'add' && ed.ds === 'regulations' && ed.sheet === '규정') { GP.toast('첫 조항 칸을 불러오는 중이에요'); return; }
    const rows = editRows(ed, del);
    if (!del && ed.mode === 'edit' && !Object.keys(rows[0].values).length) { GP.toast('바뀐 칸이 없어요'); return; }
    ed.busy = true; paintPanel();
    let r;
    try { r = await ADM.edit(ed.ds, rows); } catch (err) { ed.busy = false; if (st.edit === ed) paintPanel(); GP.fail(err, '확인하지 못했어요'); return; }
    ed.busy = false;
    if (st.edit !== ed) return;
    placeErrors(ed, r.rows || []);
    paintPanel();
    if (r.errorRows) { const b = document.querySelector('.adm-panel .adm-f.bad [data-ef], .adm-panel .adm-msg'); if (b) b.scrollIntoView({ block: 'center' }); if (b && b.focus) b.focus({ preventScroll: true }); return; }
    if (!r.changeRows) { GP.toast('바뀐 내용이 없어요'); return; }
    st.pending = { ed, rows, token: r.token };
    confirmEdit(ed, r.rows || [], del);
  }
  GP.act['adm-save'] = () => submitEdit(false);
  GP.act['adm-del'] = () => submitEdit(true);
  const chgCard = (r, delLabel) => {
    const [t, c] = r.action === 'delete' && delLabel ? [delLabel, 'warn'] : ACT[r.action] || [r.action, 'line'];
    return `<div class="adm-row"><div class="adm-row-h"><span class="tag ${c}">${t}</span><b>${esc(r.label || r.key)}</b><span class="muted">${esc(r.sheet)}</span>${(r.tags || []).filter(x => x !== delLabel).map(x => `<span class="tag acc">${esc(x)}</span>`).join('')}</div>
      ${(r.changes || []).length ? `<ul class="adm-chg">${r.changes.map(x => `<li><span class="k">${esc(x.col)}</span><span>${x.before ? `<s>${esc(x.before)}</s> → ` : ''}<span class="to">${esc(x.after || '(비움)')}</span></span></li>`).join('')}</ul>` : ''}
      ${(r.warnings || []).map(w => `<p class="adm-msg w">${icon('info')} ${esc(w)}</p>`).join('')}</div>`;
  };
  function confirmEdit(ed, rows, del) {
    const newEmp = rows.some(x => x.sheet === '직원' && x.action === 'add');
    const regen = ed.ds === 'hr' && !newEmp && rows.some(x => x.sheet === '평정' || (x.sheet === '직원' && x.action === 'update' && !(x.tags || []).includes('퇴직')));
    const title = del ? DEL_ASK[ed.info.deleteLabel] || '삭제할까요?' : ed.mode === 'add' ? '이대로 추가할까요?' : '이대로 저장할까요?';
    const goal = regen ? `<div class="stack adm-goal"><span class="small muted">저장한 뒤 이 직원의 목표 후보를 다시 만들 때</span>
        <label class="radio"><input type="radio" name="admEditGoal" value="employee" checked><span>그 직원이 고른 AI 모드로 만들기 <span class="small muted">· 실제 모델을 한 번 불러요(OpenAI API는 비용이 들어요) · 모드가 설정되지 않았으면 실패로 남아요</span></span></label>
        <label class="radio"><input type="radio" name="admEditGoal" value="mock"><span>시연용 가데이터로 만들기 <span class="small muted">· 비용 없음 · 화면에 ‘가데이터’로 보여요</span></span></label></div>`
      : newEmp ? note('새 직원은 본인 입력(업무 설명·경험 요약·기술 스택)이 없어 AI 활용 업무 기본 후보가 들어가요. 직원이 내 정보를 채우면 그 직원이 고른 AI 모드로 다시 만들어요. 처음 비밀번호는 시연 초기 비밀번호예요.')
      : del && ed.sheet === '직원' ? note('재직 상태를 퇴직, 계정 상태를 중지로 바꾸고 로그인을 끊어요. 부서장이면 부서장도 해제해요. 직원 기록은 지우지 않고 남겨요.') : '';
    GP.sheet(`<div class="adm-rows">${rows.filter(x => x.action !== 'same').map(x => chgCard(x, del ? ed.info.deleteLabel : null)).join('')}</div>${goal}`,
      { title, sub: `${DS[ed.ds].title} · 저장하면 바로 반영되고 변경 이력에 남아요`, foot: `<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="adm-edit-ok">${icon('check')}${del ? esc(ed.info.deleteLabel || '삭제') : ed.mode === 'add' ? '추가하기' : '저장하기'}</button>` });
  }
  GP.act['adm-edit-ok'] = async () => {
    const p = st.pending; if (!p) return;
    const gm = (document.querySelector('input[name="admEditGoal"]:checked') || {}).value;
    const btn = document.querySelector('[data-act="adm-edit-ok"]'); if (btn) { btn.disabled = true; btn.innerHTML = '<span class="sp"></span>저장하는 중…'; }
    try {
      const r = await ADM.edit(p.ed.ds, p.rows, { save: true, token: p.token, goalMode: gm === 'mock' ? 'mock' : null });
      st.pending = null; GP.closeSheet();
      if (st.edit === p.ed) st.edit = null;
      Object.keys(st.cache).forEach(k => { if (k.startsWith(p.ed.ds + '|')) delete st.cache[k]; });
      st.overview = null; st.history = null;
      GP.render(false);
      const vers = (r.applied && r.applied.versions) || [];
      GP.toast(`저장했어요${vers.length ? ` · ${vers.map(v => `「${v.regulation}」 새 버전`).join(', ')}` : ''}${r.goalCount ? ' · 목표 후보를 다시 만들어요' : ''}`);
    } catch (err) {
      st.pending = null; GP.closeSheet();
      GP.fail(err, '저장하지 못했어요');
    }
  };

  /* ── 미리보기 · 반영 ── */
  async function loadPreview(id) {
    try { st.previews[id] = await ADM.upload(id); } catch (err) { st.previews[id] = { error: err }; }
    if (S().route === 'admin-preview:' + id) GP.render(false);
  }
  const rowCard = (r, form) => {
    const [t, c] = ACT[r.action] || [r.action, 'line'];
    return `<div class="adm-row ${r.action === 'error' ? 'error' : ''}"><div class="adm-row-h"><span class="tag ${c}">${t}</span><b>${esc(r.label || r.key)}</b><span class="muted">${esc(r.sheet)}${form ? '' : ` 시트 · ${r.row}행`} · ${esc(r.key)}</span>${(r.tags || []).map(x => `<span class="tag acc">${esc(x)}</span>`).join('')}</div>
      ${(r.errors || []).map(e => `<p class="adm-msg e">${icon('alert')} <b>${esc(e.col)}</b> · ${esc(e.msg)}</p>`).join('')}
      ${(r.changes || []).length && r.action !== 'error' ? `<ul class="adm-chg">${r.changes.map(x => `<li><span class="k">${esc(x.col)}</span><span>${x.before ? `<s>${esc(x.before)}</s> → ` : ''}<span class="to">${esc(x.after || '(비움)')}</span></span></li>`).join('')}</ul>` : ''}
      ${(r.warnings || []).map(w => `<p class="adm-msg w">${icon('info')} ${esc(w)}</p>`).join('')}</div>`;
  };
  function preview(id) {
    const p = st.previews[id];
    if (!p) { loadPreview(id); return page({ back: 'admin-history', title: '미리보기', body: loading('불러오는 중…') }); }
    if (p.error) return page({ back: 'admin-history', title: '미리보기', body: failBox(p.error, '미리보기를 불러오지 못했어요') });
    const D = DS[p.dataset] || { title: p.dataset }, rows = p.rows || [], applied = p.status === 'applied';
    const cnt = a => rows.filter(r => r.action === a).length;
    const shown = st.filter === 'all' ? rows : rows.filter(r => r.action === st.filter);
    const sums = p.summary || {};
    const title = p.source === 'form' ? '화면에서 저장했어요' : applied ? '반영했어요' : p.status === 'rejected' ? '취소한 미리보기예요' : p.status === 'expired' ? '시간이 지난 미리보기예요' : p.errorRows ? '오류를 고쳐야 반영할 수 있어요' : p.changeRows ? '이 내용으로 반영할까요?' : '바뀐 내용이 없어요';
    const ap = p.applied || {};
    const sheetsDone = Object.entries(ap).filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v) && Object.values(v).some(Boolean))
      .map(([k, v]) => `${k} ${Object.entries(v).filter(([, n]) => n).map(([a, n]) => `${{ add: '추가', update: '변경', delete: '삭제', hidden: '목록에서 뺌' }[a] || a} ${n}`).join(' · ')}`);
    const appliedNote = applied ? note(`반영 결과 · ${sheetsDone.join(' / ') || '바뀐 행 없음'}${ap.transfers ? ` · 인사이동·권한 이력 ${ap.transfers}건` : ''}${(ap.versions || []).length ? ` · 새 규정 버전 ${ap.versions.map(v => `「${esc(v.regulation)}」 ${esc(v.version)}(조항 ${v.chunks}개)`).join(', ')}` : ''}${p.goalCount ? ` · 목표 후보를 다시 만드는 직원 ${p.goalCount}명` : ''}`) : '';
    const foot = p.status !== 'previewed' ? `<button class="btn line" data-go="admin-ds:${p.dataset}">${esc(D.title)}로</button>` :
      `${p.dataset === 'hr' ? `<div class="stack" style="margin-bottom:10px"><span class="small muted">반영한 뒤 바뀐 직원의 목표 후보를 다시 만들 때</span>
          <label class="radio"><input type="radio" name="admApplyGoal" value="mock" checked>시연용 가데이터로 만들기</label>
          <label class="radio"><input type="radio" name="admApplyGoal" value="employee">각 직원이 고른 AI 모드로 만들기(설정 안 된 직원은 실패로 남아요)</label></div>` : ''}
        <div class="actions" style="margin-top:0"><button class="btn pri" data-act="adm-apply" data-arg="${id}" ${p.canApply ? '' : 'disabled'}>${icon('check')}반영하기</button><button class="btn line" data-act="adm-discard" data-arg="${id}">취소</button></div>
        ${p.canApply ? '' : `<p class="small muted" style="margin:6px 0 0">${p.errorRows ? `오류가 있는 행 ${p.errorRows}개를 고친 파일을 다시 올려 주세요.` : '바뀌는 행이 없어 반영할 것이 없어요.'}</p>`}`;
    return page({
      back: 'admin-ds:' + p.dataset, eyebrow: `${esc(D.title)} · ${esc(p.fileName)}${p.createdAt ? ` · ${esc(p.createdAt)}` : ''}`, title,
      lead: p.source === 'form' ? '관리자 화면에서 고쳐 팀 DB에 저장한 내용이에요.' : applied ? '팀 DB에 반영했어요. 아래는 반영한 행이에요.' : '파일과 지금 데이터를 비교했어요. 아직 아무것도 바뀌지 않았어요. 미리보기는 30분 동안만 반영할 수 있어요.',
      body: `${appliedNote}<div class="card"><table class="adm-sum"><thead><tr><th>시트</th><th>추가</th><th>변경</th><th>삭제</th><th>그대로</th><th>오류</th></tr></thead>
          <tbody>${Object.entries(sums).map(([s, c]) => `<tr><td>${esc(s)}</td><td>${c.add}</td><td>${c.update}</td><td>${c.delete}</td><td>${c.same}</td><td class="${c.error ? 'err' : ''}">${c.error}</td></tr>`).join('')}</tbody></table>
          ${(p.notes || []).map(n => `<p class="small muted" style="margin:8px 0 0">${icon('info')} ${esc(n)}</p>`).join('')}</div>
        <div class="adm-tabs">${[['all', '전체', rows.length], ['error', '오류', cnt('error')], ['add', '추가', cnt('add')], ['update', '변경', cnt('update')], ['delete', '삭제', cnt('delete')], ['skip', '건너뜀', cnt('skip')]].filter(([k, , n]) => k === 'all' || n).map(([k, l, n]) => `<button class="chip ${st.filter === k ? 'on' : ''}" data-act="adm-filter" data-arg="${k}">${l} ${n}</button>`).join('')}</div>
        <div class="adm-rows">${shown.slice(0, 300).map(r => rowCard(r, p.source === 'form')).join('') || '<p class="muted small">보여 줄 행이 없어요.</p>'}${shown.length > 300 ? `<p class="small muted">처음 300행만 보여요(전체 ${shown.length}행).</p>` : ''}</div>
        <div class="adm-foot">${foot}</div>`
    });
  }
  GP.act['adm-filter'] = k => { st.filter = k; GP.render(false); };
  GP.act['adm-apply'] = async id => {
    const p = st.previews[id]; if (!p || !p.canApply) return;
    const gm = (document.querySelector('input[name="admApplyGoal"]:checked') || {}).value;
    const btn = document.querySelector('[data-act="adm-apply"]'); if (btn) { btn.disabled = true; btn.innerHTML = '<span class="sp"></span>반영하는 중…'; }
    try {
      const r = await ADM.apply(id, gm === 'mock' ? 'mock' : null);
      Object.assign(p, { status: 'applied', canApply: false, applied: r.applied, goalCount: r.goalCount });
      st.cache = {}; st.overview = null; st.history = null;
      GP.render(true); GP.toast('반영했어요');
    } catch (err) {
      GP.fail(err, '반영하지 못했어요');
      if (err.payload && ['STALE_PREVIEW', 'NOW_INVALID', 'PREVIEW_EXPIRED', 'UPLOAD_DONE'].includes(err.payload.code)) { delete st.previews[id]; }
      GP.render(false);
    }
  };
  GP.act['adm-discard'] = async id => {
    try { await ADM.discard(id); } catch (err) { /* 이미 끝난 미리보기면 그대로 */ }
    const p = st.previews[id]; st.history = null;
    GP.go(p ? 'admin-ds:' + p.dataset : 'admin'); GP.toast('미리보기를 취소했어요. 아무것도 바뀌지 않았어요');
  };

  /* ── 업로드 이력 ── */
  function history() {
    if (!st.history) { ADM.uploads('').then(h => { st.history = h; if (S().route === 'admin-history') GP.render(false); }).catch(err => { st.history = { error: err }; GP.render(false); }); return page({ eyebrow: '관리자', title: '변경 이력', body: loading('불러오는 중…') }); }
    if (st.history.error) return page({ eyebrow: '관리자', title: '변경 이력', body: failBox(st.history.error, '이력을 불러오지 못했어요') });
    return page({ eyebrow: '관리자', title: '변경 이력', lead: '화면에서 고친 내용과 올린 파일의 미리보기·반영 결과예요. 누르면 그때 바뀐 내용을 볼 수 있어요.', body: uploadList(st.history) });
  }

  /* ── 그리기 ── */
  GP.renderAdmin = function (side, view, rib, top) {
    const s = S();
    let [id, param] = String(s.route || 'admin').split(':');
    if (!['admin', 'admin-ds', 'admin-preview', 'admin-history'].includes(id)) { id = 'admin'; s.route = 'admin'; history_replace('admin'); }
    param = String(s.route).split(':').slice(1).join(':');
    const active = id === 'admin-ds' ? param : id === 'admin-preview' ? (st.previews[param] || {}).dataset || 'admin-history' : id;
    side.innerHTML = sidebar(active);
    rib.querySelector('.mode').outerHTML = GP.modeChip();
    if (st.edit && (id !== 'admin-ds' || st.edit.ds !== param)) st.edit = null;   // 그 데이터 화면을 떠나면 패널을 닫는다
    view.className = id === 'admin-ds' ? 'view wide adm-ds' : 'view wide';
    view.innerHTML = id === 'admin-ds' ? dataset(param) : id === 'admin-preview' ? preview(param) : id === 'admin-history' ? history() : overview();
    document.title = 'GrowPath · 관리자';
    const f = view.querySelector('#admFile');
    if (f) f.addEventListener('change', () => upload(param, f.files && f.files[0]));
    const q = view.querySelector('#admQ');
    if (q) q.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) GP.act['adm-q'](param); });
    const bk = view.querySelector('#admBulk');
    if (bk) bk.addEventListener('toggle', () => { st.bulk = bk.open; });
    const tb = view.querySelector('.adm-tbl');
    if (tb) tb.addEventListener('keydown', e => { const tr = e.target.closest('tr[data-act]'); if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tr.click(); } });
    bindPanel(view.querySelector('.adm-panel'));
    GP.refresh();
    if (top) window.scrollTo(0, 0);
  };
  const history_replace = r => { try { window.history.replaceState(null, '', '#' + r); } catch (e) { /* 무시 */ } };
  const prevReset = GP.onDataReset;
  GP.onDataReset = () => { if (prevReset) prevReset(); Object.assign(st, { tab: {}, q: {}, page: {}, cache: {}, overview: null, previews: {}, filter: 'all', history: null, busy: false, edit: null, pending: null, bulk: false }); };
})();

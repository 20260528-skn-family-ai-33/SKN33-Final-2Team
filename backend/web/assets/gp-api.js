/* GrowPath 5차 목업 · API 호출 모음 (설계서 v1.7 /api/v1)
   화면 코드는 서버를 직접 부르지 않고 이 파일의 함수만 쓴다. 나중에 React 로 옮길 때도 이 파일을 그대로 쓸 수 있게
   DOM·화면 상태를 건드리지 않는다(입력 → fetch → JSON 또는 ApiErr).
   - 오류는 서버 형식 {error: {code, message, hint, retryable, kind, cause, raw}} 를 ApiErr 로 바꿔 던진다
   - 오래 걸리는 작업은 'Prefer: respond-async' 로 보내 202 {jobId} 를 받고, job() 으로 끝날 때까지 기다린다 */
(function () {
  'use strict';
  const BASE = '/api/v1';

  class ApiErr extends Error {
    constructor(status, payload) {
      const p = payload || {};
      super(p.raw || p.message || `HTTP ${status}`);
      this.name = 'ApiErr'; this.status = status; this.payload = p;
    }
  }

  async function call(method, path, body, opts) {
    opts = opts || {};
    const headers = {};
    let data;
    if (body instanceof FormData) data = body;
    else if (body !== undefined) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(body); }
    if (opts.async) headers.Prefer = 'respond-async';
    let r;
    try {
      r = await fetch(BASE + path, { method, headers, body: data, credentials: 'same-origin', cache: 'no-store', signal: opts.signal });
    } catch (e) {
      if (e && e.name === 'AbortError') throw e;
      throw new ApiErr(0, { code: 'SERVER', kind: 'server', message: 'AI 서버에 연결하지 못했어요', cause: '서버(목업_실행.cmd)에 연결하지 못했어요', hint: '서버가 켜져 있는지 확인해 주세요', raw: String(e && e.message || e), retryable: true });
    }
    if (r.status === 204) return null;
    let j = null;
    try { j = await r.json(); } catch (e) { /* 본문 없음 */ }
    if (!r.ok) throw new ApiErr(r.status, (j && j.error) || { code: 'HTTP_' + r.status, kind: 'other', message: '요청을 처리하지 못했어요', raw: `HTTP ${r.status}` });
    if (r.status === 202 && j && j.jobId && opts.wait !== false && opts.async) return job(j.jobId, opts);
    return j;
  }

  /* 작업이 끝날 때까지 기다린다(서버가 최대 10초씩 붙잡았다가 응답). 실패면 ApiErr, 멈추면 AbortError */
  async function job(id, opts) {
    opts = opts || {};
    for (;;) {
      const v = await call('GET', `/jobs/${encodeURIComponent(id)}?wait=10`, undefined, { signal: opts.signal });
      if (opts.onProgress) opts.onProgress(v);
      if (v.status === 'running') continue;
      if (v.status === 'done') return v.result || {};
      const e = v.error || {};
      if (v.status === 'cancelled') { const a = new Error('사용자가 멈췄어요'); a.name = 'AbortError'; throw a; }
      throw new ApiErr(502, { code: e.code, kind: e.kind, message: e.user, cause: e.text, hint: e.hint, raw: e.raw, retryable: e.retryable });
    }
  }

  const enc = encodeURIComponent;
  const API = window.GPAPI = {
    ApiErr, call, job,
    get: (p, o) => call('GET', p, undefined, o), post: (p, b, o) => call('POST', p, b === undefined ? {} : b, o),
    put: (p, b, o) => call('PUT', p, b, o), patch: (p, b, o) => call('PATCH', p, b, o), del: (p, o) => call('DELETE', p, undefined, o),
    cancelJob: id => call('POST', `/jobs/${enc(id)}/cancel`, {}),

    /* 인증·내 정보 (API-01~08) */
    accounts: () => API.get('/demo/accounts'),
    login: (employeeNo, password, keepSignedIn) => API.post('/auth/login', { employeeNo, password, keepSignedIn }),
    logout: () => API.post('/auth/logout'),
    me: () => API.get('/me'),
    profile: () => API.get('/me/profile'),
    saveSelf: body => API.put('/me/profile/self', body),
    revertSelf: () => API.del('/me/profile/self'),
    consent: (period, consent) => API.put(`/me/evaluations/${enc(period)}/consent`, { consent }),
    goals: () => API.get('/me/goal-suggestions'),
    goalsRegenerate: () => API.post('/me/goal-suggestions/regenerate'),
    workspace: () => API.get('/me/workspace'),

    /* AI 모델·시연 도구 (API-10~12) */
    providers: () => API.get('/ai/providers'),
    setProvider: provider => API.put('/me/ai-provider', { provider }),
    aiStatus: provider => API.get(`/ai/status?provider=${enc(provider)}`),
    aiLog: () => API.get('/ai/log'),
    demoSettings: body => API.put('/me/demo-settings', body),
    demoReset: () => API.post('/demo/reset'),
    demoJump: stage => API.post('/demo/jump', { stage }),

    /* 새 로드맵 작성 (API-14~35) */
    draftCurrent: () => API.get('/drafts/current'),
    draftCreate: body => API.post('/drafts', body),
    draftPatch: (id, body) => API.patch(`/drafts/${enc(id)}`, body),
    draftDelete: id => API.del(`/drafts/${enc(id)}`),
    draftGet: id => API.get(`/drafts/${enc(id)}/options`),
    changesApply: (id, kind) => API.post(`/drafts/${enc(id)}/changes/apply`, { kind }),
    changesRevert: (id, kind) => API.post(`/drafts/${enc(id)}/changes/revert`, { kind }),
    projectFile: (id, file) => { const f = new FormData(); f.append('file', file, file.name); return call('POST', `/drafts/${enc(id)}/project-file`, f); },
    projectClear: id => API.del(`/drafts/${enc(id)}/project-file`),
    projectSummary: (id, skipImages) => API.post(`/drafts/${enc(id)}/project-file/summary`, { skipImages: !!skipImages }, { async: true, wait: false }),
    assessment: id => API.post(`/drafts/${enc(id)}/assessment`, {}, { async: true, wait: false }),
    diagnosis: id => API.post(`/drafts/${enc(id)}/diagnosis`, {}, { async: true, wait: false }),
    overrides: (id, body) => API.put(`/drafts/${enc(id)}/diagnosis/overrides`, body),
    optionsStart: id => API.post(`/drafts/${enc(id)}/options`),
    optionRetry: (id, pid) => API.post(`/drafts/${enc(id)}/options/${enc(pid)}/retry`),
    acceptPartial: id => API.post(`/drafts/${enc(id)}/options/accept-partial`),
    regenerate: (id, pid, request) => API.post(`/drafts/${enc(id)}/options/${enc(pid)}/regenerate`, { request }),
    supportRetry: (id, perspective) => API.post(`/drafts/${enc(id)}/options/support/retry`, { perspective }),
    select: (id, perspective) => API.post(`/drafts/${enc(id)}/selection`, { perspective }),
    confirm: id => API.post(`/drafts/${enc(id)}/confirm`),

    /* 내 로드맵·점검·보고서 (API-36~52) */
    plan: id => API.get(`/plans/${enc(id)}`),
    progress: (id, act, body) => API.put(`/plans/${enc(id)}/activities/${enc(act)}/progress`, body),
    attach: (id, act, file) => { const f = new FormData(); f.append('file', file, file.name); return call('POST', `/plans/${enc(id)}/activities/${enc(act)}/attachments`, f); },
    archive: id => API.post(`/plans/${enc(id)}/archive`),
    resume: id => API.post(`/plans/${enc(id)}/resume`),
    revise: (id, body) => API.post(`/plans/${enc(id)}/revisions`, body, { async: true, wait: false }),
    reviseSupportRetry: id => API.post(`/plans/${enc(id)}/revisions/support/retry`, {}, { async: true, wait: false }),
    acceptRevision: rid => API.post(`/revisions/${enc(rid)}/accept`),
    dropRevision: rid => API.del(`/revisions/${enc(rid)}`),
    commentRead: (id, cid) => API.post(`/plans/${enc(id)}/comments/${enc(cid)}/read`),
    savePost: (id, body) => API.put(`/plans/${enc(id)}/post-assessment`, body),
    makeReport: id => API.post(`/plans/${enc(id)}/reports`, {}, { async: true, wait: false }),
    postDeep: id => API.post(`/plans/${enc(id)}/post-assessment/deep`, {}, { async: true, wait: false }),  // 설계서 밖 추가(10/23) · 사후 심화 질문 만들기
    confirmReport: rid => API.post(`/reports/${enc(rid)}/confirm`),

    /* 학습 자료·자격증·규정 (API-22, 53, 54) */
    certifications: () => API.get('/certifications'),
    resources: q => API.get('/resources?' + new URLSearchParams(q).toString()),
    resourcesLookup: ids => API.post('/resources/lookup', { ids }),
    regSets: () => API.get('/regulations/sets'),
    skillMap: () => API.get('/skills/map'),  // 설계서 밖 추가(10/23) · 검토·확정 화면 스킬 지도(스킬 태그 + 선수 관계 초안)
    regLookup: ids => API.post('/regulations/lookup', { ids }),
    ask: (question, history, signal) => call('POST', '/assistant/ask', { question, history }, { async: true, signal }),

    /* 부서장 (API-55~59) */
    team: () => API.get('/team/members'),
    teamMember: uid => API.get(`/team/members/${enc(uid)}/plans`),
    teamComment: (pid, body) => API.post(`/team/plans/${enc(pid)}/comments`, body),
    teamCommentEdit: (pid, cid, body) => API.patch(`/team/plans/${enc(pid)}/comments/${enc(cid)}`, body),  // 설계서 밖 추가(10/23) · 삭제 API 없음

    /* 관리자 (인적·규정·교육 데이터 엑셀·CSV) */
    admin: {
      overview: () => API.get('/admin/overview'),
      rows: (ds, sheet, q) => API.get(`/admin/datasets/${enc(ds)}/rows?` + new URLSearchParams(Object.assign({ sheet }, q || {})).toString()),
      edit: (ds, rows, o) => API.post(`/admin/datasets/${enc(ds)}/edit`, Object.assign({ rows }, o || {})),
      preview: (ds, file, sheet) => { const f = new FormData(); f.append('file', file, file.name); if (sheet) f.append('sheet', sheet); return call('POST', `/admin/datasets/${enc(ds)}/preview`, f); },
      upload: uploadId => API.get(`/admin/uploads/${enc(uploadId)}`),
      apply: (uploadId, goalMode) => API.post(`/admin/uploads/${enc(uploadId)}/apply`, { goalMode: goalMode || null }),
      discard: uploadId => API.del(`/admin/uploads/${enc(uploadId)}`),
      uploads: ds => API.get(`/admin/uploads?dataset=${enc(ds || '')}`),
      goalsAll: mode => API.post('/admin/goal-suggestions/regenerate-all', { mode: mode || null }),
      buildIndex: provider => API.post('/admin/regulations/index', { provider }, { async: true, wait: false }),
      downloadUrl: (ds, fmt, sheet) => `${BASE}/admin/datasets/${enc(ds)}/export?` + new URLSearchParams({ format: fmt, sheet: sheet || '' }).toString(),
      templateUrl: (ds, fmt, sheet) => `${BASE}/admin/datasets/${enc(ds)}/template?` + new URLSearchParams({ format: fmt, sheet: sheet || '' }).toString()
    }
  };
})();

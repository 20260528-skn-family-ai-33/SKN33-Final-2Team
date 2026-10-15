/* GrowPath 4차 목업 (Claude) · 내 정보 (10/15)
   로그인한 직원이 가상 사내 DB(employees.js)에 있는 자기 정보를 본다. 좌측 위 계정 칸이나 좌측 메뉴 '내 정보'로 들어온다.
   인사 정보·권한(감독 그룹)은 읽기 전용, 본인 입력 프로필과 평정의 학습 사용 동의는 직접 고친다(10/15 사용자 결정).
   고친 값은 이 브라우저에만 둔다(gp4c.me.<직원 id> · 엑셀 원본 그대로). 목표 후보 제안(진단 에이전트)이 바로 이 값을 쓴다 */
(function () {
  'use strict';
  const GP = window.GP, D = GP.D, AI = GP.AI, P = GP.P, { esc, icon } = GP;
  const S = () => GP.S, scr = GP.screens;
  /* 본인 입력 목록: [키, 이름, 입력 예시]. 입력 상태(input_status)는 reported 입력함 / none_confirmed 없음 확인 / unprovided 입력 안 함 */
  const LISTS = [['tech', '기술 스택', '예: Python 2년'], ['certs', '보유 자격', '예: SQLD (2019-09-06 취득)'], ['learning', '교육 이력', '예: 생성형 AI 활용 과정 (2025, 16시간)'], ['projects', '프로젝트', '예: 업무 조회 API 개선 (백엔드 기능 구현 담당)']];
  const ROLE = { employee: '일반 사용자', hr_admin: '시스템 관리자(인사 관리)' };
  const none = '<span class="muted">없음</span>';
  const val = v => (v == null || v === '' ? none : esc(v));

  /* ── 인사 정보 (읽기 전용) ── */
  const hrCard = e => `<div class="card"><div class="sec-h"><h2 class="st">인사 정보</h2><span class="tag line">${icon('lock')}사내 인사 DB · 읽기 전용</span></div>
    <dl class="kv me-kv">
      <dt>이름</dt><dd>${esc(e.name)}</dd>
      <dt>사번</dt><dd class="num">${esc(e.code)}</dd>
      <dt>직원 구분</dt><dd>${[e.empGroup, e.status].filter(Boolean).map(esc).join(' · ') || none}</dd>
      <dt>입사일</dt><dd>${val(e.hireDate)}</dd>
      <dt>소속</dt><dd>${[e.parentDept, e.dept].filter(Boolean).map(esc).join(' › ') || none}</dd>
      <dt>직급</dt><dd>${val(e.grade)}${e.gradeSince ? ` <span class="small muted">· ${esc(e.gradeSince)} 임용</span>` : ''}</dd>
      <dt>직종·직렬</dt><dd>${val(e.jobFamily)}</dd>
      <dt>직위·보직</dt><dd>${val(e.position)}</dd>
      <dt>직무</dt><dd>${val(e.job)}</dd>
      <dt>주요 담당 업무</dt><dd>${val(e.task)}</dd>
      <dt>현재 근무</dt><dd>${e.validFrom ? `${esc(e.validFrom)}부터${e.changeReason ? ` · ${esc(e.changeReason)}` : ''}` : none}</dd>
    </dl>
    <p class="small muted me-foot">인사 정보는 직접 고칠 수 없어요. 다르면 인사 담당 부서(인재경영실 · 가상)에 정정을 요청해 주세요.</p></div>`;

  /* ── 권한·공개 범위 (감독 그룹 · 읽기 전용) ── */
  const permCard = e => {
    const sup = GP.isSup(e), ms = GP.members(e), my = e.mySupervisor;
    return `<div class="card"><div class="sec-h"><h2 class="st">권한·공개 범위</h2><span class="tag line">${icon('lock')}감독 그룹 · 인사 관리자가 정함</span></div>
    <dl class="kv me-kv">
      <dt>서비스 역할</dt><dd>${esc(ROLE[e.role] || e.role || '')}${e.role === 'hr_admin' ? ' <span class="small muted">· 관리자 기능은 아직 없어요</span>' : ''}</dd>
      <dt>부서장 권한</dt><dd>${sup ? `있음 · 감독 그룹 ‘${esc(e.supGroup.name)}’<br><span class="small muted">볼 수 있는 직원 ${ms.length}명: ${ms.map(m => esc(m.name)).join(', ')}</span> <button class="link" data-go="m-list">소속 직원 계획 ${icon('right')}</button>` : '없음'}</dd>
      <dt>내 계획이 올라가는 그룹</dt><dd>${e.planGroup ? esc(e.planGroup.name) : `없음 <span class="small muted">· 내 계획은 나만 봐요</span>`}</dd>
      <dt>내 계획을 보는 부서장</dt><dd>${my ? `${esc(my.name)} <span class="small muted">· 사번 ${esc(my.code)}</span>` : '없음'}</dd>
    </dl>
    <p class="small muted me-foot">${my ? `${esc(my.name)} 님은 내 확정 로드맵, 활동 진행 상태, 결과 보고서를 볼 수 있어요. ` : ''}활동 메모·첨부, 작성 중인 로드맵, 본인 입력 정보는 부서장 화면에 보이지 않아요.</p></div>`;
  };

  /* ── 본인 입력 정보 (보기 / 고치기) ── */
  const listView = (e, k) => {
    const items = e[k] || [], st = e.profile && e.profile.inputStatus ? e.profile.inputStatus[k] : null;
    if (items.length) return `<ul class="plain-list me-list">${items.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
    return `<span class="muted">${st === 'none_confirmed' ? '없음(확인함)' : '입력 안 함'}</span>`;
  };
  const selfView = e => {
    const p = e.profile || {};
    return `${e.profile ? '' : P.note('본인 입력 프로필이 아직 없어요. ‘수정’을 눌러 업무 설명부터 채우면 목표 후보를 내 업무에 맞춰 받을 수 있어요.')}
      <dl class="kv me-kv">
      <dt>업무 설명</dt><dd>${val(p.workDesc)}</dd>
      <dt>경험 요약</dt><dd>${val(p.expSummary)}</dd>
      <dt>개발 경험</dt><dd>${p.devYears == null ? none : `${esc(p.devYears)}년`}</dd>
      ${LISTS.map(([k, l]) => `<dt>${l}</dt><dd>${listView(e, k)}</dd>`).join('')}
    </dl>`;
  };
  const selfForm = ed => `<div class="me-form">
    <div class="field"><label>업무 설명 <span class="muted small">지금 하는 일과 AI로 줄이고 싶은 일</span></label><textarea class="textarea sm" data-bind="meEdit.workDesc" maxlength="500" rows="3" aria-label="업무 설명" placeholder="예: 사내 업무 시스템의 조회 기능을 유지보수해요. 규정 문서에서 근거를 찾는 데 시간이 오래 걸려요.">${esc(ed.workDesc)}</textarea></div>
    <div class="field"><label>경험 요약 <span class="muted small">선택</span></label><textarea class="textarea sm" data-bind="meEdit.expSummary" maxlength="500" rows="3" aria-label="경험 요약" placeholder="예: 백엔드 개발 경험은 있지만 RAG는 직접 구현해 본 적이 없어요.">${esc(ed.expSummary)}</textarea></div>
    <div class="field"><label>개발 경험 <span class="muted small">선택 · 0.5년 단위</span></label><div class="unit"><input class="input num" type="number" min="0" max="50" step="0.5" data-bind="meEdit.devYears" value="${esc(ed.devYears)}" placeholder="예: 1.5" aria-label="개발 경험 연수"><span>년</span></div></div>
    ${LISTS.map(([k, l, ph]) => `<div class="field"><label>${l} <span class="muted small">선택 · 한 줄에 하나씩</span></label>
      <textarea class="textarea sm" data-bind="meEdit.${k}" maxlength="800" rows="3" aria-label="${l}" placeholder="${esc(ph)}">${esc(ed[k])}</textarea>
      <label class="check sm"><input type="checkbox" data-me-none="${k}" ${ed[k + 'None'] ? 'checked' : ''}>없어요 (없음을 확인함)</label></div>`).join('')}
    <p class="err" id="meErr" role="alert" hidden></p></div>`;
  const lines = t => String(t || '').split('\n').map(x => x.trim()).filter(Boolean).slice(0, 20);
  /* 고친 값이 사내 DB 값과 같으면 '직접 고침'으로 두지 않는다 */
  const selfOf = e => ({ profile: e.profile || null, certs: e.certs || [], learning: e.learning || [], tech: e.tech || [], projects: e.projects || [] });

  GP.act['me-edit'] = () => {
    const e = GP.me(), p = e.profile || {}, st = p.inputStatus || {};
    const ed = { workDesc: p.workDesc || '', expSummary: p.expSummary || '', devYears: p.devYears == null ? '' : p.devYears };
    LISTS.forEach(([k]) => { ed[k] = (e[k] || []).join('\n'); ed[k + 'None'] = st[k] === 'none_confirmed'; });
    S().meEdit = ed; GP.save(); GP.render(false);
  };
  GP.act['me-cancel'] = () => { S().meEdit = null; GP.save(); GP.render(false); };
  GP.act['me-save'] = () => {
    const e = GP.me(), ed = S().meEdit; if (!ed) return;
    const err = m => { const el = document.getElementById('meErr'); if (el) { el.textContent = m; el.hidden = false; el.scrollIntoView({ block: 'nearest' }); } };
    const wd = String(ed.workDesc || '').trim(), ex = String(ed.expSummary || '').trim();
    const yrs = ed.devYears === '' || ed.devYears == null ? null : Number(ed.devYears);
    if (yrs != null && !(yrs >= 0 && yrs <= 50)) return err('개발 경험은 0~50년 사이로 적거나 비워 주세요.');
    const lists = Object.fromEntries(LISTS.map(([k]) => [k, lines(ed[k])]));
    const any = wd || ex || yrs != null || LISTS.some(([k]) => lists[k].length || ed[k + 'None']);
    /* 사내 DB 규칙: 본인 입력 프로필이 있으면 업무 설명은 필수 */
    if (any && !wd) return err('업무 설명을 적어 주세요. 본인 입력 정보를 저장할 때 업무 설명은 꼭 있어야 해요.');
    const status = k => (lists[k].length ? 'reported' : ed[k + 'None'] ? 'none_confirmed' : 'unprovided');
    const self = { profile: any ? { workDesc: wd, expStatus: ex ? 'reported' : 'unprovided', expSummary: ex || null, devYears: yrs, inputStatus: { certs: status('certs'), learning: status('learning'), projects: status('projects'), tech: status('tech') } } : null,
      certs: lists.certs, learning: lists.learning, tech: lists.tech, projects: lists.projects };
    const x = GP.meEdits(e.id) || {}, db = selfOf(GP.acct(e.id));
    if (JSON.stringify(self) === JSON.stringify(db)) delete x.self; else x.self = self;
    x.at = D.today;
    GP.setMeEdits(e.id, x);
    S().meEdit = null; GP.save(); GP.render(false);
    GP.toast('본인 입력 정보를 저장했어요 · 새 로드맵 작성의 목표 후보에 반영돼요');
  };
  GP.act['me-revert'] = () => GP.sheet('<p style="margin-top:0">직접 고친 본인 입력 정보(업무 설명·경험·기술 스택·자격·교육·프로젝트)를 지우고 사내 DB 값으로 되돌려요. 평정의 학습 사용 동의는 그대로예요.</p>',
    { title: '사내 DB 값으로 되돌릴까요?', foot: '<button class="btn line" data-act="sheet-close">취소</button><button class="btn pri" data-act="me-revert-ok">되돌리기</button>' });
  GP.act['me-revert-ok'] = () => {
    const e = GP.me(), x = GP.meEdits(e.id) || {}; delete x.self;
    GP.setMeEdits(e.id, x); GP.closeSheet(); GP.render(false); GP.toast('사내 DB 값으로 되돌렸어요');
  };

  /* ── 근무성적평정 (본인 입력 평가) · 학습 사용 동의만 고친다 ── */
  const evalCard = e => {
    const ev = e.evals || [];
    return `<div class="card"><div class="sec-h"><h2 class="st">근무성적평정</h2><span class="tag line">본인 입력 평가</span></div>
      ${ev.length ? `<div class="list me-evals">${ev.map(v => `<div class="li"><div class="tx"><b>${esc(v.period)} · ${esc(v.grade)}${v.score ? ` · ${esc(v.score)}` : ''}</b><small>${esc(v.title)}</small></div>
        <label class="check sm"><input type="checkbox" data-me-consent="${esc(v.period)}" ${v.consent ? 'checked' : ''}>학습 사용 동의</label></div>`).join('')}</div>` : '<p class="muted small" style="margin:0">등록된 평정이 없어요.</p>'}
      <p class="small muted me-foot">학습 사용에 동의한 평정만 목표 후보 제안에 참고로 넘겨요. 등급·점수로 목표를 정하거나 문장에 쓰지 않아요. 동의는 언제든 바꿀 수 있어요.</p></div>`;
  };

  /* ── 이 정보가 쓰이는 곳 ── */
  const useCard = e => `<div class="card flat"><h2 class="st">이 정보가 쓰이는 곳</h2><div class="stack">
    <div class="row top">${icon('spark')}<span><b>목표 후보 제안</b> · 진단 에이전트가 직급·부서·직무·담당 업무와 본인 입력 정보, 학습 사용에 동의한 평정만 보고 목표 후보 3개를 제안해요. 고치면 새 로드맵 작성에서 후보를 새로 받아요. <button class="link" data-go="${GP.newRoute ? GP.newRoute() : 'new-goal'}">새 로드맵 작성 ${icon('right')}</button></span></div>
    <div class="row top">${icon('scale')}<span><b>사내 생활 도우미·지원 조건 확인</b> · 규정 에이전트가 직원 구분·직급을 봐요. ${AI.regApplies() ? `${esc(e.empGroup || '')} 직원이라 등록된 ${esc(AI.regSet().label)}(${esc(AI.regSet().regs.filter(r => !r.overseas).map(r => r.name).slice(0, 3).join('·'))} 등)에서 근거를 찾아요. 국외근무 규정은 국외근무를 물을 때만 봐요.` : `등록된 규정은 ${esc(Object.keys(AI.REG_SETS).join('·'))} 대상이라 ${esc(e.empGroup || '')} 직원에게는 ‘적용 대상 아님’으로 안내해요. ${esc(e.empGroup || '')} 대상 규정은 확보한 뒤 등록할 예정이에요.`}</span></div>
  </div></div>`;

  scr.me = {
    nav: 'me', title: '내 정보', width: 'wide',
    render() {
      const e = GP.me(), ed = S().meEdit;
      return P.page({
        eyebrow: '내 정보', title: `${esc(e.name)} 님의 정보`,
        lead: '인사 정보와 권한은 사내 인사 DB(가상)에서 가져와 고칠 수 없어요. 본인 입력 정보와 평정의 학습 사용 동의는 직접 고칠 수 있고, 목표 후보 제안에 바로 쓰여요.',
        body: `<div class="me-page">${hrCard(e)}
          <div class="card"><div class="sec-h"><h2 class="st">본인 입력 정보</h2><span class="tag ${e.edited ? 'acc' : 'line'}">${e.edited ? `직접 고침${e.editedAt ? ` · ${esc(e.editedAt)}` : ''}` : '사내 DB 값'}</span>${ed ? '' : `<button class="btn line sm me-ed" data-act="me-edit">${icon('edit')}수정</button>`}</div>
            ${ed ? selfForm(ed) : selfView(e)}
            ${ed ? '<div class="actions me-act"><button class="btn pri" data-act="me-save">저장</button><button class="btn line" data-act="me-cancel">취소</button></div>' : ''}
            <p class="small muted me-foot">고친 내용은 이 브라우저에만 저장돼요(시연 · 사내 DB 원본은 그대로).${e.edited && !ed ? ' <button class="link quiet" data-act="me-revert">사내 DB 값으로 되돌리기</button>' : ''}</p></div>
          ${evalCard(e)}${permCard(e)}${useCard(e)}</div>`
      });
    },
    after(root) {
      /* '없어요' 확인란: 고치는 중인 값에만 둔다(저장을 눌러야 반영) */
      root.querySelectorAll('[data-me-none]').forEach(c => c.addEventListener('change', () => { const ed = S().meEdit; if (ed) { ed[c.dataset.meNone + 'None'] = c.checked; GP.save(); } }));
      /* 학습 사용 동의: 바로 저장. 사내 DB 값과 같아지면 고친 기록에서 뺀다 */
      root.querySelectorAll('[data-me-consent]').forEach(c => c.addEventListener('change', () => {
        const e = GP.me(), per = c.dataset.meConsent, db = (GP.acct(e.id).evals || []).find(v => v.period === per);
        const x = GP.meEdits(e.id) || {}, cs = x.consent || {};
        if (db && db.consent === c.checked) delete cs[per]; else cs[per] = c.checked;
        x.consent = cs; GP.setMeEdits(e.id, x);
        GP.toast(c.checked ? '이 평정을 목표 후보 제안에 참고하도록 동의했어요' : '이 평정은 목표 후보 제안에 쓰지 않아요');
      }));
    }
  };
})();

/* GrowPath 5차 목업 (Claude) · 스킬 지도 — 검토·확정 화면과 내 로드맵(확정한 로드맵) 화면, 요약 박스(기간·시간·비용) 바로 아래
   (2026-10-23 팀 합의: 3안 비교가 아니라 검토·확정에서 보여 줌 · 사용자: 확정한 로드맵 화면에도)
   생활코딩 WEBn 지식 지도(seomal)처럼 점과 화살표로 그린다. 시안(시안_3안_마인드맵/3안_마인드맵_시안_20261022.html '스킬 지도 + 선수 관계')을 옮긴 것
   - 점 = 팀 DB 스킬 태그 하나(36개), 점 크기 = 그 스킬이 붙은 강좌·도서·자격 수, 이름 아래 = 분야
   - 화살표 = 선수 관계(먼저 배울 스킬 → 다음 스킬). 아직 팀 DB에 없어 서버가 초안 파일(db/team_request/skill_prerequisites.csv · 가정)을 읽어 준다
     (GET /skills/map · 설계서 밖). 팀 DB에 표가 생기면 서버(app/skillmap.py)만 바꾸고 이 파일은 그대로 쓴다
   - 이 로드맵이 다루는 스킬: 자료 활동은 자료에 붙은 팀 DB 스킬, 직접 수행 과제는 로드맵 에이전트가 고른 스킬(a.skills · 1~3개 · 10/23).
     과제에 스킬이 없으면(예전 계획·에이전트가 빠뜨림) 같은 단계(없으면 앞 단계, 그래도 없으면 뒤 단계) 자료의 스킬을 따른다('추정' 표시는 하지 않음 · 사용자 결정).
     그 스킬을 다루는 활동의 주차를 꼬리표로 단다(예: 1~6주차)
   - 로드맵에 없는 스킬은 따로 표시하지 않는다(10/23 사용자 결정: '먼저 필요' 표시 뺌 · 선수 관계는 화살표로 보임)
   - 배치는 이어진 스킬끼리 모이는 힘 배치. 시작 자리를 정해 두어 매번 같은 모양이 나온다 */
(function () {
  'use strict';
  const GP = window.GP, P = GP.P, API = GP.API, { esc, icon } = GP;
  const SM = GP.skillMap = {};
  let data = null, loading = null, loadErr = null, layout = null, plan = null, picked = null, big = null;

  /* ── 자료 읽기 ── */
  SM.load = function () {
    if (data) { center(); return null; }
    if (loading) return loading;
    loading = API.skillMap()
      .then(d => { data = d; loadErr = null; layout = null; })
      .catch(err => { loadErr = err; })
      .finally(() => { loading = null; paint(); });
    return loading;
  };
  GP.act['sm-retry'] = () => { loadErr = null; paint(); SM.load(); };

  // 글자 폭은 캔버스로 잰다(SVG 는 자동 줄바꿈이 없음)
  const cv = document.createElement('canvas').getContext('2d');
  const FONT = () => getComputedStyle(document.body).fontFamily;
  const tw = (t, size, weight) => { cv.font = `${weight || 400} ${size}px ${FONT()}`; return cv.measureText(t).width; };
  function wrap(text, maxW, size, weight, maxLines) {
    const lines = [];
    let cur = '';
    String(text).split(' ').forEach(w => { const t = cur ? `${cur} ${w}` : w; if (!cur || tw(t, size, weight) <= maxW) cur = t; else { lines.push(cur); cur = w; } });
    if (cur) lines.push(cur);
    if (lines.length > maxLines) {
      lines.length = maxLines;
      let last = lines[maxLines - 1];
      while (last && tw(last + '…', size, weight) > maxW) last = last.slice(0, -1);
      lines[maxLines - 1] = last + '…';
    }
    return lines;
  }

  /* ── 선수 관계 ── */
  const rel = () => {
    if (rel.d === data) return rel.v;
    const parents = {}, kids = {};
    data.prerequisites.forEach(([a, b]) => { (parents[b] = parents[b] || []).push(a); (kids[a] = kids[a] || []).push(b); });
    rel.d = data; rel.v = { parents, kids };
    return rel.v;
  };

  /* ── 이 로드맵이 다루는 스킬 ── */
  function coverOf(pl) {
    const byName = Object.fromEntries(data.skills.map(s => [s.name, s.id]));
    const resSkills = a => ((P.resOf(a.res) || {}).skills || []).map(n => byName[n]).filter(Boolean);
    const ofStage = n => [...new Set(pl.acts.filter(a => a.stage === n && a.res).flatMap(resSkills))];
    const inherit = n => { for (const s of [n, n - 1, n - 2, n - 3, n + 1, n + 2, n + 3]) { if (s < 1 || s > 4) continue; const k = ofStage(s); if (k.length) return k; } return []; };
    const taskSkills = a => { const ids = [...new Set((a.skills || []).map(n => byName[n]).filter(Boolean))]; return ids.length ? ids : inherit(a.stage); };
    const cov = new Map();
    pl.acts.forEach(a => (a.res ? resSkills(a) : taskSkills(a)).forEach(id => { if (!cov.has(id)) cov.set(id, []); cov.get(id).push({ a }); }));
    return cov;
  }
  /* 주차 꼬리표: 그 스킬을 다루는 활동들의 주차를 이어 붙인다(1,2,3,5,6 → '1~3·5~6주차'). 세 덩어리 이상이면 처음~끝.
     계획에 주차가 없으면(옛 기록) 단계로 대신한다 */
  const actWeek = a => (a.wFrom === a.wTo ? `${a.wFrom}주차` : `${a.wFrom}~${a.wTo}주차`);
  function weeksOf(list) {
    if (list.some(x => x.a.wFrom == null || x.a.wTo == null)) return `${[...new Set(list.map(x => x.a.stage))].sort().join('·')}단계`;
    const ws = [...new Set(list.flatMap(x => Array.from({ length: x.a.wTo - x.a.wFrom + 1 }, (_, i) => x.a.wFrom + i)))].sort((p, q) => p - q);
    const runs = [];
    ws.forEach(w => { const r = runs[runs.length - 1]; if (r && w === r[1] + 1) r[1] = w; else runs.push([w, w]); });
    const fmt = ([a, b]) => (a === b ? `${a}` : `${a}~${b}`);
    return `${runs.length > 2 ? fmt([runs[0][0], runs[runs.length - 1][1]]) : runs.map(fmt).join('·')}주차`;
  }

  /* ── 배치(한 번만 계산) ── */
  function place() {
    if (layout && layout.d === data) return layout;
    const nodes = data.skills.map(s => ({ id: s.id, name: s.name, cat: s.category, n: s.resources, r: 5 + Math.sqrt(s.resources) * 0.6, lines: wrap(s.name, 116, 11.5, 650, 2) }));
    const byId = Object.fromEntries(nodes.map(n => [n.id, n])), { parents, kids } = rel();
    nodes.forEach(n => { n.bw = Math.max(n.r * 2, ...n.lines.map(l => tw(l, 11.5, 650)), tw(n.cat, 10.5)) + 6; n.bh = n.r * 2 + 6 + n.lines.length * 15 + 13; });
    // 처음 자리: 뿌리(선수 없는 스킬)마다 아래 스킬 수만큼 부채꼴을 나누고, 선수 깊이만큼 바깥으로
    const roots = nodes.filter(n => !parents[n.id]).map(n => n.id), tkids = {}, seen = new Set(roots), queue = roots.slice();
    while (queue.length) { const u = queue.shift(); (kids[u] || []).forEach(v => { if (!seen.has(v)) { seen.add(v); (tkids[u] = tkids[u] || []).push(v); queue.push(v); } }); }
    const leaves = u => ((tkids[u] || []).length ? tkids[u].reduce((s, v) => s + leaves(v), 0) : 1);
    const put = (u, depth, from, to) => {
      const mid = (from + to) / 2, R = 70 + depth * 115; byId[u].x = Math.cos(mid) * R; byId[u].y = Math.sin(mid) * R;
      let f = from; (tkids[u] || []).forEach(v => { const span = (to - from) * leaves(v) / leaves(u); put(v, depth + 1, f, f + span); f += span; });
    };
    roots.sort((a, b) => leaves(b) - leaves(a) || a - b);
    const total = roots.reduce((s, r) => s + leaves(r), 0) || 1;
    let a0 = -Math.PI / 2;
    roots.forEach(r => { const span = 2 * Math.PI * leaves(r) / total; put(r, 0, a0, a0 + span); a0 += span; });
    nodes.forEach((n, i) => { if (n.x == null) { n.x = Math.cos(i) * 300; n.y = Math.sin(i) * 300; } }); // 선수 관계가 순환이라 뿌리에서 닿지 않는 스킬
    const L = data.prerequisites.map(([a, b]) => ({ a: byId[a], b: byId[b] })).filter(l => l.a && l.b);
    const N = 500;
    for (let it = 0; it < N; it++) {
      const alpha = 1 - it / N;
      nodes.forEach(n => { n.fx = -n.x * 0.004; n.fy = -n.y * 0.004; });
      L.forEach(({ a, b }) => { const vx = b.x - a.x, vy = b.y - a.y, d = Math.hypot(vx, vy) || 0.01, f = (d - 105) / d * 0.05; a.fx += vx * f; a.fy += vy * f; b.fx -= vx * f; b.fy -= vy * f; });
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], vx = b.x - a.x, vy = b.y - a.y, d2 = Math.max(vx * vx + vy * vy, 400), d = Math.sqrt(d2), f = 4200 / d2;
        a.fx -= vx / d * f; a.fy -= vy / d * f; b.fx += vx / d * f; b.fy += vy / d * f;
      }
      const lim = 22 * alpha + 1;
      nodes.forEach(n => { n.x += Math.max(-lim, Math.min(lim, n.fx)); n.y += Math.max(-lim, Math.min(lim, n.fy)); });
      // 점 + 아래 글자를 한 상자로 보고 겹치면 바로 떼어 놓는다
      if (it > N * 0.3) for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], ox = (a.bw + b.bw) / 2 + 10 - Math.abs(a.x - b.x);
        const ay = a.y - a.r + a.bh / 2, by = b.y - b.r + b.bh / 2, oy = (a.bh + b.bh) / 2 + 8 - Math.abs(ay - by);
        if (ox > 0 && oy > 0) {
          if (ox / (a.bw + b.bw) < oy / (a.bh + b.bh)) { const s = a.x < b.x ? -1 : 1; a.x += s * ox / 2; b.x -= s * ox / 2; }
          else { const s = ay < by ? -1 : 1; a.y += s * oy / 2; b.y -= s * oy / 2; }
        }
      }
    }
    layout = { d: data, nodes, byId };
    return layout;
  }

  /* ── 그리기 ── */
  function svg(pl) {
    const m = place(), cov = coverOf(pl), on = id => cov.has(id);
    const defs = `<defs>${[['g', '#BDBDB5'], ['on', 'var(--accent)']].map(([k, c]) => `<marker id="sm-${k}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" style="fill:${c}"/></marker>`).join('')}</defs>`;
    const edges = data.prerequisites.map(([a, b]) => {
      const A = m.byId[a], B = m.byId[b]; if (!A || !B) return '';
      const vx = B.x - A.x, vy = B.y - A.y, d = Math.hypot(vx, vy) || 1, ux = vx / d, uy = vy / d, hit = on(a) && on(b);
      return `<line class="sm-e${hit ? ' on' : ''}" marker-end="url(#sm-${hit ? 'on' : 'g'})" x1="${(A.x + ux * (A.r + 2)).toFixed(1)}" y1="${(A.y + uy * (A.r + 2)).toFixed(1)}" x2="${(B.x - ux * (B.r + 5)).toFixed(1)}" y2="${(B.y - uy * (B.r + 5)).toFixed(1)}"/>`;
    }).join('');
    let x1 = -1e9;
    const nodes = m.nodes.map(n => {
      const c = cov.get(n.id), cls = c ? ' cov' : ' off';
      const tagT = c ? weeksOf(c) : '', tagW = tagT ? tw(tagT, 10, 700) + 12 : 0;
      if (tagT) x1 = Math.max(x1, n.x + n.r + 5 + tagW);
      const y0 = n.r + 15;
      return `<g class="sm-n${cls}${picked === n.id ? ' pick' : ''}" data-act="sm-pick" data-arg="${n.id}" transform="translate(${n.x.toFixed(1)},${n.y.toFixed(1)})" role="button" tabindex="0" aria-pressed="${picked === n.id}" aria-label="${esc(n.name)}${c ? ` · 이 로드맵 ${tagT}` : ''}">
        <circle class="dot" r="${n.r.toFixed(1)}"/>${c ? `<circle class="ring" r="${(n.r + 1.5).toFixed(1)}"/>` : ''}
        ${n.lines.map((l, i) => `<text x="0" y="${(y0 + i * 15).toFixed(1)}" text-anchor="middle">${esc(l)}</text>`).join('')}<text class="cat" x="0" y="${(y0 + n.lines.length * 15).toFixed(1)}" text-anchor="middle">${esc(n.cat)}</text>
        ${tagT ? `<g class="tag" transform="translate(${(n.r + 5).toFixed(1)},-8)"><rect width="${tagW.toFixed(1)}" height="16" rx="8"/><text x="${(tagW / 2).toFixed(1)}" y="11.5" text-anchor="middle">${tagT}</text></g>` : ''}</g>`;
    }).join('');
    const b = m.nodes.reduce((o, n) => ({ x0: Math.min(o.x0, n.x - n.bw / 2), y0: Math.min(o.y0, n.y - n.r - 6), x1: Math.max(o.x1, n.x + n.bw / 2), y1: Math.max(o.y1, n.y - n.r + n.bh) }), { x0: 1e9, y0: 1e9, x1: -1e9, y1: -1e9 });
    b.x1 = Math.max(b.x1, x1);
    const pad = 24, W = Math.ceil(b.x1 - b.x0 + pad * 2), H = Math.ceil(b.y1 - b.y0 + pad * 2), fit = !bigNow();
    return { cov, html: `<svg class="sm-svg" viewBox="${(b.x0 - pad).toFixed(1)} ${(b.y0 - pad).toFixed(1)} ${W} ${H}" width="${W}" height="${H}" style="${fit ? `width:100%;max-width:${W}px` : `width:${W}px`};height:auto" role="img" aria-label="스킬 지도: 팀 DB 스킬과 선수 관계(가정), 이 로드맵이 다루는 스킬 표시">${defs}<g>${edges}</g><g>${nodes}</g></svg>` };
  }
  // 넓은 화면은 칸에 맞추고, 좁은 화면은 실제 크기로 두고 옆으로 밀어 본다
  const bigNow = () => (big != null ? big : window.innerWidth <= 900);

  /* 누른 스킬 설명(지도 아래) */
  function info(pl, cov) {
    if (picked == null || !data.skills.some(s => s.id === picked)) return `<p class="small muted">스킬 점을 누르면 이 로드맵에서 몇 주차에 어떤 활동이 다루는지와 선수 관계를 보여 줘요.</p>`;
    const s = data.skills.find(x => x.id === picked), { parents, kids } = rel();
    const names = ids => (ids && ids.length ? ids.map(id => esc((data.skills.find(x => x.id === id) || {}).name || '')).join(', ') : '<span class="muted">없어요</span>');
    const c = cov.get(picked);
    let here = '<span class="muted">이 로드맵에는 없어요.</span>';
    if (c) {
      // 다루는 활동을 주차와 함께. 많으면 앞의 4개만 적고 나머지는 개수로
      const wk = x => (x.a.wFrom != null ? ` (${actWeek(x.a)})` : ''), shown = c.slice(0, 4);
      here = `<b>${weeksOf(c)}</b> · ${shown.map(x => `${esc(x.a.title)}${wk(x)}`).join(', ')}${c.length > shown.length ? ` 외 ${c.length - shown.length}개` : ''}`;
    }
    return `<div class="sm-pick-h"><b>${esc(s.name)}</b><span class="tag">${esc(s.category)}</span><button class="link quiet" data-act="sm-pick" data-arg="${picked}" aria-label="설명 닫기">${icon('x')}</button></div>
      <dl class="kv sm-kv"><dt>이 로드맵</dt><dd>${here}</dd><dt>팀 DB 자료</dt><dd>${s.resources}건에 이 스킬이 붙어 있어요</dd>
        <dt>먼저 배울 스킬</dt><dd>${names(parents[picked])}</dd><dt>다음 스킬</dt><dd>${names(kids[picked])}</dd></dl>`;
  }

  /* 화면 한 칸(검토·확정 = 작성 중 안, 내 로드맵 = 확정한 로드맵). 자료를 아직 안 읽었으면 자리만 두고 after 에서 SM.load().
     다른 로드맵으로 옮기면 누른 스킬은 풀어 둔다 */
  SM.html = function (pl) {
    const key = pl.rid || 'draft';
    if (plan && (plan.rid || 'draft') !== key) picked = null;
    plan = pl;
    const head = n => `<div class="sec-h"><h2 class="st">이 로드맵이 다루는 스킬</h2>${n || ''}</div>`;
    if (loadErr) {
      const msg = (loadErr.payload && (loadErr.payload.message || loadErr.payload.raw)) || loadErr.message || '';
      return `<div class="sec" id="smBox">${head()}<div class="loading">${icon('alert')}<span>스킬 지도를 불러오지 못했어요${msg ? ` · ${esc(msg)}` : ''}</span><button class="btn line sm" data-act="sm-retry">다시 시도</button></div></div>`;
    }
    if (!data) return `<div class="sec" id="smBox">${head()}<div class="loading"><span class="sp"></span><span>스킬 지도를 불러오는 중…</span></div></div>`;
    const g = svg(pl), draft = data.prerequisiteSource !== 'db';
    const sum = `팀 DB 스킬 ${data.skills.length}개 가운데 이 로드맵이 다루는 스킬 <b>${g.cov.size}개</b>를 진하게, 다루는 주차를 꼬리표로 보여 줘요.`;
    return `<div class="sec" id="smBox">${head(`<button class="link quiet" data-act="sm-zoom">${icon(bigNow() ? 'minus' : 'plus')}${bigNow() ? '화면에 맞추기' : '크게 보기'}</button>`)}
      <p class="small muted sm-sum">${sum}</p>
      <div class="card flat sm-card">
        <div class="sm-key"><span><i class="k-cov"></i>이 로드맵이 다루는 스킬(꼬리표 = 주차)</span><span><i class="k-e"></i>먼저 배울 스킬 → 다음 스킬${draft ? '(가정)' : ''}</span><span><i class="k-n"></i>점 크기 = 팀 DB 자료 수</span></div>
        <div class="sm-wrap">${g.html}</div>
        <div class="sm-info" aria-live="polite">${info(pl, g.cov)}</div>
      </div>
      ${g.cov.size ? '' : P.note('이 로드맵의 활동에서 팀 DB 스킬을 찾지 못했어요.')}
      ${draft ? P.note(`선수 관계 ${data.prerequisites.length}개는 팀 DB에 아직 없어 임시 초안(가정)으로 그렸어요. 팀 검토 전에는 참고로만 봐 주세요.`) : ''}
      ${data.unmatched && data.unmatched.length ? P.note(`선수 관계 초안 ${data.unmatched.length}개는 지금 팀 DB 스킬 이름과 맞지 않아 뺐어요(${esc(data.unmatched.map(u => `${u.prerequisite} → ${u.skill}`).join(', '))}).`) : ''}</div>`;
  };
  // 그 칸만 다시 그린다(화면 전체를 다시 그리지 않게)
  function paint(keepScroll) {
    const box = document.getElementById('smBox');
    if (!box || !plan) return;
    const old = box.querySelector('.sm-wrap'), pos = old && [old.scrollLeft, old.scrollTop];
    box.outerHTML = SM.html(plan);
    const w = document.querySelector('#smBox .sm-wrap');
    if (keepScroll && pos && w) { w.scrollLeft = pos[0]; w.scrollTop = pos[1]; } else center();
  }
  // 실제 크기로 볼 때(좁은 화면·크게 보기)는 이 로드맵의 스킬이 가운데 오게 밀어 둔다
  function center() {
    const w = document.querySelector('#smBox .sm-wrap');
    if (!w || (w.scrollWidth <= w.clientWidth + 2 && w.scrollHeight <= w.clientHeight + 2)) return;
    const els = [...w.querySelectorAll('.sm-n.cov')];
    if (!els.length) return;
    const wr = w.getBoundingClientRect();
    const pts = els.map(e => { const r = e.getBoundingClientRect(); return [(r.left + r.right) / 2 - wr.left + w.scrollLeft, (r.top + r.bottom) / 2 - wr.top + w.scrollTop]; });
    w.scrollLeft = pts.reduce((s, p) => s + p[0], 0) / pts.length - w.clientWidth / 2;
    w.scrollTop = pts.reduce((s, p) => s + p[1], 0) / pts.length - w.clientHeight / 2;
  }
  GP.act['sm-pick'] = arg => { const id = Number(arg); picked = picked === id ? null : id; paint(true); const el = document.querySelector(`#smBox [data-act="sm-pick"][data-arg="${id}"]`); if (el && picked === id) el.focus({ preventScroll: true }); };
  GP.act['sm-zoom'] = () => { big = !bigNow(); paint(); };
  // 점은 SVG 라 Enter·Space 로도 누를 수 있게
  document.addEventListener('keydown', e => {
    const el = e.target.closest && e.target.closest('#smBox .sm-n');
    if (el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); GP.act['sm-pick'](el.dataset.arg); }
  });
})();

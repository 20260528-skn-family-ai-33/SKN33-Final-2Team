/* 스킬 지도 — 검토·확정 화면과 내 로드맵(확정한 로드맵) 화면, 요약 박스 바로 아래 (5차 gp-skillmap.js · 2026-10-23 팀 합의)
   생활코딩 WEBn 지식 지도(seomal)처럼 점과 화살표로 그린다. 로드맵에 없는 스킬은 따로 표시하지 않는다(10/23 사용자 결정) */
import { useQuery } from '@tanstack/react-query';
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { catalogApi } from '@/api/endpoints/catalog';
import type { SkillMapData } from '@/api/types/catalog';
import type { PlanContent } from '@/api/types/plan';
import { resOf, useCatalog } from '@/shared/state/catalog';
import { Icon } from '@/shared/ui/Icon';
import { Note } from '@/shared/ui/parts';
import { ApiError } from '@/api/client';
import { actWeek, canvasMeasure, coverOf, place, relOf, weeksOf, type Cover, type Layout } from './layout';

let layoutCache: { d: SkillMapData; m: Layout } | null = null;
let bigPref: boolean | null = null;
// 넓은 화면은 칸에 맞추고, 좁은 화면은 실제 크기로 두고 옆으로 밀어 본다
const bigNow = () => (bigPref != null ? bigPref : window.innerWidth <= 900);

function layoutOf(d: SkillMapData): Layout {
  if (layoutCache && layoutCache.d === d) return layoutCache.m;
  const m = place(d, canvasMeasure());
  layoutCache = { d, m };
  return m;
}

function Info({ data, picked, cov, onClose }: { data: SkillMapData; picked: number | null; cov: Cover; onClose: () => void }) {
  if (picked == null || !data.skills.some((s) => s.id === picked))
    return <p className="small muted">스킬 점을 누르면 이 로드맵에서 몇 주차에 어떤 활동이 다루는지와 선수 관계를 보여 줘요.</p>;
  const s = data.skills.find((x) => x.id === picked)!;
  const { parents, kids } = relOf(data);
  const names = (ids?: number[]) =>
    ids && ids.length ? ids.map((id) => data.skills.find((x) => x.id === id)?.name || '').join(', ') : <span className="muted">없어요</span>;
  const c = cov.get(picked);
  let here: React.ReactNode = <span className="muted">이 로드맵에는 없어요.</span>;
  if (c) {
    // 다루는 활동을 주차와 함께. 많으면 앞의 4개만 적고 나머지는 개수로
    const shown = c.slice(0, 4);
    here = (
      <>
        <b>{weeksOf(c)}</b> · {shown.map((x) => `${x.a.title}${x.a.wFrom != null ? ` (${actWeek(x.a)})` : ''}`).join(', ')}
        {c.length > shown.length ? ` 외 ${c.length - shown.length}개` : ''}
      </>
    );
  }
  return (
    <>
      <div className="sm-pick-h">
        <b>{s.name}</b>
        <span className="tag">{s.category}</span>
        <button className="link quiet" aria-label="설명 닫기" onClick={onClose}>
          <Icon name="x" />
        </button>
      </div>
      <dl className="kv sm-kv">
        <dt>이 로드맵</dt>
        <dd>{here}</dd>
        <dt>팀 DB 자료</dt>
        <dd>{s.resources}건에 이 스킬이 붙어 있어요</dd>
        <dt>먼저 배울 스킬</dt>
        <dd>{names(parents[picked])}</dd>
        <dt>다음 스킬</dt>
        <dd>{names(kids[picked])}</dd>
      </dl>
    </>
  );
}

function Svg({ data, pl, picked, onPick, big }: { data: SkillMapData; pl: PlanContent; picked: number | null; onPick: (id: number) => void; big: boolean }) {
  useCatalog((s) => s.res);
  const m = useMemo(() => layoutOf(data), [data]);
  const cov = coverOf(data, pl, resOf);
  const tw = useMemo(() => canvasMeasure(), []);
  const on = (id: number) => cov.has(id);
  /* 주차 꼬리표: 노드 오른쪽에 붙으므로 그림 너비에 넣는다 */
  const tags = m.nodes.map((n) => {
    const c = cov.get(n.id);
    const tagT = c ? weeksOf(c) : '';
    return { c, tagT, tagW: tagT ? tw(tagT, 10, 700) + 12 : 0 };
  });
  const x1 = m.nodes.reduce((v, n, i) => (tags[i].tagT ? Math.max(v, n.x + n.r + 5 + tags[i].tagW) : v), -1e9);
  const nodes = m.nodes.map((n, i) => {
    const { c, tagT, tagW } = tags[i];
    const y0 = n.r + 15;
    return (
      <g
        key={n.id}
        className={`sm-n${c ? ' cov' : ' off'}${picked === n.id ? ' pick' : ''}`}
        transform={`translate(${n.x.toFixed(1)},${n.y.toFixed(1)})`}
        role="button"
        tabIndex={0}
        aria-pressed={picked === n.id}
        aria-label={`${n.name}${c ? ` · 이 로드맵 ${tagT}` : ''}`}
        data-arg={n.id}
        onClick={() => onPick(n.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onPick(n.id);
          }
        }}
      >
        <circle className="dot" r={n.r.toFixed(1)} />
        {c ? <circle className="ring" r={(n.r + 1.5).toFixed(1)} /> : null}
        {n.lines.map((l, i) => (
          <text key={i} x="0" y={(y0 + i * 15).toFixed(1)} textAnchor="middle">
            {l}
          </text>
        ))}
        <text className="cat" x="0" y={(y0 + n.lines.length * 15).toFixed(1)} textAnchor="middle">
          {n.cat}
        </text>
        {tagT ? (
          <g className="tag" transform={`translate(${(n.r + 5).toFixed(1)},-8)`}>
            <rect width={tagW.toFixed(1)} height="16" rx="8" />
            <text x={(tagW / 2).toFixed(1)} y="11.5" textAnchor="middle">
              {tagT}
            </text>
          </g>
        ) : null}
      </g>
    );
  });
  const b = m.nodes.reduce(
    (o, n) => ({ x0: Math.min(o.x0, n.x - n.bw / 2), y0: Math.min(o.y0, n.y - n.r - 6), x1: Math.max(o.x1, n.x + n.bw / 2), y1: Math.max(o.y1, n.y - n.r + n.bh) }),
    { x0: 1e9, y0: 1e9, x1: -1e9, y1: -1e9 },
  );
  b.x1 = Math.max(b.x1, x1);
  const pad = 24;
  const W = Math.ceil(b.x1 - b.x0 + pad * 2);
  const H = Math.ceil(b.y1 - b.y0 + pad * 2);
  return (
    <svg
      className="sm-svg"
      viewBox={`${(b.x0 - pad).toFixed(1)} ${(b.y0 - pad).toFixed(1)} ${W} ${H}`}
      width={W}
      height={H}
      style={!big ? { width: '100%', maxWidth: W, height: 'auto' } : { width: W, height: 'auto' }}
      role="img"
      aria-label="스킬 지도: 팀 DB 스킬과 선수 관계(가정), 이 로드맵이 다루는 스킬 표시"
    >
      <defs>
        {[
          ['g', '#BDBDB5'],
          ['on', 'var(--accent)'],
        ].map(([k, c]) => (
          <marker key={k} id={`sm-${k}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" style={{ fill: c }} />
          </marker>
        ))}
      </defs>
      <g>
        {data.prerequisites.map(([a, bb], i) => {
          const A = m.byId[a];
          const B = m.byId[bb];
          if (!A || !B) return null;
          const vx = B.x - A.x;
          const vy = B.y - A.y;
          const d = Math.hypot(vx, vy) || 1;
          const ux = vx / d;
          const uy = vy / d;
          const hit = on(a) && on(bb);
          return (
            <line
              key={i}
              className={`sm-e${hit ? ' on' : ''}`}
              markerEnd={`url(#sm-${hit ? 'on' : 'g'})`}
              x1={(A.x + ux * (A.r + 2)).toFixed(1)}
              y1={(A.y + uy * (A.r + 2)).toFixed(1)}
              x2={(B.x - ux * (B.r + 5)).toFixed(1)}
              y2={(B.y - uy * (B.r + 5)).toFixed(1)}
            />
          );
        })}
      </g>
      <g>{nodes}</g>
    </svg>
  );
}

/** 검토·확정 = 작성 중 안, 내 로드맵 = 확정한 로드맵. 다른 로드맵으로 옮기면 누른 스킬은 풀어 둔다 */
export function SkillMap({ pl }: { pl: PlanContent }) {
  const q = useQuery({ queryKey: ['skills-map'], queryFn: catalogApi.skillMap, staleTime: Infinity });
  const key = pl.rid || 'draft';
  const [picked, setPicked] = useState<{ key: string; id: number | null }>({ key, id: null });
  const [big, setBig] = useState(bigNow());
  const wrapRef = useRef<HTMLDivElement>(null);
  const keepScroll = useRef(false);
  const pid = picked.key === key ? picked.id : null;
  const data = q.data;
  const cov = useMemo(() => (data ? coverOf(data, pl, resOf) : new Map()), [data, pl]);

  // 실제 크기로 볼 때(좁은 화면·크게 보기)는 이 로드맵의 스킬이 가운데 오게 밀어 둔다
  useLayoutEffect(() => {
    const w = wrapRef.current;
    if (keepScroll.current) {
      keepScroll.current = false;
      return;
    }
    if (!w || (w.scrollWidth <= w.clientWidth + 2 && w.scrollHeight <= w.clientHeight + 2)) return;
    const els = [...w.querySelectorAll('.sm-n.cov')];
    if (!els.length) return;
    const wr = w.getBoundingClientRect();
    const pts = els.map((e) => {
      const r = e.getBoundingClientRect();
      return [(r.left + r.right) / 2 - wr.left + w.scrollLeft, (r.top + r.bottom) / 2 - wr.top + w.scrollTop];
    });
    w.scrollLeft = pts.reduce((s, p) => s + p[0], 0) / pts.length - w.clientWidth / 2;
    w.scrollTop = pts.reduce((s, p) => s + p[1], 0) / pts.length - w.clientHeight / 2;
  }, [data, big, key]);

  const head = (n?: React.ReactNode) => (
    <div className="sec-h">
      <h2 className="st">이 로드맵이 다루는 스킬</h2>
      {n}
    </div>
  );
  if (q.error) {
    const e = q.error as ApiError;
    const msg = (e.payload && (e.payload.message || e.payload.raw)) || e.message || '';
    return (
      <div className="sec" id="smBox">
        {head()}
        <div className="loading">
          <Icon name="alert" />
          <span>스킬 지도를 불러오지 못했어요{msg ? ` · ${msg}` : ''}</span>
          <button className="btn line sm" onClick={() => void q.refetch()}>
            다시 시도
          </button>
        </div>
      </div>
    );
  }
  if (!data)
    return (
      <div className="sec" id="smBox">
        {head()}
        <div className="loading">
          <span className="sp" />
          <span>스킬 지도를 불러오는 중…</span>
        </div>
      </div>
    );
  const draft = data.prerequisiteSource !== 'db';
  const pick = (id: number) => {
    keepScroll.current = true;
    setPicked({ key, id: pid === id ? null : id });
  };
  const unmatched = data.unmatched || [];
  return (
    <div className="sec" id="smBox">
      {head(
        <button
          className="link quiet"
          onClick={() => {
            bigPref = !big;
            setBig(!big);
          }}
        >
          <Icon name={big ? 'minus' : 'plus'} />
          {big ? '화면에 맞추기' : '크게 보기'}
        </button>,
      )}
      <p className="small muted sm-sum">
        팀 DB 스킬 {data.skills.length}개 가운데 이 로드맵이 다루는 스킬 <b>{cov.size}개</b>를 진하게, 다루는 주차를 꼬리표로 보여 줘요.
      </p>
      <div className="card flat sm-card">
        <div className="sm-key">
          <span>
            <i className="k-cov" />이 로드맵이 다루는 스킬(꼬리표 = 주차)
          </span>
          <span>
            <i className="k-e" />
            먼저 배울 스킬 → 다음 스킬{draft ? '(가정)' : ''}
          </span>
          <span>
            <i className="k-n" />점 크기 = 팀 DB 자료 수
          </span>
        </div>
        <div className="sm-wrap" ref={wrapRef}>
          <Svg data={data} pl={pl} picked={pid} onPick={pick} big={big} />
        </div>
        <div className="sm-info" aria-live="polite">
          <Info data={data} picked={pid} cov={cov} onClose={() => pid != null && pick(pid)} />
        </div>
      </div>
      {cov.size ? null : <Note>이 로드맵의 활동에서 팀 DB 스킬을 찾지 못했어요.</Note>}
      {draft ? <Note>선수 관계 {data.prerequisites.length}개는 팀 DB에 아직 없어 임시 초안(가정)으로 그렸어요. 팀 검토 전에는 참고로만 봐 주세요.</Note> : null}
      {unmatched.length ? (
        <Note>
          선수 관계 초안 {unmatched.length}개는 지금 팀 DB 스킬 이름과 맞지 않아 뺐어요({unmatched.map((u) => `${u.prerequisite} → ${u.skill}`).join(', ')}).
        </Note>
      ) : null}
    </div>
  );
}

/* 스킬 지도 — 검토·확정 화면과 내 로드맵(확정한 로드맵) 화면, 요약 박스 바로 아래 (5차 gp-skillmap.js · 2026-10-23 팀 합의)
   생활코딩 WEBn 지식 지도(seomal)처럼 점과 화살표로 그린다. 로드맵에 없는 스킬은 따로 표시하지 않는다(10/23 사용자 결정)
   그리는 틀(MapBox)은 내 스킬 지도(MySkillMap · 누적)와 함께 쓴다. 점과 화살표를 어떤 모양으로 그릴지는 쓰는 쪽이 MapView 로 정한다 */
import { useQuery } from '@tanstack/react-query';
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { catalogApi } from '@/api/endpoints/catalog';
import type { SkillMapData } from '@/api/types/catalog';
import type { PlanContent, Progress } from '@/api/types/plan';
import { st } from '@/shared/lib/plan';
import { resOf, useCatalog } from '@/shared/state/catalog';
import { Icon } from '@/shared/ui/Icon';
import { Note } from '@/shared/ui/parts';
import { ApiError } from '@/api/client';
import { matchingCertificates } from '@/features/roadmap/roadmapLearningData';
import { useMe } from '@/shared/state/session';
import { afterReveal } from '@/skins/afterReveal';
import { actWeek, canvasMeasure, coverOf, edgeEnds, focusOf, place, relOf, revealDelta, weeksOf, type Cover, type Layout } from './layout';

let layoutCache: { d: SkillMapData; m: Layout } | null = null;
let bigPref: boolean | null = null;
// 넓은 화면은 칸에 맞추고, 좁은 화면은 크게 두고 옆으로 밀어 본다
const bigNow = () => (bigPref != null ? bigPref : typeof window !== 'undefined' && window.innerWidth <= 900);

function layoutOf(d: SkillMapData): Layout {
  if (layoutCache && layoutCache.d === d) return layoutCache.m;
  const m = place(d, canvasMeasure());
  layoutCache = { d, m };
  return m;
}

/** 점 하나의 모양. cls: .sm-n 에 붙는 상태(cov·off) · tag: 오른쪽 꼬리표 · aria: 이름 뒤에 읽어 줄 말 · medal: 점 위에 얹는 메달 뱃지 */
export interface NodeLook {
  cls: string;
  tag?: string;
  aria?: string;
  ring?: boolean;
  medal?: 'bronze' | 'silver' | 'gold';
}

/** 메달 가운데 별(꼭짓점 5개). 점 크기에 맞춰 그린다 */
function starPoints(outer: number): string {
  return Array.from({ length: 10 }, (_, i) => {
    const radius = i % 2 ? outer * 0.42 : outer;
    const angle = (Math.PI / 5) * i - Math.PI / 2;
    return `${(Math.cos(angle) * radius).toFixed(1)},${(Math.sin(angle) * radius).toFixed(1)}`;
  }).join(' ');
}
/** 화살표의 모양. on: 이 로드맵이 양쪽을 다룸 · trail: 지나온 길(뱃지 스킬에서 이어진 화살표) */
export type EdgeLook = '' | 'on' | 'trail';
export interface InfoCtl {
  close: () => void;
  pick: (id: number) => void;
}
export interface MapView {
  label: string;
  sum: ReactNode;
  keys: ReactNode;
  look: (id: number) => NodeLook;
  edge: (from: number, to: number) => EdgeLook;
  /** 누른 스킬의 설명. close 는 누른 스킬을 풀고, pick 은 다른 스킬로 옮긴다 */
  info: (ctl: InfoCtl) => ReactNode;
  notes?: ReactNode;
}

/* 퍼져 나가기: 지도가 화면에 들어올 때 한 번, 가운데 점부터 가장자리 점 순서로 나타난다(모양은 gp-v2.css 의 sm-spread).
   점마다 가운데에서 떨어진 거리에 비례해 늦게 시작하고, 가운데 쪽으로 조금 당겨진 자리에서 제자리로 나온다 */
const SPREAD_MS = 900; // 가운데 점과 가장 먼 점의 시작 시각 차이
const SPREAD_PULL = 0.16; // 시작 자리: 가운데 쪽으로 이만큼(거리의 비율) 당긴다
const spreadVars = (x: number, y: number, cx: number, cy: number, far: number, lag = 0): CSSProperties =>
  ({
    '--sm-d': `${Math.round((Math.hypot(x - cx, y - cy) / far) * SPREAD_MS + lag)}ms`,
    '--sm-dx': `${((cx - x) * SPREAD_PULL).toFixed(1)}px`,
    '--sm-dy': `${((cy - y) * SPREAD_PULL).toFixed(1)}px`,
  }) as CSSProperties;

const InfoSlot = ({ render, ctl }: { render: MapView['info']; ctl: InfoCtl }) => <>{render(ctl)}</>;

/** 선수·후속 스킬 칩. 누르면 그 스킬로 옮겨 간다 · strong: 강조할 스킬(이 로드맵이 다루는 스킬 등) */
export function SkillChips({ data, ids, onPick, strong }: { data: SkillMapData; ids?: number[]; onPick: (id: number) => void; strong?: (id: number) => boolean }) {
  const list = (ids || []).map((id) => data.skills.find((x) => x.id === id)).filter((x): x is SkillMapData['skills'][number] => x != null);
  if (!list.length) return <span className="muted">없어요</span>;
  return (
    <span className="sm-chips">
      {list.map((x) => (
        <button key={x.id} type="button" className={`tag sm-chip${strong?.(x.id) ? ' acc' : ''}`} onClick={() => onPick(x.id)}>
          {x.name}
        </button>
      ))}
    </span>
  );
}

function Info({ data, picked, cov, owned, progress, ctl }: { data: SkillMapData; picked: number | null; cov: Cover; owned?: string[]; progress?: Record<string, Progress>; ctl: InfoCtl }) {
  const certificates = useCatalog(state => state.certById);
  const me = useMe();
  if (picked == null || !data.skills.some((s) => s.id === picked))
    return <p className="small muted">스킬 점을 누르면 이 로드맵에서 몇 주차에 어떤 활동이 다루는지와 선수 관계를 보여 줘요.</p>;
  const s = data.skills.find((x) => x.id === picked)!;
  const { parents, kids } = relOf(data);
  const certs = matchingCertificates(Object.values(certificates), [s.name], owned ?? me?.certs);
  const inPlan = (id: number) => cov.has(id);
  const c = cov.get(picked);
  let here: React.ReactNode = <span className="muted">이 로드맵에는 없어요.</span>;
  if (c) {
    here = (
      <>
        <b>{weeksOf(c)}</b>
        <ul className="sm-acts">
          {c.map((x, i) => (
            <li key={`${x.a.id}-${i}`}>
              <span>
                {x.a.wFrom != null ? `${actWeek(x.a)} · ` : ''}
                {x.a.title}
              </span>
              {progress && st(progress, x.a.id) === 'done' ? <span className="tag done">완료</span> : null}
            </li>
          ))}
        </ul>
      </>
    );
  }
  return (
    <>
      <div className="sm-pick-h">
        <b>{s.name}</b>
        <span className="tag">{s.category}</span>
        <button className="link quiet" aria-label="설명 닫기" onClick={ctl.close}>
          <Icon name="x" />
        </button>
      </div>
      <dl className="kv sm-kv">
        <dt>먼저 배울 스킬</dt>
        <dd>
          <SkillChips data={data} ids={parents[picked]} onPick={ctl.pick} strong={inPlan} />
        </dd>
        <dt>이어지는 스킬</dt>
        <dd>
          <SkillChips data={data} ids={kids[picked]} onPick={ctl.pick} strong={inPlan} />
        </dd>
        <dt>추천 자격증</dt>
        <dd>{certs.length ? certs.map(cert => cert.name).join(', ') : '일치하는 자격증이 없어요.'}</dd>
        <dt>이 로드맵</dt>
        <dd>{here}</dd>
      </dl>
    </>
  );
}

/** 빈 곳 클릭으로 볼 누름: 지도를 끌어 민 뒤의 클릭은 풀기로 치지 않는다 */
const DRAG_PX = 5;

function Svg({ data, view, picked, onPick, onClear, big, zoom }: { data: SkillMapData; view: MapView; picked: number | null; onPick: (id: number) => void; onClear: () => void; big: boolean; zoom: number }) {
  const m = useMemo(() => layoutOf(data), [data]);
  const tw = useMemo(() => canvasMeasure(), []);
  const focus = useMemo(() => focusOf(data, picked), [data, picked]);
  const down = useRef<{ x: number; y: number } | null>(null);
  /* 꼬리표: 노드 오른쪽에 붙으므로 그림 너비에 넣는다 */
  const looks = m.nodes.map((n) => {
    const look = view.look(n.id);
    const tagT = look.tag || '';
    return { look, tagT, tagW: tagT ? tw(tagT, 10, 700) + 12 : 0 };
  });
  const x1 = m.nodes.reduce((v, n, i) => (looks[i].tagT ? Math.max(v, n.x + n.r + 5 + looks[i].tagW) : v), -1e9);
  // 퍼져 나가기의 가운데: 점들이 놓인 범위의 한가운데
  const xs = m.nodes.map((n) => n.x);
  const ys = m.nodes.map((n) => n.y);
  const cx = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 0;
  const cy = ys.length ? (Math.min(...ys) + Math.max(...ys)) / 2 : 0;
  const far = Math.max(1, ...m.nodes.map((n) => Math.hypot(n.x - cx, n.y - cy)));
  const nodes = m.nodes.map((n, i) => {
    const { look, tagT, tagW } = looks[i];
    const y0 = n.r + 15;
    const isPick = focus != null && picked === n.id;
    return (
      <g
        key={n.id}
        className={`sm-n ${look.cls}${isPick ? ' pick' : ''}${focus?.near.has(n.id) ? ' rel' : ''}`}
        transform={`translate(${n.x.toFixed(1)},${n.y.toFixed(1)})`}
        style={spreadVars(n.x, n.y, cx, cy, far)}
        role="button"
        tabIndex={0}
        aria-pressed={picked === n.id}
        aria-label={`${n.name}${look.aria || ''}`}
        data-arg={n.id}
        onClick={() => onPick(n.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onPick(n.id);
          }
        }}
      >
        {/* 누른 점에서 퍼지는 고리: 누를 때 새로 붙어 한두 번만 퍼진다(.sm-n 의 등장 움직임과 겹치지 않게 자식에 둔다) */}
        {isPick ? <circle className="sm-pulse" r={(n.r + 2).toFixed(1)} aria-hidden="true" /> : null}
        <circle className="dot" r={n.r.toFixed(1)} />
        {look.ring ? <circle className="ring" r={(n.r + 1.5).toFixed(1)} /> : null}
        {look.medal ? (
          <g className={`medal ${look.medal}`}>
            <circle className="coin" r={n.r.toFixed(1)} />
            <circle className="rim" r={(n.r * 0.74).toFixed(1)} />
            <polygon className="star" points={starPoints(n.r * 0.5)} />
          </g>
        ) : null}
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
  const ends = data.prerequisites.map(([a, bb]) => (m.byId[a] && m.byId[bb] ? edgeEnds(m.byId[a], m.byId[bb]) : null));
  return (
    <svg
      className={`sm-svg${focus ? ' has-pick' : ''}`}
      onPointerDown={(e) => {
        down.current = { x: e.clientX, y: e.clientY };
      }}
      onClick={(e) => {
        const d = down.current;
        down.current = null;
        if (!focus || (e.target as Element).closest('.sm-n')) return;
        if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) > DRAG_PX) return;
        onClear();
      }}
      viewBox={`${(b.x0 - pad).toFixed(1)} ${(b.y0 - pad).toFixed(1)} ${W} ${H}`}
      width={W}
      height={H}
      /* 크게 보기: 실제 크기와 칸 너비의 1.4배 중 큰 쪽. 넓은 화면에서는 실제 크기가 칸보다 작아 눌러도 그대로였다(#227) */
      style={big ? { width: `calc(max(${W}px, 140%) * ${zoom})`, height: 'auto' } : { width: `${zoom * 100}%`, maxWidth: W * zoom, height: 'auto' }}
      role="img"
      aria-label={view.label}
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
          const p = ends[i];
          if (!p) return null;
          const edge = view.edge(a, bb);
          const rel = focus?.edges[i];
          return (
            <line
              key={i}
              className={`sm-e${edge ? ` ${edge}` : ''}${rel ? ` rel rel-${rel}` : ''}`}
              markerEnd={`url(#sm-${edge || rel ? 'on' : 'g'})`}
              /* 화살표는 이어 주는 두 점이 나온 뒤에 나타난다 */
              style={spreadVars((p.x1 + p.x2) / 2, (p.y1 + p.y2) / 2, cx, cy, far, 260)}
              x1={p.x1.toFixed(1)}
              y1={p.y1.toFixed(1)}
              x2={p.x2.toFixed(1)}
              y2={p.y2.toFixed(1)}
            />
          );
        })}
      </g>
      {/* 누른 점에 닿는 화살표 위로 흐르는 점선. 원래 선의 순서를 바꾸면 다시 붙으며 등장 움직임이 다시 돌므로, 흐린 선들 위에 따로 덧그린다 */}
      {focus ? (
        <g className="sm-flow" aria-hidden="true">
          {focus.edges.map((rel, i) => {
            const p = ends[i];
            if (!rel || !p) return null;
            return <line key={i} className={`rel-${rel}`} x1={p.x1.toFixed(1)} y1={p.y1.toFixed(1)} x2={p.x2.toFixed(1)} y2={p.y2.toFixed(1)} />;
          })}
        </g>
      ) : null}
      <g>{nodes}</g>
    </svg>
  );
}

/** 누른 점(아래 이름·분류 글자까지)이 지도 안쪽 스크롤 밖이거나, 창 위쪽 띠·아래에 떠 있는 설명 칸에 가려지면 보이게 민다.
    지도 안쪽(크게 보기·좁은 화면)을 먼저 밀고, 창은 그만큼 옮겨 갈 자리를 기준으로 민다(부드럽게 밀면 바로 다시 잰 값은 옛 자리라) */
function showPicked(wrap: HTMLElement, info: HTMLElement | null): void {
  const el = wrap.querySelector('.sm-n.pick');
  if (!el) return;
  const behavior: ScrollBehavior = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  const r = el.getBoundingClientRect();
  const w = wrap.getBoundingClientRect();
  const room = (delta: number, pos: number, max: number) => Math.max(-pos, Math.min(max - pos, delta));
  const dx = room(revealDelta(r.left, r.right, w.left, w.left + wrap.clientWidth), wrap.scrollLeft, wrap.scrollWidth - wrap.clientWidth);
  const dy = room(revealDelta(r.top, r.bottom, w.top, w.top + wrap.clientHeight), wrap.scrollTop, wrap.scrollHeight - wrap.clientHeight);
  if (dx || dy) wrap.scrollBy({ left: dx, top: dy, behavior });
  // 위쪽: 붙어 있는 띠·상단 메뉴(테마가 scroll-padding-top 으로 알려 준다) · 아래쪽: 설명 칸 위 끝.
  // 설명 칸은 나타나며 살짝 아래에서 올라오므로 화면 아래에 붙었을 때의 자리(창 높이 - bottom - 높이)와 견줘 작은 쪽을 쓴다
  const css = getComputedStyle(document.documentElement);
  const top = parseFloat(css.scrollPaddingTop) || parseFloat(css.getPropertyValue('--rib-h')) || 0;
  let bottom = window.innerHeight;
  if (info?.classList.contains('on')) {
    const stuck = window.innerHeight - (parseFloat(getComputedStyle(info).bottom) || 0) - info.offsetHeight;
    bottom = Math.min(bottom, info.getBoundingClientRect().top, stuck);
  }
  const wy = revealDelta(r.top - dy, r.bottom - dy, top, bottom);
  if (wy) window.scrollBy({ top: wy, behavior });
}

/** 스킬 지도 틀: 자료를 불러와 요약·범례·그림·설명·안내를 차례로 놓는다. viewKey 가 바뀌면(다른 로드맵) 누른 스킬은 풀어 둔다 */
export function MapBox({ id, title, viewKey, build, wheelZoom = false }: { id: string; title: string; viewKey: string; build: (data: SkillMapData, picked: number | null) => MapView; wheelZoom?: boolean }) {
  const q = useQuery({ queryKey: ['skills-map'], queryFn: catalogApi.skillMap, staleTime: Infinity });
  const [picked, setPicked] = useState<{ key: string; id: number | null }>({ key: viewKey, id: null });
  const [big, setBig] = useState(bigNow());
  const [zoom, setZoom] = useState(1);
  const wrapRef = useRef<HTMLDivElement>(null);
  const infoRef = useRef<HTMLDivElement>(null);
  const keepScroll = useRef(false);
  // 지도가 화면에 들어온 뒤에 퍼져 나가기를 시작한다(화면 아래쪽에 있을 때 안 보이는 곳에서 끝나 버리지 않게).
  // 테마의 나타나기(덩어리가 떠오르기)와 겹치면 묻혀서 안 보이므로, 지도가 든 덩어리가 떠오른 뒤에 시작한다
  const [seen, setSeen] = useState(typeof IntersectionObserver === 'undefined');
  const pid = picked.key === viewKey ? picked.id : null;
  const data = q.data;

  useEffect(() => {
    const wrap = wrapRef.current;
    if (seen || !wrap) return;
    let stopWaiting = (): void => {};
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        stopWaiting = afterReveal(wrap, () => setSeen(true));
      },
      { threshold: 0.15 },
    );
    io.observe(wrap);
    return () => {
      io.disconnect();
      stopWaiting();
    };
  }, [data, seen]);

  useLayoutEffect(() => {
    const wrap = wrapRef.current;
    if (!wheelZoom || !wrap) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey || !event.deltaY) return;
      event.preventDefault();
      setZoom((value) => Math.min(3, Math.max(0.5, value * (event.deltaY < 0 ? 1.1 : 1 / 1.1))));
    };
    wrap.addEventListener('wheel', onWheel, { passive: false });
    return () => wrap.removeEventListener('wheel', onWheel);
  }, [data, q.error, wheelZoom]);

  // 실제 크기로 볼 때(좁은 화면·크게 보기)는 강조한 스킬이 가운데 오게 밀어 둔다
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
  }, [data, big, viewKey]);

  // 누른 뒤(설명 칸이 화면 아래에 떠오른 뒤) 누른 점이 가려졌으면 보이게 민다. 칩으로 옮겨 갈 때도 같다
  useEffect(() => {
    if (pid != null && wrapRef.current) showPicked(wrapRef.current, infoRef.current);
  }, [pid]);

  const head =(n?: React.ReactNode) => (
    <div className="sec-h">
      <h2 className="st">{title}</h2>
      {n}
    </div>
  );
  if (q.error) {
    const e = q.error as ApiError;
    const msg = (e.payload && (e.payload.message || e.payload.raw)) || e.message || '';
    return (
      <div className="sec" id={id}>
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
      <div className="sec" id={id}>
        {head()}
        <div className="loading">
          <span className="sp" />
          <span>스킬 지도를 불러오는 중…</span>
        </div>
      </div>
    );
  const pick = (skillId: number) => {
    keepScroll.current = true;
    setPicked({ key: viewKey, id: pid === skillId ? null : skillId });
  };
  const clear = () => setPicked({ key: viewKey, id: null });
  const ctl: InfoCtl = { close: clear, pick: (skillId) => setPicked({ key: viewKey, id: skillId }) };
  const view = build(data, pid);
  return (
    <div className="sec" id={id}>
      {head(
        <button
          className="link quiet"
          onClick={() => {
            bigPref = !big;
            setBig(!big);
            setZoom(1);
          }}
        >
          <Icon name={big ? 'minus' : 'plus'} />
          {big ? '화면에 맞추기' : '크게 보기'}
        </button>,
      )}
      <p className="small muted sm-sum">{view.sum}</p>
      {/* Esc 로 풀기: 지도의 점뿐 아니라 설명 칸의 칩에 초점이 있을 때도 듣도록 카드에 둔다 */}
      <div
        className="card flat sm-card"
        onKeyDown={(e) => {
          if (e.key !== 'Escape' || pid == null) return;
          e.preventDefault();
          e.stopPropagation();
          clear();
        }}
      >
        <div className="sm-key">{view.keys}</div>
        <div className={`sm-wrap${big ? ' sm-big' : ''} ${seen ? 'sm-go' : 'sm-wait'}`} ref={wrapRef} title={wheelZoom ? 'Ctrl + 스크롤로 확대·축소' : undefined}>
          <Svg data={data} view={view} picked={pid} onPick={pick} onClear={clear} big={big} zoom={zoom} />
        </div>
        {/* 스킬을 눌렀을 때만 화면 아래에 붙여 지도 위에 띄운다(지도가 화면보다 길어 맨 아래 설명이 눈에 안 띄어서) */}
        <div className={`sm-info${pid != null && data.skills.some((s) => s.id === pid) ? ' on' : ''}`} aria-live="polite" ref={infoRef}>
          <InfoSlot render={view.info} ctl={ctl} />
        </div>
      </div>
      {view.notes}
    </div>
  );
}

/** 검토·확정 = 작성 중 안, 내 로드맵 = 확정한 로드맵 */
/** owned: 추천 자격증에서 뺄 보유 자격증. 기본은 로그인한 본인 것 · 부서장이 직원 로드맵을 볼 때는 직원 보유 자격증을 받지 않으므로 [] (#96) */
/** progress: 넘기면 활동마다 완료 여부를 함께 적는다(검토·확정 화면은 아직 기록이 없어 넘기지 않는다) */
export function SkillMap({ pl, owned, progress }: { pl: PlanContent; owned?: string[]; progress?: Record<string, Progress> }) {
  // 자료가 나중에 오면 자료에 붙은 스킬로 다시 그린다
  useCatalog((s) => s.res);
  return (
    <MapBox
      id="smBox"
      title="이 로드맵이 다루는 스킬"
      viewKey={pl.rid || 'draft'}
      build={(data, pid) => {
        const cov = coverOf(data, pl, resOf);
        const draft = data.prerequisiteSource !== 'db';
        const unmatched = data.unmatched || [];
        return {
          label: '스킬 지도: 팀 DB 스킬과 선수 관계(가정), 이 로드맵이 다루는 스킬 표시',
          sum: (
            <>
              팀 DB 스킬 {data.skills.length}개 가운데 이 로드맵이 다루는 스킬 <b>{cov.size}개</b>를 진하게, 다루는 주차를 꼬리표로 보여 줘요.
            </>
          ),
          keys: (
            <>
              <span>
                <i className="k-cov" />이 로드맵이 다루는 스킬(꼬리표 = 주차)
              </span>
              <span>
                <i className="k-e" />
                배우게 될 스킬 · 학습 연결{draft ? '(가정)' : ''}
              </span>
              <span>
                <i className="k-n" />점 크기 = 팀 DB 자료 수
              </span>
            </>
          ),
          look: (skillId) => {
            const c = cov.get(skillId);
            if (!c) return { cls: 'off' };
            const tag = weeksOf(c);
            return { cls: 'cov', tag, aria: ` · 이 로드맵 ${tag}`, ring: true };
          },
          edge: (from, to) => (cov.has(from) && cov.has(to) ? 'on' : ''),
          info: (ctl) => <Info data={data} picked={pid} cov={cov} owned={owned} progress={progress} ctl={ctl} />,
          notes: (
            <>
              {cov.size ? null : <Note>이 로드맵의 활동에서 팀 DB 스킬을 찾지 못했어요.</Note>}
              {draft ? <Note>선수 관계 {data.prerequisites.length}개는 팀 DB에 아직 없어 임시 초안(가정)으로 그렸어요. 팀 검토 전에는 참고로만 봐 주세요.</Note> : null}
              {unmatched.length ? (
                <Note>
                  선수 관계 초안 {unmatched.length}개는 지금 팀 DB 스킬 이름과 맞지 않아 뺐어요({unmatched.map((u) => `${u.prerequisite} → ${u.skill}`).join(', ')}).
                </Note>
              ) : null}
            </>
          ),
        };
      }}
    />
  );
}

import { trackName } from '@/shared/constants/data';
/* 로드맵 일정(간트) 표시 (5차 ganttOne·ganttAll·gtStages·gtCard·gt-fold·설명 상자)
   로드맵이 하나면 '전체 진행' 카드 자리에, 여럿이면 하나로 합쳐 맨 위에 둔다. 이번 주 칸을 칠한다.
   예정 주차가 지나도 늦었다고 표시하지 않는다(스스로 정한 학습 계획). 처음엔 모두 펼치고, 접은 상태는 새로 고칠 때까지만 기억한다 */
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { openRecord } from '@/features/roadmap/RecordSheet';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { hrs } from '@/shared/lib/format';
import { count, st, stageActs } from '@/shared/lib/plan';
import { Icon } from '@/shared/ui/Icon';
import { addDays, axisAll, colsOne, confirmDay, dayGap, gtPos, md, planStart, planWeeks, weekNow, type GtCol } from './ganttCalc';

const gtFold = new Set<string>();

interface Tip {
  v: string;
  t: string;
  m: string;
}

/* 설명 상자: 하나만 만들어 body 에 둔다(화면 등장 애니메이션의 transform 이 fixed 위치를 흔들지 않게) */
function useTip() {
  const [tip, setTip] = useState<{ tip: Tip; row: HTMLElement } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const hide = () => setTip(null);
    const onDown = (e: PointerEvent) => {
      if (e.pointerType === 'mouse') hide();
    };
    document.addEventListener('pointerdown', onDown);
    window.addEventListener('scroll', hide, true);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      window.removeEventListener('scroll', hide, true);
    };
  }, []);
  useEffect(() => {
    const el = box.current;
    if (!el || !tip) return;
    const row = tip.row;
    const bar = (row.querySelector('.gt-bar') as HTMLElement) || row;
    const sc = row.closest('.gt-scroll');
    if (!sc) return;
    const b = sc.getBoundingClientRect();
    const r = bar.getBoundingClientRect();
    const tw = el.offsetWidth;
    const th = el.offsetHeight;
    const cx = Math.min(Math.max((Math.max(r.left, b.left) + Math.min(r.right, b.right)) / 2, b.left), b.right);
    const top = r.top - th - 8 < 44 ? r.bottom + 8 : r.top - th - 8;
    el.style.left = `${Math.min(Math.max(cx - tw / 2, 8), window.innerWidth - tw - 8)}px`;
    el.style.top = `${top}px`;
  }, [tip]);
  const show = (e: React.SyntheticEvent) => {
    const row = (e.target as HTMLElement).closest('.gt-row') as HTMLElement | null;
    if (!row) return;
    if (tip && tip.row === row) return;
    setTip({ row, tip: { v: row.dataset.tv || '', t: row.dataset.tt || '', m: row.dataset.tm || '' } });
  };
  const el = tip
    ? createPortal(
        <div className="gt-tip" role="tooltip" ref={box}>
          <b>{tip.tip.v}</b>
          <span>{tip.tip.t}</span>
          <small>{tip.tip.m}</small>
        </div>,
        document.body,
      )
    : null;
  return { show, el, hide: () => setTip(null) };
}

function Tg({ k, name, onToggle }: { k: string; name: string; onToggle: () => void }) {
  const open = !gtFold.has(k);
  return (
    <button className="gt-tg" aria-expanded={open} aria-label={`${name} ${open ? '접기' : '펼치기'}`} onClick={onToggle}>
      <Icon name={open ? 'minus' : 'plus'} />
    </button>
  );
}

/** 한 줄 = 왼쪽 이름 칸 + 오른쪽 막대 칸. tip 은 마우스를 올리거나 이름 칸에 초점이 가면 보이는 설명(날짜가 먼저) */
function Row({ lv, ins, label, bar, tip }: { lv: number; ins: string[]; label: ReactNode; bar: ReactNode; tip: Tip }) {
  return (
    <div className={`gt-row lv${lv}`} data-in={ins.join(' ')} hidden={ins.some((k) => gtFold.has(k))} data-tv={tip.v} data-tt={tip.t} data-tm={tip.m}>
      <div className="gt-l">{label}</div>
      <div className="gt-tl">{bar}</div>
    </div>
  );
}

/** 로드맵 하나의 단계·활동 줄. off = 축 첫날부터 이 로드맵 1주차 첫날까지 일 수, T = 축 전체 일 수, up = 위 줄(로드맵)의 접기 열쇠 */
function Stages({ R, off, T, up, onToggle }: { R: PlanRecord; off: number; T: number; up: string[]; onToggle: (k: string) => void }) {
  const pl = R.plan;
  const base = planStart(R);
  const when = (f: number, t: number) => `${f === t ? f : `${f}~${t}`}주차 · ${md(addDays(base, 7 * (f - 1)))}~${md(addDays(base, 7 * t - 1))}`;
  return (
    <>
      {D.stages
        .filter((s) => s.n >= pl.start && stageActs(pl, s.n).length)
        .map((s) => {
          const as = stageActs(pl, s.n);
          const dn = as.filter((a) => st(R.progress, a.id) === 'done').length;
          const key = `${R.id}:${s.n}`;
          const f = Math.min(...as.map((a) => a.wFrom));
          const t = Math.max(...as.map((a) => a.wTo));
          return (
            <Fragment key={key}>
              <Row
                lv={1}
                ins={up}
                label={
                  <>
                    <Tg k={key} name={`${s.n}단계 ${s.name}`} onToggle={() => onToggle(key)} />
                    <span className="gt-no">{s.n}</span>
                    <span className="gt-name">{s.name}</span>
                    <span className="gt-sub">
                      {dn}/{as.length}
                    </span>
                  </>
                }
                bar={
                  <span className="gt-bar sum" style={gtPos(off + 7 * (f - 1), off + 7 * t, T)}>
                    <i style={{ width: `${(dn / as.length) * 100}%` }} />
                  </span>
                }
                tip={{ v: when(f, t), t: `${s.n}단계 ${s.name}`, m: `활동 ${as.length}개 중 ${dn}개 완료` }}
              />
              {as.map((a, i) => {
                const done = st(R.progress, a.id) === 'done';
                const no = `${s.n}.${i + 1}`;
                const w = when(a.wFrom, a.wTo);
                const m = `${hrs(a.hours)} · ${done ? '완료' : '진행 중'}`;
                return (
                  <Row
                    key={a.id}
                    lv={2}
                    ins={up.concat(key)}
                    label={
                      <button className="gt-a" aria-label={`${no} ${a.title}, ${w}, ${m}, 실행 기록 열기`} onClick={() => openRecord(R.id, a.id)}>
                        <span className="gt-no">{no}</span>
                        <span className="gt-name">{a.title}</span>
                        {done ? <Icon name="check" cls="gt-ok" /> : null}
                      </button>
                    }
                    bar={
                      <span className={`gt-bar act${done ? ' done' : ''}`} style={gtPos(off + 7 * (a.wFrom - 1), off + 7 * a.wTo, T)}>
                        {done ? <Icon name="check" /> : null}
                      </span>
                    }
                    tip={{ v: w, t: a.title, m }}
                  />
                );
              })}
            </Fragment>
          );
        })}
    </>
  );
}

/** 머리 줄(칸 이름 두 줄) + 세로 칸 선·이번 주 칸 + 줄들 + 범례 */
function Card({ title, link, heads, cols, rows, note, cls }: { title: ReactNode; link: ReactNode; heads: [string, string]; cols: GtCol[]; rows: ReactNode; note: string; cls?: string }) {
  const tip = useTip();
  const scroll = useRef<HTMLDivElement>(null);
  /* 일정이 칸보다 넓어 옆으로 밀리면 이번 주 칸이 이름 칸 바로 옆(한 칸 띄움)에 오게 맞춘다 */
  useEffect(() => {
    const sc = scroll.current;
    const on = sc?.querySelector<HTMLElement>('.gt-h .on');
    if (!sc || !on || sc.scrollWidth <= sc.clientWidth) return;
    const l = sc.querySelector<HTMLElement>('.gt-h .gt-l');
    sc.scrollLeft += on.getBoundingClientRect().left - sc.getBoundingClientRect().left - (l?.offsetWidth || 0) - on.offsetWidth;
  }, []);
  return (
    <div className="card gt-card">
      <div className="sec-h">
        <h2 className="st">{title}</h2>
        {link}
      </div>
      <div className="gt-scroll" ref={scroll} onPointerOver={tip.show} onFocus={tip.show}>
        <div className={`gt${cls ? ` ${cls}` : ''}`} style={{ ['--n' as string]: cols.length }}>
          <div className="gt-h">
            <div className="gt-l">
              <span>{heads[0]}</span>
              <span>{heads[1]}</span>
            </div>
            <div className="gt-tl">
              {cols.map((c, i) => (
                <div key={i} className={c.on ? 'on' : ''} aria-current={c.on ? 'date' : undefined}>
                  <b>{c.top}</b>
                  <span>{c.sub}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="gt-body">
            <div className="gt-grid" aria-hidden="true">
              {cols.map((c, i) => (
                <i key={i} className={c.on ? 'on' : ''} />
              ))}
            </div>
            {rows}
          </div>
        </div>
      </div>
      <div className="gt-key">
        <span>
          <i className="k-done" />
          완료
        </span>
        <span>
          <i className="k-left" />
          남은 활동
        </span>
        <span>
          <i className="k-now" />
          이번 주
        </span>
        <span className="gt-note">{note}</span>
      </div>
      {tip.el}
    </div>
  );
}

function useFold() {
  const [, setN] = useState(0);
  return (k: string) => {
    if (gtFold.has(k)) gtFold.delete(k);
    else gtFold.add(k);
    setN((n) => n + 1);
  };
}

export function GanttOne({ R }: { R: PlanRecord }) {
  const go = useGo();
  const toggle = useFold();
  const pl = R.plan;
  const c = count(pl, R.progress);
  const base = planStart(R);
  const n = planWeeks(pl);
  return (
    <Card
      title={`로드맵 일정 · 활동 ${c.done}/${c.t} 완료`}
      link={
        <button className="link" onClick={() => go(paths.roadmap(R.id))}>
          로드맵 전체 <Icon name="right" />
        </button>
      }
      heads={['주차', '시작일(월)']}
      cols={colsOne(R)}
      rows={<Stages R={R} off={0} T={7 * n} up={[]} onToggle={toggle} />}
      note={`한 칸은 월~일 1주예요. 1주차는 처음 확정한 날(${md(confirmDay(R))})이 든 주(${md(base)}~${md(addDays(base, 6))})예요.`}
    />
  );
}

export function GanttAll({ list }: { list: PlanRecord[] }) {
  const go = useGo();
  const toggle = useFold();
  const { axis, starts, T, cols } = axisAll(list);
  const rows = list.map((R, i) => {
    const pl = R.plan;
    const c = count(pl, R.progress);
    const off = dayGap(axis, starts[i]);
    const w = planWeeks(pl);
    const wk = weekNow(R);
    const at = `${wk <= w ? `지금 ${wk}주차 / ` : ''}전체 ${w}주`;
    return (
      <div className="gt-roadmap-group" key={R.id}>
        <Row
          lv={0}
          ins={[]}
          label={
            <>
              <Tg k={R.id} name={pl.goal} onToggle={() => toggle(R.id)} />
              <button className="gt-r" onClick={() => go(paths.roadmap(R.id))}>
                <span className="gt-name">{pl.displayTitle || pl.goal}</span>
                <small>
                  {at} · {trackName(pl.opt, pl.name)}
                </small>
              </button>
            </>
          }
          bar={
            <span className="gt-bar rm" style={gtPos(off, off + 7 * w, T)}>
              <i style={{ width: `${(c.done / c.t) * 100}%` }} />
            </span>
          }
          tip={{ v: `${md(starts[i])}~${md(addDays(starts[i], 7 * w - 1))} · ${at}`, t: pl.goal, m: `${trackName(pl.opt, pl.name)} · v${pl.version} · 활동 ${c.t}개 중 ${c.done}개 완료` }}
        />
        <Stages R={R} off={off} T={T} up={[R.id]} onToggle={toggle} />
      </div>
    );
  });
  return (
    <Card title="전체 일정" link={null} heads={['', '주 시작일(월)']} cols={cols} rows={rows} note="한 칸은 월~일 1주예요. 로드맵마다 처음 확정한 날이 든 주를 1주차로 세요." cls="all" />
  );
}

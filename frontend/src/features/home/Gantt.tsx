import { activityTime } from '@/shared/lib/resourceTime';
import { sharedCourses } from './sharedCourses';
import { trackName } from '@/shared/constants/data';
/* 로드맵 일정(간트) 표시 (5차 ganttOne·ganttAll·gtStages·gtCard·gt-fold·설명 상자)
   로드맵이 하나면 '전체 진행' 카드 자리에, 여럿이면 하나로 합쳐 맨 위에 둔다. 이번 주 칸을 칠한다.
   예정 주차가 지나도 늦었다고 표시하지 않는다(스스로 정한 학습 계획). 처음엔 모두 펼치고, 접은 상태는 새로 고칠 때까지만 기억한다 */
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { openRecord } from '@/features/roadmap/RecordSheet';
import { ActRow } from '@/features/roadmap/parts';
import { openSheet } from '@/shared/state/ui';
import { useCatalog } from '@/shared/state/catalog';
import { useGo } from '@/shared/hooks/useGo';
import { count, st } from '@/shared/lib/plan';
import { Icon } from '@/shared/ui/Icon';
import { addDays, axisAll, colsOne, dailyCols, confirmDay, dayGap, gtPos, md, planStart, planWeeks, weekNow, type GtCol } from './ganttCalc';

import './ganttInteraction.css';

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

/** 로드맵 하나의 스킬·활동 줄. off = 축 첫날부터 이 로드맵 1주차 첫날까지 일 수, T = 축 전체 일 수, up = 위 줄(로드맵)의 접기 열쇠 */
function Stages({ R, off, T, up, onToggle }: { R: PlanRecord; off: number; T: number; up: string[]; onToggle: (k: string) => void }) {
  const pl = R.plan;
  const base = planStart(R);
  const resources = useCatalog(state => state.res);
  const skillOrder = pl.def.learningSkills?.map(skill => skill.name) || [];
  const groups = new Map<string, typeof pl.acts>();
  for (const activity of pl.acts) {
    const resource = activity.res ? resources[activity.res] : undefined;
    const name = activity.skill || activity.skills?.[0] || resource?.skills?.find(skill => skillOrder.includes(skill)) || resource?.skills?.[0] || '기타 활동';
    groups.set(name, [...(groups.get(name) || []), activity]);
  }
  const names = [...skillOrder.filter(name => groups.has(name)), ...[...groups.keys()].filter(name => !skillOrder.includes(name))];
  const shared=sharedCourses(pl.acts,resources);
  const sharedIds=new Set(shared.map(course=>course.id));
  const when = (f: number, t: number) => `${f === t ? f : `${f}~${t}`}주차 · ${md(addDays(base, 7 * (f - 1)))}~${md(addDays(base, 7 * t - 1))}`;
  return (
    <>
      {shared.map(course=>{
        const done=course.activities.every(activity=>st(R.progress,activity.id)==='done');
        const show=()=>openSheet({title:course.title,sub:`공통 강좌 · ${course.skills.join(' · ')}`,body:()=> <div>{course.activities.map(activity=><section key={activity.id}><h3>{activity.skill}</h3><ul className="acts"><ActRow a={activity} R={R}/></ul></section>)}</div>});
        return <Row key={`shared:${course.id}`} lv={1} ins={up}
          label={<button className="gt-a" aria-label={`${course.title} 공통 강좌 · ${course.skills.join(' · ')} · 관련 스킬 기록 열기`} onClick={show}><span className="gt-name">{course.title}<small>공통 · {course.skills.join(' · ')}</small></span></button>}
          bar={<button type="button" className={`gt-bar act gt-materials-open${done?' done':''}`} aria-label={`${course.title} · ${course.skills.join(' · ')} · ${course.from}~${course.to}주차`} onClick={show} style={gtPos(off+7*(course.from-1),off+7*course.to,T)}/>}
          tip={{v:when(course.from,course.to),t:course.title,m:`${course.skills.join(' · ')}에 연결된 공통 강좌 · 배정 범위 표시`}}/>;
      })}
      {names.map((name, index) => {
          const as = groups.get(name)!;
          const number = index + 1;
          const materials = as.filter(activity => activity.res);
          const separateMaterials=materials.filter(activity=>!sharedIds.has(activity.res!));
          const courses = materials.filter(activity => { const resource = resources[activity.res!]; return resource?.type === 'course' || resource?.kind === '강좌'; }).length;
          const books = materials.filter(activity => { const resource = resources[activity.res!]; return resource?.type === 'book' || resource?.kind === '도서'; }).length;
          const materialLabel = [courses ? `강좌 ${courses}개` : '', books ? `도서 ${books}권` : '', materials.length > courses + books ? `기타 ${materials.length - courses - books}개` : ''].filter(Boolean).join(' · ');
          const showMaterials = () => openSheet({ title: `${name} · 학습 자료`, sub: materialLabel, body: () => <ul className="acts">{materials.map(activity => <ActRow key={activity.id} a={activity} R={R} />)}</ul> });
          const dn = as.filter((a) => st(R.progress, a.id) === 'done').length;
          const key = `${R.id}:skill:${name}`;
          const f = Math.min(...as.map((a) => a.wFrom));
          const t = Math.max(...as.map((a) => a.wTo));
          const rangeEnd = Math.min(T, off + 7 * t + (as.some(activity => !activity.res) ? 3.5 : 0));
          return (
            <Fragment key={key}>
              <Row
                lv={1}
                ins={up}
                label={
                  <>
                    <Tg k={key} name={name} onToggle={() => onToggle(key)} />
                    <span className="gt-no">{number}</span>
                    <span className="gt-name">{name}</span>
                    <span className="gt-sub">
                      {dn}/{as.length}
                    </span>
                  </>
                }
                bar={
                  <span className="gt-bar sum" style={gtPos(off + 7 * (f - 1), rangeEnd, T)}>
                    <i style={{ width: `${(dn / as.length) * 100}%` }} />
                  </span>
                }
                tip={{ v: when(f, t), t: name, m: `활동 ${as.length}개 중 ${dn}개 완료` }}
              />
              {materials.length > 0 && <Row lv={2} ins={up.concat(key)} label={<button className="gt-a" aria-label={`${name} 자료 학습 · ${materialLabel} · 자료 목록 열기`} onClick={showMaterials}><span className="gt-no">{number}.1</span><span className="gt-name">자료 학습 <small>{materialLabel}</small></span></button>} bar={separateMaterials.length ? <button type="button" className="gt-bar act gt-materials-open" aria-label={`${name} 학습 자료 열기`} onClick={showMaterials} style={gtPos(off + 7 * (Math.min(...separateMaterials.map(activity => activity.wFrom)) - 1), off + 7 * Math.max(...separateMaterials.map(activity => activity.wTo)), T)} /> : <span className="gt-shared-note">공통 강좌 연결 표시 참조</span>} tip={{ v: when(Math.min(...materials.map(activity => activity.wFrom)), Math.max(...materials.map(activity => activity.wTo))), t: `${name} 자료 학습`, m: `${materialLabel} · 클릭하면 개별 자료와 기록을 볼 수 있어요.` }} />}
              {as.filter(activity => !activity.res).map((a, i) => {
                const task = !a.res;
                const activityFrom = task ? t : a.wFrom;
                const activityTo = task ? t : a.wTo;
                const done = st(R.progress, a.id) === 'done';
                const no = `${number}.${i + (materials.length ? 2 : 1)}`;
                const w = when(activityFrom, activityTo);
                const m = `${activityTime(a).text} · ${done ? '완료' : '진행 중'}`;
                return (
                  <Row
                    key={a.id}
                    lv={2}
                    ins={up.concat(key)}
                    label={
                      <button className="gt-a" aria-label={`${no} ${a.title}, ${w}, ${m}, ${task ? '과제물 제출 열기' : '실행 기록 열기'}`} onClick={() => openRecord(R.id, a.id)}>
                        <span className="gt-no">{no}</span>
                        <span className="gt-name">{a.title}</span>
                        {done ? <Icon name="check" cls="gt-ok" /> : null}
                      </button>
                    }
                    bar={
                      task ? <button type="button" className={`gt-bar act gt-task-submit${done ? ' done' : ''}`} aria-label={`${a.title} 과제물 제출`} onClick={() => openRecord(R.id, a.id)} style={gtPos(Math.max(0, off + 7 * t - 3.5), Math.min(T, off + 7 * t + 3.5), T)}>{done ? <Icon name="check" /> : null}</button> : <span className={`gt-bar act${done ? ' done' : ''}`} style={gtPos(off + 7 * (activityFrom - 1), off + 7 * activityTo, T)}>{done ? <Icon name="check" /> : null}</span>
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
function Card({ title, link, heads, cols, days, rows, note, cls }: { title: ReactNode; link: ReactNode; heads: [string, string]; cols: GtCol[]; days?: GtCol[]; rows: ReactNode; note: string; cls?: string }) {
  const tip = useTip();
  const scroll = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const daily = !!days && Math.round(zoom * 100) >= 150;
  const visibleCols = daily ? days! : cols;
  const [timelineSize, setTimelineSize] = useState({ available: 0, base: cols.length * 34 });
  useEffect(() => {
    const element = scroll.current;
    if (!element) return;
    const measure = () => {
      const label = element.querySelector<HTMLElement>('.gt-h .gt-l');
      const available = Math.max(0, element.clientWidth - (label?.offsetWidth || 236));
      setTimelineSize({ available, base: Math.max(available, cols.length * 34) });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [cols.length]);
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ pointer: number; x: number; left: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const changeZoom = (value: number) => { tip.hide(); setZoom(Math.max(.45, Math.min(1.5, value))); };
  useEffect(() => {
    const element = scroll.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      tip.hide();
      setZoom(value => Math.max(.45, Math.min(1.5, value + (event.deltaY < 0 ? .1 : -.1))));
    };
    element.addEventListener('wheel', onWheel, { passive: false });
    return () => element.removeEventListener('wheel', onWheel);
  }, [tip.hide]);
  const fit = () => {
    const element = scroll.current;
    if (!element) return;
    changeZoom(Math.min(1, timelineSize.available / timelineSize.base));
    element.scrollLeft = 0;
  };
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
        <div className="gt-view-controls" aria-label="일정표 보기 조절">
          <button type="button" onClick={() => changeZoom(zoom - .1)} disabled={zoom <= .45} aria-label="일정표 축소">−</button>
          <span aria-live="polite">{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => changeZoom(zoom + .1)} disabled={zoom >= 1.5} aria-label="일정표 확대">+</button>
          <button type="button" onClick={fit}>전체 맞춤</button>
          <button type="button" onClick={() => changeZoom(1)} disabled={zoom === 1}>원래 크기</button>
          {link}
        </div>
      </div>
      <div className={`gt-scroll gt-pan${dragging ? ' is-dragging' : ''}`} ref={scroll} onScroll={event => event.currentTarget.style.setProperty('--gt-scroll-left', `${Math.max(0, event.currentTarget.scrollLeft)}px`)} tabIndex={0} aria-label="일정표 · 좌우 드래그로 이동, Ctrl과 마우스 휠로 확대·축소"
        onPointerOver={event => { if (!drag.current?.moved) tip.show(event); }} onFocus={tip.show}
        onPointerDown={event => {
          if (event.pointerType !== 'mouse' || event.button !== 0) return;
          suppressClick.current = false;
          drag.current = { pointer: event.pointerId, x: event.clientX, left: event.currentTarget.scrollLeft, moved: false };
        }}
        onPointerMove={event => {
          const start = drag.current;
          if (!start || start.pointer !== event.pointerId) return;
          const dx = event.clientX - start.x;
          if (!start.moved && Math.abs(dx) < 5) return;
          if (!start.moved) { start.moved = true; suppressClick.current = true; setDragging(true); tip.hide(); event.currentTarget.setPointerCapture(event.pointerId); }
          event.preventDefault();
          event.currentTarget.scrollLeft = start.left - dx;
        }}
        onPointerUp={event => { drag.current = null; setDragging(false); if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        onPointerCancel={() => { drag.current = null; suppressClick.current = false; setDragging(false); }}
        onLostPointerCapture={() => { drag.current = null; setDragging(false); }}
        onClickCapture={event => { if (suppressClick.current) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false; } }}>

        <div className={`gt${cls ? ` ${cls}` : ''}`} style={{ ['--n' as string]: visibleCols.length, minWidth: `calc(var(--gl) + ${daily ? Math.max(timelineSize.base * zoom, visibleCols.length * 26) : timelineSize.base * zoom}px)` }}>
          <div className="gt-h">
            <div className="gt-l">
              <span>{daily ? '일 단위' : heads[0]}</span>
              <span>{daily ? '날짜' : heads[1]}</span>
            </div>
            <div className="gt-tl">
              {visibleCols.map((c, i) => (
                <div key={i} className={[c.on ? 'on' : '', c.weekStart ? 'gt-week-start' : ''].filter(Boolean).join(' ')} aria-current={c.on ? 'date' : undefined}>
                  <b>{c.top}</b>
                  <span>{c.sub}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="gt-body">
            <div className="gt-grid" aria-hidden="true">
              {visibleCols.map((c, i) => (
                <i key={i} className={[c.on ? 'on' : '', c.weekStart ? 'gt-week-start' : ''].filter(Boolean).join(' ')} />
              ))}
            </div>
            {daily && <div className="gt-week-boundaries" aria-hidden="true">{visibleCols.map((column, index) => <i key={index} className={column.weekStart ? 'week-start' : ''} />)}</div>}
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
          {daily ? '오늘' : '이번 주'}
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
      heads={['주차', '시작일']}
      cols={colsOne(R)}
      days={dailyCols(base, 7 * n)}
      rows={<Stages R={R} off={0} T={7 * n} up={[]} onToggle={toggle} />}
      note={`1주차는 시작일(${md(confirmDay(R))})부터 ${md(addDays(base, 6))}까지예요. 150% 이상 확대하면 하루 단위로 보여요.`}
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
    <Card title="전체 일정" link={null} heads={['', '주 시작일']} cols={cols} days={dailyCols(axis, T)} rows={rows} note="로드맵 시작일부터 7일을 1주로 세요. 150% 이상 확대하면 하루 단위로 보여요." cls="all" />
  );
}

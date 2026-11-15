import { activityTime } from '@/shared/lib/resourceTime';
import { sharedCourses } from './sharedCourses';
import { trackName } from '@/shared/constants/data';
/* 로드맵 일정(간트) 표시 (5차 ganttOne·ganttAll·gtStages·gtCard·gt-fold·설명 상자)
   로드맵이 하나면 '전체 진행' 카드 자리에, 여럿이면 하나로 합쳐 맨 위에 둔다. 이번 주 칸을 칠한다.
   예정 주차가 지나도 늦었다고 표시하지 않는다(스스로 정한 학습 계획). 처음엔 모두 펼치고, 접은 상태는 새로 고칠 때까지만 기억한다.
   도서는 진행 상태를 기록하지 않는 참고 자료라 일정표에 넣지 않는다 */
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { openRecord } from '@/features/roadmap/RecordSheet';
import { ActRow } from '@/features/roadmap/parts';
import { openSheet } from '@/shared/state/ui';
import { useCatalog } from '@/shared/state/catalog';
import { useClockRefresh, useDemoDay } from '@/shared/state/demoClock';
import { useGo } from '@/shared/hooks/useGo';
import { count, isBookResource, st } from '@/shared/lib/plan';
import { Icon } from '@/shared/ui/Icon';
import { addDays, axisAll, colsOne, dailyCols, dayGap, doneFills, gtFillPos, gtPos, md, planStart, planWeeks, weekNow, type GtBar, type GtCol, type GtSpan } from './ganttCalc';

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
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') hide();
    };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', hide, true);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
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
      {/* 막대는 일정 구간(gt-span) 안에서만 자리를 잡는다. 화면이 넓어 날짜 칸을 더 그려도 막대 길이는 그대로다 */}
      <div className="gt-tl"><div className="gt-span">{bar}</div></div>
    </div>
  );
}

/** 스킬·로드맵 막대의 칠: 완료한 하위 활동 막대가 놓인 구간만 칠한다 */
function Fills({ range, bars }: { range: GtSpan; bars: GtBar[] }) {
  return <>{doneFills(range, bars).map((fill) => <i key={fill.left} style={gtFillPos(fill)} />)}</>;
}

/** 로드맵 하나의 스킬·활동 줄. off = 축 첫날부터 이 로드맵 1주차 첫날까지 일 수, T = 축 전체 일 수, up = 위 줄(로드맵)의 접기 열쇠,
    head = 이 로드맵의 활동 막대 전체를 받아 맨 위에 그릴 줄(로드맵 막대) */
function Stages({ R, off, T, up, onToggle, head }: { R: PlanRecord; off: number; T: number; up: string[]; onToggle: (k: string) => void; head?: (bars: GtBar[]) => ReactNode }) {
  const pl = R.plan;
  const base = planStart(R);
  const resources = useCatalog(state => state.res);
  const skillOrder = pl.def.learningSkills?.map(skill => skill.name) || [];
  const acts = pl.acts.filter(activity => !isBookResource(activity.res ? resources[activity.res] : undefined));
  const groups = new Map<string, typeof pl.acts>();
  for (const activity of acts) {
    const resource = activity.res ? resources[activity.res] : undefined;
    const name = activity.skill || activity.skills?.[0] || resource?.skills?.find(skill => skillOrder.includes(skill)) || resource?.skills?.[0] || '기타 활동';
    groups.set(name, [...(groups.get(name) || []), activity]);
  }
  const names = [...skillOrder.filter(name => groups.has(name)), ...[...groups.keys()].filter(name => !skillOrder.includes(name))];
  const courseStarts = [...new Set(acts.flatMap(activity => {
    const resource = activity.res ? resources[activity.res] : undefined;
    return resource?.type === 'course' || resource?.kind === '강좌' ? [activity.wFrom] : [];
  }))].sort((a, b) => a - b);
  const shared=sharedCourses(acts,resources);
  const sharedIds=new Set(shared.map(course=>course.id));
  const when = (f: number, t: number) => `${f === t ? f : `${f}~${t}`}주차 · ${md(addDays(base, 7 * (f - 1)))}~${md(addDays(base, 7 * t - 1))}`;
  const isDone = (activity: (typeof acts)[number]) => st(R.progress, activity.id) === 'done';
  /* 활동 막대의 자리. 스킬·로드맵 막대는 이 구간을 기준으로 칠하므로 그리는 곳과 같은 값을 쓴다 */
  const materialSpan = (materials: typeof acts): GtSpan => ({ from: off + 7 * (Math.min(...materials.map(activity => activity.wFrom)) - 1), to: off + 7 * Math.max(...materials.map(activity => activity.wTo)) });
  const taskSpan = (name: string, a: (typeof acts)[number], t: number): GtSpan => {
    const taskWeek = a.wTo || t;
    const nextCourseWeek = courseStarts.find(week => week > taskWeek) ?? taskWeek + 1;
    const withoutCourse = R.plan.def.materialSchedule?.some(slot => slot.skill === name && slot.weeks === 0);
    return { from: Math.max(0, off + 7 * (taskWeek - 1) + (withoutCourse ? 0 : 3.5)), to: Math.min(T, off + 7 * (withoutCourse ? taskWeek : nextCourseWeek - 0.5)) };
  };
  /** 한 스킬의 활동 줄에 그리는 막대들(자료 학습 한 줄 + 과제마다 한 줄) */
  const skillBars = (name: string, t: number): GtBar[] => {
    const as = groups.get(name) || [];
    const separate = as.filter(activity => activity.res && !sharedIds.has(activity.res));
    return [
      ...(separate.length ? [{ ...materialSpan(separate), done: separate.every(isDone) }] : []),
      ...as.filter(activity => !activity.res).map(a => ({ ...taskSpan(name, a, t), done: isDone(a) })),
    ];
  };
  const sharedBars: GtBar[] = shared.map(course => ({ from: off + 7 * (course.from - 1), to: off + 7 * course.to, done: course.activities.every(isDone) }));
  const allBars: GtBar[] = [...sharedBars];
  const body = (
    <>
      {shared.map(course=>{
        const done=course.activities.every(activity=>st(R.progress,activity.id)==='done');
        const skillLabel=`${course.skills.join(' · ')} 공통`;
        const show=()=>openSheet({title:course.title,sub:skillLabel,body:()=> <div>{course.activities.map(activity=><section key={activity.id}><h3>{activity.skill}</h3><ul className="acts"><ActRow a={activity} R={R}/></ul></section>)}</div>});
        return <Row key={`shared:${course.id}`} lv={1} ins={up}
          label={<button className="gt-a" aria-label={`${course.title} · ${skillLabel} · 관련 스킬 기록 열기`} onClick={show}><span className="gt-name" title={course.title}>{course.title}<small>{skillLabel}</small></span>{done?<Icon name="check" cls="gt-ok"/>:null}</button>}
          bar={<button type="button" className={`gt-bar act gt-materials-open${done?' done':''}`} aria-label={`${course.title} · ${skillLabel} · ${course.from}~${course.to}주차`} onClick={show} style={gtPos(off+7*(course.from-1),off+7*course.to,T)}>{done?<Icon name="check"/>:null}</button>}
          tip={{v:when(course.from,course.to),t:course.title,m:skillLabel}}/>;
      })}
      {(() => {
        interface SkillCluster {
          key: string;
          skills: string[];
          numbers: number[];
          title: string;
          noLabel: string;
          sharedCourse?: (typeof shared)[number];
        }
        const clusters: SkillCluster[] = [];
        const visited = new Set<string>();
        for (let i = 0; i < names.length; i++) {
          const name = names[i];
          if (visited.has(name)) continue;
          const sharedCourse = shared.find(course => course.skills.includes(name));
          if (sharedCourse) {
            const clusterSkills = names.filter(n => sharedCourse.skills.includes(n));
            clusterSkills.forEach(n => visited.add(n));
            const numbers = clusterSkills.map(n => names.indexOf(n) + 1);
            const minNo = Math.min(...numbers);
            const maxNo = Math.max(...numbers);
            const noLabel = minNo === maxNo ? `${minNo}` : (numbers.length === maxNo - minNo + 1 ? `${minNo}~${maxNo}` : numbers.join(', '));
            clusters.push({
              key: `${R.id}:cluster:${clusterSkills.join('+')}`,
              skills: clusterSkills,
              numbers,
              title: clusterSkills.join(' · '),
              noLabel,
              sharedCourse,
            });
          } else {
            visited.add(name);
            const no = i + 1;
            clusters.push({
              key: `${R.id}:cluster:${name}`,
              skills: [name],
              numbers: [no],
              title: name,
              noLabel: `${no}`,
              sharedCourse: undefined,
            });
          }
        }

        return clusters.map(cluster => {
          const allActs = cluster.skills.flatMap(s => groups.get(s) || []);
          // 묶음의 완료 수도 전체와 같은 기준으로 센다(공통 강좌는 하나 · 걸린 활동이 모두 끝나야 완료)
          const { done: dn, t: total } = count({ ...pl, acts: allActs }, R.progress);
          let f: number, t: number;
          if (cluster.sharedCourse) {
            f = cluster.sharedCourse.from;
            const deliverables = allActs.filter(a => !a.res);
            t = deliverables.length ? Math.max(...deliverables.map(a => a.wTo)) : Math.max(...allActs.map(a => a.wTo));
          } else {
            const schedule = pl.def.materialSchedule?.find(row => row.skill === cluster.skills[0]);
            const deliverables = allActs.filter(a => !a.res);
            f = schedule?.startWeek ?? Math.min(...allActs.map(a => a.wFrom));
            // 스킬 전체 구간(schedule.endWeek)에는 도서 주차가 들어 있어, 과제가 없으면 일정표에 남은 활동까지만 그린다
            t = Math.max(...(deliverables.length ? deliverables : allActs).map(a => a.wTo));
          }
          const rangeEnd = Math.min(T, off + 7 * t + (allActs.some(activity => !activity.res) ? 3.5 : 0));
          const range = { from: off + 7 * (f - 1), to: rangeEnd };
          const own = cluster.skills.flatMap(name => skillBars(name, t));
          allBars.push(...own);
          const bars = cluster.sharedCourse ? [sharedBars[shared.indexOf(cluster.sharedCourse)], ...own] : own;

          return (
            <Fragment key={cluster.key}>
              <Row
                lv={1}
                ins={up}
                label={
                  <>
                    <Tg k={cluster.key} name={cluster.title} onToggle={() => onToggle(cluster.key)} />
                    <span className="gt-no">{cluster.noLabel}</span>
                    <span className="gt-name" title={cluster.title}>{cluster.title}</span>
                    <span className="gt-sub">
                      {dn}/{total}
                    </span>
                  </>
                }
                bar={
                  // 활동 줄을 펼쳤으면 활동 막대만 보이게 스킬 막대는 그리지 않는다
                  gtFold.has(cluster.key) ? (
                    <span className="gt-bar sum" style={gtPos(range.from, range.to, T)}>
                      <Fills range={range} bars={bars} />
                    </span>
                  ) : null
                }
                tip={{ v: when(f, t), t: cluster.title, m: `활동 ${total}개 중 ${dn}개 완료` }}
              />
              {cluster.skills.map(name => {
                const as = groups.get(name)!;
                const number = names.indexOf(name) + 1;
                const materials = as.filter(activity => activity.res);
                const separateMaterials = materials.filter(activity => !sharedIds.has(activity.res!));
                const courses = separateMaterials.filter(activity => {
                  const resource = resources[activity.res!];
                  return resource?.type === 'course' || resource?.kind === '강좌';
                }).length;
                // 과제 줄과 같은 기준: 이 줄에 그린 자료를 모두 완료하면 막대를 채운다
                const materialsDone = separateMaterials.length > 0 && separateMaterials.every(activity => st(R.progress, activity.id) === 'done');
                const materialLabel =
                  [courses ? `강좌 ${courses}개` : '', separateMaterials.length > courses ? `기타 ${separateMaterials.length - courses}개` : '']
                    .filter(Boolean)
                    .join(' · ') || '공통 강좌 연결';
                const showMaterials = () =>
                  openSheet({
                    title: `${name} · 학습 자료`,
                    sub: materialLabel,
                    body: () => <ul className="acts">{(separateMaterials.length ? separateMaterials : materials).map(activity => <ActRow key={activity.id} a={activity} R={R} />)}</ul>,
                  });

                return (
                  <Fragment key={`${cluster.key}:${name}`}>
                    {separateMaterials.length > 0 && (
                      <Row
                        lv={2}
                        ins={up.concat(cluster.key)}
                        label={
                          <button className="gt-a" aria-label={`${name} 자료 학습 · ${materialLabel} · 자료 목록 열기`} onClick={showMaterials}>
                            <span className="gt-no">{number}.1</span>
                            <span className="gt-name">
                              자료 학습 <small>{materialLabel}</small>
                            </span>
                            {materialsDone ? <Icon name="check" cls="gt-ok" /> : null}
                          </button>
                        }
                        bar={
                          separateMaterials.length ? (
                            <button
                              type="button"
                              className={`gt-bar act gt-materials-open${materialsDone ? ' done' : ''}`}
                              aria-label={`${name} 학습 자료 열기${materialsDone ? ' · 완료' : ''}`}
                              onClick={showMaterials}
                              style={gtPos(materialSpan(separateMaterials).from, materialSpan(separateMaterials).to, T)}
                            >
                              {materialsDone ? <Icon name="check" /> : null}
                            </button>
                          ) : (
                            <span className="gt-shared-note">공통 강좌 연결 표시 참조</span>
                          )
                        }
                        tip={{
                          v: when(
                            separateMaterials.length ? Math.min(...separateMaterials.map(activity => activity.wFrom)) : f,
                            separateMaterials.length ? Math.max(...separateMaterials.map(activity => activity.wTo)) : t,
                          ),
                          t: `${name} 자료 학습`,
                          m: `${materialLabel} · 클릭하면 개별 자료와 기록을 볼 수 있어요.`,
                        }}
                      />
                    )}
                    {as.filter(activity => !activity.res).map((a, i) => {
                      const task = !a.res;
                      const taskWeek = a.wTo || t;
                      const marker = taskSpan(name, a, t);
                      const activityFrom = a.wFrom || taskWeek;
                      const activityTo = taskWeek;
                      const done = st(R.progress, a.id) === 'done';
                      const no = `${number}.${i + (separateMaterials.length ? 2 : 1)}`;
                      const w = when(activityFrom, activityTo);
                      const m = `${activityTime(a).text} · ${done ? '완료' : '진행 중'}`;
                      return (
                        <Row
                          key={a.id}
                          lv={2}
                          ins={up.concat(cluster.key)}
                          label={
                            <button className="gt-a" aria-label={`${no} ${a.title}, ${w}, ${m}, ${task ? '과제물 제출 열기' : '실행 기록 열기'}`} onClick={() => openRecord(R.id, a.id)}>
                              <span className="gt-no">{no}</span>
                              <span className="gt-name" title={a.title}>{a.title}</span>
                              {done ? <Icon name="check" cls="gt-ok" /> : null}
                            </button>
                          }
                          bar={
                            task ? (
                              <button
                                type="button"
                                className={`gt-bar act gt-task-submit${done ? ' done' : ''}`}
                                aria-label={`${a.title} 과제물 제출`}
                                onClick={() => openRecord(R.id, a.id)}
                                style={gtPos(marker.from, marker.to, T)}
                              >
                                {done ? <Icon name="check" /> : null}
                              </button>
                            ) : (
                              <span className={`gt-bar act${done ? ' done' : ''}`} style={gtPos(off + 7 * (activityFrom - 1), off + 7 * activityTo, T)}>
                                {done ? <Icon name="check" /> : null}
                              </span>
                            )
                          }
                          tip={{ v: w, t: a.title, m }}
                        />
                      );
                    })}
                  </Fragment>
                );
              })}
            </Fragment>
          );
        });
      })()}
    </>
  );
  return <>{head?.(allBars)}{body}</>;
}

/** 하루 칸의 폭은 화면 폭과 상관없이 같게 둔다. 화면이 넓으면 칸을 늘리지 않고 일정 뒤의 날짜를 더 보여 주고,
    일정이 화면보다 길면 옆으로 민다(#224). 주 단위는 일정 전체를 한눈에 보는 용도라 화면에 맞춰 늘린다 */
const DAY_WIDTH = 40;
const WEEK_MIN = 34;

/** 머리 줄(칸 이름 두 줄) + 세로 칸 선·이번 주 칸 + 줄들 + 범례 */
function Card({ title, link, heads, cols, total, days, rows, note, cls }: { title: ReactNode; link: ReactNode; heads: [string, string]; cols: GtCol[]; /** 일정 전체 일 수 */ total: number; /** 첫날부터 n일의 하루 단위 칸 */ days?: (n: number) => GtCol[]; rows: ReactNode; note: string; cls?: string }) {
  const tip = useTip();
  const scroll = useRef<HTMLDivElement>(null);
  /* 처음에는 하루 단위로 보여 준다. 배율(%) 조절은 없애고 일·주 단위만 바꾼다 */
  const [unit, setUnit] = useState<'day' | 'week'>(days ? 'day' : 'week');
  const daily = !!days && unit === 'day';
  const [available, setAvailable] = useState(0);
  useEffect(() => {
    const element = scroll.current;
    if (!element) return;
    const measure = () => {
      const label = element.querySelector<HTMLElement>('.gt-h .gt-l');
      setAvailable(Math.max(0, element.clientWidth - (label?.offsetWidth || 236)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  /* 하루 단위: 화면에 들어가는 만큼 날짜 칸을 더 그린다(막대는 일정 구간 안에만) */
  const dayCount = Math.max(total, Math.floor(available / DAY_WIDTH));
  const visibleCols = daily ? days!(dayCount) : cols;
  const span = daily ? total / dayCount : 1;
  const width = daily ? Math.max(available, dayCount * DAY_WIDTH) : Math.max(available, cols.length * WEEK_MIN);
  const scrolls = width > available + 1;
  /* 주 단위는 하루 단위로 일정이 한 화면에 안 들어올 때만 쓸모가 있어, 그때만 전환 버튼을 보여 준다 */
  const dayOverflows = !!days && total * DAY_WIDTH > available + 1;
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ pointer: number; x: number; left: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const changeUnit = (next: 'day' | 'week') => { tip.hide(); setUnit(next); };
  /* 일정이 칸보다 넓어 옆으로 밀리면 이번 주 칸이 이름 칸 바로 옆(한 칸 띄움)에 오게 맞춘다.
     시연 기준 날짜를 옮기면 지금 표시 중인 칸(주·일 단위)을 다시 따라간다. 시연이 아니면 첫 표시 때만 맞춘다.
     첫 측정 뒤에 일정표 폭이 넓어질 수 있어 측정이 끝나면 한 번 더 맞춘다 */
  const demoDay = useDemoDay();
  const measured = available > 0;
  const toToday = () => {
    const sc = scroll.current;
    const on = sc?.querySelector<HTMLElement>('.gt-h .on');
    if (!sc || !on || sc.scrollWidth <= sc.clientWidth) return;
    const l = sc.querySelector<HTMLElement>('.gt-h .gt-l');
    sc.scrollLeft += on.getBoundingClientRect().left - sc.getBoundingClientRect().left - (l?.offsetWidth || 0) - on.offsetWidth;
  };
  // 단위를 바꾸면 칸 폭이 달라지므로 다시 맞춘다
  useEffect(toToday, [demoDay, measured, unit]);
  return (
    <div className="card gt-card">
      <div className="sec-h">
        <h2 className="st">{title}</h2>
        <div className="gt-view-controls" role="group" aria-label="일정표 보기 조절">
          {dayOverflows || (days && !daily) ? <span className="gt-unit" role="group" aria-label="칸 단위">
            <button type="button" aria-pressed={daily} onClick={() => changeUnit('day')}>일 단위</button>
            <button type="button" aria-pressed={!daily} onClick={() => changeUnit('week')}>주 단위</button>
          </span> : null}
          {/* 옆으로 넘칠 때만 쓸모가 있어 그때만 보여 준다 */}
          {scrolls ? <button type="button" onClick={() => { tip.hide(); toToday(); }}>{daily ? '오늘로' : '이번 주로'}</button> : null}
          {link}
        </div>
      </div>
      <div className={`gt-scroll gt-pan${dragging ? ' is-dragging' : ''}`} ref={scroll} onScroll={event => event.currentTarget.style.setProperty('--gt-scroll-left', `${Math.max(0, event.currentTarget.scrollLeft)}px`)} tabIndex={0} role="region" aria-label="일정표 · 넘치면 좌우로 끌어서 이동"
        onPointerOver={event => { if (!drag.current?.moved) tip.show(event); }} onPointerLeave={tip.hide} onFocus={tip.show}
        onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) tip.hide(); }}
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

        <div className={`gt${cls ? ` ${cls}` : ''}`} style={{ ['--n' as string]: visibleCols.length, ['--gt-span' as string]: span, minWidth: `calc(var(--gl) + ${width}px)` }}>
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
          완료한 활동
        </span>
        <span>
          <i className="k-left" />
          남은 활동
        </span>
        <span>
          <i className="k-sum"><i /><i /></i>
          스킬·로드맵 진행(완료한 구간)
        </span>
        <span>
          <i className="k-now" />
          {daily ? '오늘' : '이번 주'}
        </span>
        <span className="gt-note">{note} 도서는 일정표에 넣지 않아요.</span>
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
  useClockRefresh();
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
      total={7 * n}
      days={(count) => dailyCols(base, count)}
      rows={<Stages R={R} off={0} T={7 * n} up={[]} onToggle={toggle} />}
      note={`1주차는 시작일(${md(base)})부터 ${md(addDays(base, 6))}까지예요.`}
    />
  );
}

export function GanttAll({ list, onMove }: { list: PlanRecord[]; onMove?: (id: string, offset: number) => void }) {
  useClockRefresh();
  const go = useGo();
  const toggle = useFold();
  const { axis, starts, T, cols } = axisAll(list);
  const rows = list.map((R, i) => {
    const pl = R.plan;
    const c = count(pl, R.progress);
    const off = dayGap(axis, starts[i]);
    const w = planWeeks(pl);
    const wk = weekNow(R);
    const at = `${wk < 1 ? `${md(starts[i])} 시작 / ` : wk <= w ? `지금 ${wk}주차 / ` : ''}전체 ${w}주`;
    return (
      <div className="gt-roadmap-group" key={R.id}>
        <Stages R={R} off={off} T={T} up={[R.id]} onToggle={toggle} head={(bars) => (
        <Row
          lv={0}
          ins={[]}
          label={
            <>
              <Tg k={R.id} name={pl.displayTitle || pl.goal} onToggle={() => toggle(R.id)} />
              <button className="gt-r" onClick={() => go(paths.roadmap(R.id))}>
                <span className="gt-name" title={pl.displayTitle || pl.goal}>{pl.displayTitle || pl.goal}</span>
                <small>
                  {at} · {trackName(pl.opt, pl.name)}
                </small>
              </button>
              {onMove && list.length > 1 && <>
                <button type="button" className="gt-move" aria-label={`${pl.displayTitle || pl.goal} 위로`} disabled={i === 0} onClick={() => onMove(R.id, -1)}>↑</button>
                <button type="button" className="gt-move" aria-label={`${pl.displayTitle || pl.goal} 아래로`} disabled={i === list.length - 1} onClick={() => onMove(R.id, 1)}>↓</button>
              </>}
            </>
          }
          bar={
            <span className="gt-bar rm" style={gtPos(off, off + 7 * w, T)}>
              <Fills range={{ from: off, to: off + 7 * w }} bars={bars} />
            </span>
          }
          tip={{ v: `${md(starts[i])}~${md(addDays(starts[i], 7 * w - 1))} · ${at}`, t: pl.displayTitle || pl.goal, m: `${trackName(pl.opt, pl.name)} · 버전 ${pl.version} · 활동 ${c.t}개 중 ${c.done}개 완료` }}
        />
        )} />
      </div>
    );
  });
  return (
    <Card title="전체 일정" link={null} heads={['', '주 시작일']} cols={cols} total={T} days={(count) => dailyCols(axis, count)} rows={rows} note="로드맵 시작일부터 7일을 1주로 세요." cls="all" />
  );
}

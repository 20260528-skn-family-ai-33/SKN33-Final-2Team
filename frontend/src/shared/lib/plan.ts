/* 로드맵 계산 (화면 표시용 · 저장할 계획은 서버가 같은 규칙으로 다시 계산) — 5차 gp-parts.js 계산 부분을 옮김.
   부서장 화면도 같은 함수를 쓰도록 상태를 인자로 받는다(5차는 GP.asState 로 전역 S 를 바꿔 끼웠음) */
import type { OptionDef, Prefs } from '@/api/types/draft';
import type { Activity, PendingRevision, PlanContent, PlanParams, PlanRecord, Progress } from '@/api/types/plan';
import type { Resource } from '@/api/types/catalog';
import { D } from '@/shared/constants/data';
import { resOf } from '@/shared/state/catalog';
import { hrs, won } from './format';
import { prefText } from './prefs';
import { resourceSource } from './resourceSource';

export const stageName = (n: number): string => D.stages.find((s) => s.n === n)?.name || '';

export function buildPlan(def: OptionDef, prm: Partial<PlanParams>, goal: string): PlanContent {
  const p: PlanParams = { start: 1, hours: 4, format: 'mixed', patch: {}, ...prm };
  const acts: Activity[] = def.acts
    .filter((a) => a.stage >= p.start)
    .map((a) => {
      const r = resOf(a.res);
      const x: Activity = {
        id: a.id,
        stage: a.stage,
        title: a.title,
        res: a.res || null,
        task: !a.res,
        how: a.how || '',
        hours: a.res ? (r && r.hours != null ? r.hours : a.hours || 2) : a.hours || 0,
        wFrom: 0,
        wTo: 0,
        hoursEstimated: r ? (r.estimated || []).includes('hours') : undefined,
        hoursBasis: r?.timeNote || undefined,
      };
      // 과제가 다루는 스킬(에이전트가 고른 팀 DB 스킬 이름 · 10/23 · 스킬 지도에서 씀). 자료 활동은 자료에 붙은 스킬을 쓴다
      if (!a.res && a.skills && a.skills.length) x.skills = a.skills.slice();
      if (p.patch[a.id]) Object.assign(x, p.patch[a.id]);
      return x;
    });
  let cum = 0;
  acts.forEach((a) => {
    a.wFrom = Math.floor(cum / p.hours) + 1;
    cum += a.hours;
    a.wTo = Math.max(a.wFrom, Math.ceil(cum / p.hours));
  });
  const weeks = Math.max(1, Math.ceil(cum / p.hours));
  const resIds = [...new Set(acts.map((a) => a.res).filter(Boolean) as string[])];
  const cost = resIds.reduce((s, r) => s + (resOf(r)?.cost || 0), 0);
  const costUnknown = resIds.some((r) => !resOf(r) || resOf(r)?.cost == null);
  return {
    displayTitle: def.displayTitle,
    opt: def.id,
    name: def.name,
    short: def.short,
    tagline: def.tagline,
    goal,
    def,
    params: p,
    start: p.start,
    hours: p.hours,
    format: p.format,
    acts,
    totalH: cum,
    weeks,
    cost,
    costUnknown,
  };
}

export const range = (acts: Activity[]): string => {
  const a = Math.min(...acts.map((x) => x.wFrom));
  const b = Math.max(...acts.map((x) => x.wTo));
  return a === b ? `${a}주차` : `${a}~${b}주차`;
};

/** 활동 진행 상태: 완료가 아니면 진행 중 */
export const st = (progress: Record<string, Progress> | undefined, id: string): 'done' | 'doing' => (progress?.[id]?.status === 'done' ? 'done' : 'doing');
export const count = (pl: PlanContent, progress?: Record<string, Progress>) => ({ t: pl.acts.length, done: pl.acts.filter((a) => st(progress, a.id) === 'done').length });
export const nextAct = (pl: PlanContent, progress?: Record<string, Progress>) => pl.acts.find((a) => st(progress, a.id) !== 'done');
export const curStage = (pl: PlanContent, progress?: Record<string, Progress>) => (nextAct(pl, progress) || pl.acts[pl.acts.length - 1]).stage;
export const stageActs = (pl: PlanContent, n: number) => pl.acts.filter((a) => a.stage === n);
export const recProgress = (R: PlanRecord | null | undefined) => (R && R.progress) || {};

const actTx = (x: Activity) => `${x.title} · ${x.stage}단계 · ${hrs(x.hours)}`;

export interface DiffItem {
  k: string;
  a: string;
  b: string;
}

export function diff(a: PlanContent, b: PlanContent, pd?: Pick<PendingRevision, 'prefsFrom' | 'prefsTo'>): DiffItem[] {
  const ch: DiffItem[] = [];
  const push = (k: string, x: string, y: string) => ch.push({ k, a: x, b: y });
  if (a.opt !== b.opt) push('관점', `${a.opt} ${a.name}`, `${b.opt} ${b.name}`);
  if (pd && pd.prefsFrom && pd.prefsTo)
    (
      [
        ['format', '학습 방식'],
        ['cert', '자격증 계획'],
        ['weeks', '정해진 기간'],
        ['budget', '교육 예산'],
        ['etc', '일정·환경 제약'],
      ] as [keyof Prefs, string][]
    ).forEach(([k, l]) => {
      const x = prefText(k, pd.prefsFrom as Prefs);
      const y = prefText(k, pd.prefsTo as Prefs);
      if (x !== y) push(l, x, y);
    });
  if (a.start !== b.start) push('시작 단계', `${a.start}단계 ${stageName(a.start)}`, `${b.start}단계 ${stageName(b.start)}`);
  if (a.hours !== b.hours) push('주당 시간', hrs(a.hours), hrs(b.hours));
  const am = Object.fromEntries(a.acts.map((x) => [x.id, x]));
  const bm = Object.fromEntries(b.acts.map((x) => [x.id, x]));
  b.acts.forEach((x) => {
    const y = am[x.id];
    if (!y) push('활동 추가', '—', actTx(x));
    else if (y.title !== x.title || y.hours !== x.hours || y.stage !== x.stage) push('활동 변경', actTx(y), actTx(x));
  });
  a.acts.forEach((y) => {
    if (!bm[y.id]) push('활동 제외', actTx(y), '—');
  });
  if (a.weeks !== b.weeks) push('전체 기간', a.weeks + '주', b.weeks + '주');
  if (a.cost !== b.cost) push('예상 비용', won(a.cost), won(b.cost));
  return ch;
}

export const costText = (r: Resource | null | undefined): string =>
  !r ? '' : r.cost == null ? (r.kind === '자격' ? '응시료 확인 필요' : r.kind === '도서' ? '가격 확인 필요' : '비용 확인 필요') : r.cost ? won(r.cost) : '무료';

export function actMeta(a: Pick<Activity, 'task' | 'res'>): string {
  if (a.task) return '직접 수행 과제';
  const r = resOf(a.res);
  if (!r) return '등록 자료 (정보를 불러오지 못했어요)';
  return `${r.kind} · ${resourceSource(r)}${r.real ? '' : ' · 가상'} · ${costText(r)}`;
}

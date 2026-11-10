/* 일정 주차는 로드맵을 처음 시작한 날짜부터 7일씩 계산한다. */
import type { PlanContent, PlanRecord } from '@/api/types/plan';
import { clockNow } from '@/shared/state/demoClock';

const DAY = 864e5;
export const ymd = (s: string | null | undefined): Date | null => {
  const [y, m, d] = String(s || '').slice(0, 10)
    .split('-')
    .map(Number);
  return y ? new Date(y, m - 1, d) : null;
};
export const today0 = (now: Date = clockNow()): Date => new Date(now.getFullYear(), now.getMonth(), now.getDate());
export const addDays = (d: Date, n: number): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
export const dayGap = (a: Date, b: Date): number => Math.round((b.getTime() - a.getTime()) / DAY);
export const md = (d: Date): string => `${d.getMonth() + 1}/${d.getDate()}`;
export const monthDay = (d: Date): string => `${d.getMonth() + 1}월 ${d.getDate()}일`;
export const monday = (d: Date): Date => addDays(d, -((d.getDay() + 6) % 7));
export const confirmDay = (R: Pick<PlanRecord, 'createdAt' | 'plan'>, now?: Date): Date => ymd(R.createdAt) || ymd(R.plan.confirmedAt) || today0(now);
/** 1주차 첫날. 끝난 다음 주로 미룬 로드맵만 startDate 가 있고, 나머지는 확정한 날이다 */
export const planStart = (R: Pick<PlanRecord, 'createdAt' | 'plan'>, now?: Date): Date => ymd(R.plan.startDate) || confirmDay(R, now);
export const planWeeks = (pl: PlanContent): number => Math.max(1, pl.weeks || 0, ...pl.acts.map((a) => a.wTo));
/** 시작일 전이면 1보다 작다. 화면에 주차로 보일 때는 startsLater 로 먼저 가른다 */
export const weekNow = (R: Pick<PlanRecord, 'createdAt' | 'plan'>, now?: Date): number => Math.floor(dayGap(planStart(R, now), today0(now)) / 7) + 1;
export const startsLater = (R: Pick<PlanRecord, 'createdAt' | 'plan'>, now?: Date): boolean => planStart(R, now) > today0(now);
/** 로드맵들이 모두 끝난 다음 주의 첫날. 이미 끝났으면 오늘이다(서버 plans.next_start 와 같은 규칙) */
export const followingStart = (list: Pick<PlanRecord, 'createdAt' | 'plan'>[], now?: Date): Date =>
  list.reduce((latest, R) => {
    const next = addDays(planStart(R, now), 7 * planWeeks(R.plan));
    return next > latest ? next : latest;
  }, today0(now));

/** 막대 위치: 축 첫날부터 from~to 일(to 는 포함하지 않음). 막대 사이에 2px 틈을 둔다 */
export const gtPos = (from: number, to: number, T: number) => ({ left: `calc(${(from / T) * 100}% + 1px)`, width: `calc(${((to - from) / T) * 100}% - 2px)` });

export interface GtCol {
  top: string | number;
  sub: string | number;
  on: boolean;
  weekStart?: boolean;
}

/** 로드맵 하나: 칸 = 그 로드맵의 주차(아래에 각 주의 시작 날짜) */
export function colsOne(R: PlanRecord, now?: Date): GtCol[] {
  const base = planStart(R, now);
  const n = planWeeks(R.plan);
  const cur = weekNow(R, now);
  return Array.from({ length: n }, (_, i) => ({ top: i + 1, sub: md(addDays(base, 7 * i)), on: i + 1 === cur }));
}

/** 여럿: 칸 = 최초 시작일부터 7일 간격 */
export function axisAll(list: PlanRecord[], now?: Date) {
  const starts = list.map((R) => planStart(R, now));
  const axis = new Date(Math.min(...starts.map((d) => d.getTime())));
  const nowGap = dayGap(axis, today0(now));
  const n = Math.ceil(Math.max(...list.map((R, i) => dayGap(axis, starts[i]) + 7 * planWeeks(R.plan))) / 7);
  const cols: GtCol[] = Array.from({ length: n }, (_, i) => {
    const d = addDays(axis, 7 * i);
    return { top: i === 0 || d.getDate() <= 7 ? `${d.getMonth() + 1}월` : '', sub: d.getDate(), on: nowGap >= 7 * i && nowGap < 7 * (i + 1) };
  });
  return { axis, starts, n, T: 7 * n, cols };
}

/** 확대된 일정표: 하루 한 칸, 오늘만 강조한다. */
export function dailyCols(base: Date, days: number, now?: Date): GtCol[] {
  const current = dayGap(base, today0(now));
  return Array.from({ length: days }, (_, i) => {
    const day = addDays(base, i);
    return { top: i === 0 || day.getDate() === 1 ? `${day.getMonth() + 1}월` : '', sub: day.getDate(), on: i === current, weekStart: i % 7 === 0 };
  });
}

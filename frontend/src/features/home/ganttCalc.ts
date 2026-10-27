/* 로드맵 일정 계산 (간트 · WBS 방식: 로드맵 > 단계 > 활동 · 10/22 사용자 결정 · 5차 gp-app.js 를 옮김)
   계획에는 활동마다 n주차(주당 학습 시간으로 나눈 값)만 있어서, 1주차 = 그 로드맵을 처음 확정한 날(createdAt)이 든 주(월~일)로 놓고 날짜를 셈한다.
   칸 하나는 확정한 요일과 관계없이 늘 월~일 7일이다(10/23 사용자 결정 · 목요일에 확정해도 그 주 월요일부터 1주차) */
import type { PlanContent, PlanRecord } from '@/api/types/plan';

const DAY = 864e5;
export const ymd = (s: string | null | undefined): Date | null => {
  const [y, m, d] = String(s || '')
    .split('-')
    .map(Number);
  return y ? new Date(y, m - 1, d) : null;
};
export const today0 = (now: Date = new Date()): Date => new Date(now.getFullYear(), now.getMonth(), now.getDate());
export const addDays = (d: Date, n: number): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
export const dayGap = (a: Date, b: Date): number => Math.round((b.getTime() - a.getTime()) / DAY);
export const md = (d: Date): string => `${d.getMonth() + 1}/${d.getDate()}`;
export const monday = (d: Date): Date => addDays(d, -((d.getDay() + 6) % 7));
export const confirmDay = (R: Pick<PlanRecord, 'createdAt' | 'plan'>, now?: Date): Date => ymd(R.createdAt) || ymd(R.plan.confirmedAt) || today0(now);
export const planStart = (R: Pick<PlanRecord, 'createdAt' | 'plan'>, now?: Date): Date => monday(confirmDay(R, now));
export const planWeeks = (pl: PlanContent): number => Math.max(1, pl.weeks || 0, ...pl.acts.map((a) => a.wTo));
export const weekNow = (R: Pick<PlanRecord, 'createdAt' | 'plan'>, now?: Date): number => Math.floor(dayGap(planStart(R, now), today0(now)) / 7) + 1;

/** 막대 위치: 축 첫날부터 from~to 일(to 는 포함하지 않음). 막대 사이에 2px 틈을 둔다 */
export const gtPos = (from: number, to: number, T: number) => ({ left: `calc(${(from / T) * 100}% + 1px)`, width: `calc(${((to - from) / T) * 100}% - 2px)` });

export interface GtCol {
  top: string | number;
  sub: string | number;
  on: boolean;
}

/** 로드맵 하나: 칸 = 그 로드맵의 주차(아래에 그 주 월요일 날짜) */
export function colsOne(R: PlanRecord, now?: Date): GtCol[] {
  const base = planStart(R, now);
  const n = planWeeks(R.plan);
  const cur = weekNow(R, now);
  return Array.from({ length: n }, (_, i) => ({ top: i + 1, sub: md(addDays(base, 7 * i)), on: i + 1 === cur }));
}

/** 여럿: 칸 = 달력 주(맨 앞 로드맵의 첫 주부터) */
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

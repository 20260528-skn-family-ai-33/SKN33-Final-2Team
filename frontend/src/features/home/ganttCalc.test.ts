/* 홈 로드맵 일정 간트: 확정한 날이 든 주의 월요일부터 주차를 센다 */
import { describe, expect, it } from 'vitest';
import type { PlanContent, PlanRecord } from '@/api/types/plan';
import { colsOne, monday, planWeeks, weekNow } from './ganttCalc';

const rec = (createdAt: string, weeks: number): PlanRecord => ({ createdAt, plan: { weeks, acts: [] } as unknown as PlanContent }) as PlanRecord;
// 2026-10-26 은 월요일
const NOW = new Date(2026, 9, 26, 15, 0);

describe('ganttCalc', () => {
  it('어느 요일이든 그 주 월요일로 맞춘다', () => {
    expect(monday(new Date(2026, 9, 29)).getDate()).toBe(26); // 목
    expect(monday(new Date(2026, 10, 1)).getDate()).toBe(26); // 일
    expect(monday(new Date(2026, 9, 26)).getDate()).toBe(26); // 월
  });

  it('확정한 주를 1주차로 센다', () => {
    expect(weekNow(rec('2026-10-28', 4), NOW)).toBe(1); // 수요일 확정 → 그 주 월요일(10/26)부터
    expect(weekNow(rec('2026-10-12', 4), NOW)).toBe(3);
  });

  it('주차 칸 아래에 그 주 월요일 날짜를 쓰고 이번 주를 표시한다', () => {
    const cols = colsOne(rec('2026-10-14', 3), NOW);
    expect(cols.map((c) => [c.top, c.sub, c.on])).toEqual([
      [1, '10/12', false],
      [2, '10/19', false],
      [3, '10/26', true],
    ]);
  });

  it('계획 주 수보다 늦게 끝나는 활동이 있으면 그 주까지 늘린다', () => {
    const pl = { weeks: 2, acts: [{ wTo: 5 }] } as unknown as PlanContent;
    expect(planWeeks(pl)).toBe(5);
  });
});

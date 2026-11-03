/* 홈 로드맵 일정 간트: 실제 시작일부터 7일씩 주차를 센다 */
import { describe, expect, it } from 'vitest';
import type { PlanContent, PlanRecord } from '@/api/types/plan';
import { axisAll, colsOne, dailyCols, md, monday, planStart, planWeeks, weekNow } from './ganttCalc';

const rec = (createdAt: string, weeks: number): PlanRecord => ({ createdAt, plan: { weeks, acts: [] } as unknown as PlanContent }) as PlanRecord;
// 2026-10-26 은 월요일
const NOW = new Date(2026, 9, 26, 15, 0);

describe('ganttCalc', () => {
  it('어느 요일이든 그 주 월요일로 맞춘다', () => {
    expect(monday(new Date(2026, 9, 29)).getDate()).toBe(26); // 목
    expect(monday(new Date(2026, 10, 1)).getDate()).toBe(26); // 일
    expect(monday(new Date(2026, 9, 26)).getDate()).toBe(26); // 월
  });

  it('시작일부터 7일이 지나야 다음 주차로 넘어간다', () => {
    expect(weekNow(rec('2026-10-21', 4), NOW)).toBe(1); // 시작일에서 5일 경과
    expect(weekNow(rec('2026-10-12', 4), NOW)).toBe(3);
  });

  it('주차 칸 아래에 해당 주 시작일을 쓰고 현재 주차를 표시한다', () => {
    const cols = colsOne(rec('2026-10-14', 3), NOW);
    expect(cols.map((c) => [c.top, c.sub, c.on])).toEqual([
      [1, '10/14', false],
      [2, '10/21', true],
      [3, '10/28', false],
    ]);
  });

  it('계획 주 수보다 늦게 끝나는 활동이 있으면 그 주까지 늘린다', () => {
    const pl = { weeks: 2, acts: [{ wTo: 5 }] } as unknown as PlanContent;
    expect(planWeeks(pl)).toBe(5);
  });
});

it('목요일에 시작하면 다음 수요일까지 1주차다', () => {
  const record = rec('2026-10-29', 3);
  expect(md(planStart(record))).toBe('10/29');
  expect(weekNow(record, new Date(2026, 10, 4))).toBe(1);
  expect(weekNow(record, new Date(2026, 10, 5))).toBe(2);
});
it('통합 축에서도 각 로드맵의 실제 시작일 차이를 유지한다', () => {
  const value = axisAll([rec('2026-10-29', 2), rec('2026-11-1', 2)], NOW);
  expect(value.starts.map(md)).toEqual(['10/29','11/1']);
});
it('일 단위 칸은 월 경계와 오늘 표시를 정확하게 만든다', () => {
  const days = dailyCols(new Date(2026, 9, 29), 7, new Date(2026, 10, 1));
  expect(days.map(day => day.sub)).toEqual([29,30,31,1,2,3,4]);
  expect(days[3]).toEqual({top:'11월',sub:1,on:true,weekStart:false});
  expect(md(planStart(rec('2026-10-29T12:30:00',2)))).toBe('10/29');
});

it('일 단위에서도 7일마다 주 시작 경계를 유지한다', () => {
  const days = dailyCols(new Date(2026, 9, 29), 21);
  expect(days.flatMap((day, index) => day.weekStart ? [index] : [])).toEqual([0,7,14]);
});

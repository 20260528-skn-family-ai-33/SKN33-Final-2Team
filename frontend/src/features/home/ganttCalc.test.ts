/* 홈 로드맵 일정 간트: 실제 시작일부터 7일씩 주차를 센다 */
import { describe, expect, it } from 'vitest';
import type { PlanContent, PlanRecord } from '@/api/types/plan';
import { axisAll, colsOne, dailyCols, doneFills, followingStart, gtFillPos, md, monday, planStart, planWeeks, startsLater, weekNow } from './ganttCalc';

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

const scheduled = (createdAt: string, startDate: string, weeks: number) => ({ createdAt, plan: { weeks, acts: [], startDate } as unknown as PlanContent }) as PlanRecord;

it('끝난 다음 주로 미룬 로드맵은 정해 둔 시작일부터 주차를 센다', () => {
  const record = scheduled('2026-10-26', '2026-11-09', 2);
  expect(md(planStart(record))).toBe('11/9');
  expect(startsLater(record, new Date(2026, 10, 8))).toBe(true);
  expect(weekNow(record, new Date(2026, 10, 8))).toBeLessThan(1);
  expect(startsLater(record, new Date(2026, 10, 9))).toBe(false);
  expect(weekNow(record, new Date(2026, 10, 9))).toBe(1);
});
it('시작 전 로드맵은 일정표에 이번 주 칸이 없다', () => {
  expect(colsOne(scheduled('2026-10-26', '2026-11-09', 2), NOW).some((col) => col.on)).toBe(false);
});
it('끝난 다음 주는 마지막 주차 다음 날이고, 여럿이면 가장 늦게 끝나는 로드맵을 따른다', () => {
  expect(md(followingStart([rec('2026-10-21', 4)], NOW))).toBe('11/18');
  expect(md(followingStart([rec('2026-10-21', 4), rec('2026-10-26', 5)], NOW))).toBe('11/30');
  expect(md(followingStart([rec('2026-10-21', 2), scheduled('2026-10-21', '2026-11-04', 2)], NOW))).toBe('11/18');
});
it('진행 중인 로드맵의 기간이 이미 지났으면 오늘을 넘겨 준다', () => {
  expect(md(followingStart([rec('2026-09-01', 2)], NOW))).toBe('10/26');
});

it('일 단위에서도 7일마다 주 시작 경계를 유지한다', () => {
  const days = dailyCols(new Date(2026, 9, 29), 21);
  expect(days.flatMap((day, index) => day.weekStart ? [index] : [])).toEqual([0,7,14]);
});

describe('doneFills: 상위 막대는 완료한 하위 활동 막대의 구간만 칠한다', () => {
  // 4주(28일) 스킬: 1~2주 강좌, 2주 중반~3주 실습(강좌와 겹침), 4주 과제
  const range = { from: 0, to: 28 };
  const bars = (course: boolean, practice: boolean, task: boolean) => [
    { from: 0, to: 14, done: course },
    { from: 10.5, to: 21, done: practice },
    { from: 21, to: 28, done: task },
  ];

  it('완료한 활동이 없으면 아무것도 칠하지 않는다', () => {
    expect(doneFills(range, bars(false, false, false))).toEqual([]);
    expect(doneFills(range, [])).toEqual([]);
  });

  it('모두 완료하면 전체를 칠한다(활동 막대가 없는 날이 끼어 있어도)', () => {
    expect(doneFills(range, bars(true, true, true))).toEqual([{ left: 0, width: 100 }]);
    expect(doneFills(range, [{ from: 0, to: 7, done: true }, { from: 21, to: 28, done: true }])).toEqual([{ left: 0, width: 100 }]);
  });

  it('앞쪽만 완료하면 앞쪽 구간만 칠한다', () => {
    expect(doneFills(range, bars(true, false, false))).toEqual([{ left: 0, width: 50 }]);
  });

  it('뒤쪽만 완료하면 앞은 비우고 뒤쪽만 칠한다', () => {
    expect(doneFills(range, bars(false, false, true))).toEqual([{ left: 75, width: 25 }]);
  });

  it('앞과 뒤만 완료하면 가운데가 빈다', () => {
    const middleOpen = [
      { from: 0, to: 7, done: true },
      { from: 7, to: 21, done: false },
      { from: 21, to: 28, done: true },
    ];
    expect(doneFills(range, middleOpen)).toEqual([{ left: 0, width: 25 }, { left: 75, width: 25 }]);
  });

  it('기간이 겹치는 두 활동 중 하나만 완료하면 그 활동의 구간만 칠한다', () => {
    expect(doneFills(range, bars(false, true, false))).toEqual([{ left: 37.5, width: 37.5 }]);
  });

  it('겹치거나 맞닿은 완료 구간은 하나로 합친다', () => {
    expect(doneFills(range, bars(true, true, false))).toEqual([{ left: 0, width: 75 }]); // 겹침
    expect(doneFills(range, bars(false, true, true))).toEqual([{ left: 37.5, width: 62.5 }]); // 맞닿음
  });

  it('상위 막대 밖으로 나간 부분은 잘라 내고, 축 중간에서 시작하는 막대는 그 막대 기준으로 계산한다', () => {
    const fills = doneFills({ from: 14, to: 42 }, [
      { from: 7, to: 21, done: true },
      { from: 21, to: 35, done: false },
      { from: 38.5, to: 49, done: true },
      { from: 0, to: 7, done: true }, // 완전히 밖
    ]);
    expect(fills).toEqual([{ left: 0, width: 25 }, { left: 87.5, width: 12.5 }]);
  });

  it('칠한 구간의 끝을 양옆 1px 씩 줄어든 활동 막대의 끝과 맞춘다', () => {
    expect(gtFillPos({ left: 0, width: 100 })).toEqual({ left: 'calc(0% + 0px)', width: 'calc(100% + 0px)' });
    expect(gtFillPos({ left: 50, width: 25 })).toEqual({ left: 'calc(50% + 1px)', width: 'calc(25% + -1.5px)' });
  });
});

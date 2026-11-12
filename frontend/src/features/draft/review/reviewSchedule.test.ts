import { describe, expect, it } from 'vitest';
import type { PlanContent } from '@/api/types/plan';
import { reviewSchedule, weekDates, weekLabel } from './reviewSchedule';

type Input = Parameters<typeof reviewSchedule>[0];
const act = (id: string, skill: string, res: string | null, hours: number, wFrom: number, wTo: number) =>
  ({ id, skill, res, hours, wFrom, wTo, title: `${id} 제목`, stage: 1 }) as unknown as PlanContent['acts'][number];

function plan(overrides: Partial<NonNullable<PlanContent['def']['learningReport']>> = {}, acts = [
  act('c1', 'SQL', 'course-1', 2, 1, 1), act('t1', 'SQL', null, 4, 1, 1), act('c2', 'Bash', 'course-2', 1, 2, 3),
]): Input {
  const learningReport = {
    recommendations: { skills: [
      { name: 'SQL', courses: [{ id: 'course-1', title: 'SQL 강좌' }], books: [{ id: 'book-1', title: 'SQL 책' }] },
      { name: 'Bash', courses: [{ id: 'course-2', title: 'Bash 강좌' }], books: [] },
    ] },
    choices: { SQL: { course: 'course-1', books: ['book-1'] }, Bash: { course: 'course-2', books: [] } },
    skillOrder: ['SQL', 'Bash'],
    durationEstimates: { SQL: { startWeek: 1, endWeek: 1 }, Bash: { startWeek: 2, endWeek: 3 } },
    ...overrides,
  };
  return { def: { learningReport } as unknown as PlanContent['def'], acts };
}

describe('7단계 주차별 일정', () => {
  it('스킬 순서대로 강좌·도서·선택한 과제를 묶는다', () => {
    const rows = reviewSchedule(plan());
    expect(rows.map(row => row.skill)).toEqual(['SQL', 'Bash']);
    expect(rows[0].items).toEqual([
      { kind: 'course', title: 'SQL 강좌', hours: 2 },
      { kind: 'book', title: 'SQL 책' },
      { kind: 'task', title: 't1 제목', hours: 4 },
    ]);
    expect(weekLabel(rows[0])).toBe('1주차');
    expect(weekLabel(rows[1])).toBe('2~3주차');
  });

  it('뺀 과제는 일정에 나오지 않는다(계획에는 선택한 활동만 들어온다)', () => {
    const rows = reviewSchedule(plan({}, [act('c1', 'SQL', 'course-1', 2, 1, 1), act('c2', 'Bash', 'course-2', 1, 2, 3)]));
    expect(rows[0].items.some(item => item.kind === 'task')).toBe(false);
  });

  it('제외한 스킬은 건너뛰고, 서버 주차가 없으면 활동이 걸친 주차를 쓴다', () => {
    const rows = reviewSchedule(plan({
      choices: { SQL: { course: 'course-1', books: [], enabled: false }, Bash: { course: 'course-2', books: [] } },
      durationEstimates: undefined,
    }));
    expect(rows.map(row => row.skill)).toEqual(['Bash']);
    expect([rows[0].startWeek, rows[0].endWeek]).toEqual([2, 3]);
  });

  it('학습 자료 정보가 없는 계획은 빈 일정이다', () => {
    expect(reviewSchedule({ def: {} as PlanContent['def'], acts: [] })).toEqual([]);
  });

  it('주차 구간을 1주차 첫날 기준 날짜로 바꾼다', () => {
    const start = new Date(2026, 10, 12);
    expect(weekDates(start, { startWeek: 1, endWeek: 1 })).toBe('11/12 ~ 11/18');
    expect(weekDates(start, { startWeek: 2, endWeek: 3 })).toBe('11/19 ~ 12/2');
    expect(weekDates(start, { startWeek: null, endWeek: null })).toBe('');
    expect(weekLabel({ startWeek: null, endWeek: 2 })).toBe('주차 미정');
  });
});

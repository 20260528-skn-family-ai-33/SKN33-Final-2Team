/* 7단계 주차별 일정(#224): 확정 전에 스킬마다 언제 무엇을 하는지 한눈에 보여 주기 위한 계산.
   reviewPlan 이 만든 계획(선택한 활동만 들어 있다)만 보고 만든다 */
import type { PlanContent } from '@/api/types/plan';
import { addDays, md } from '@/features/home/ganttCalc';

export interface ScheduleItem {
  kind: 'course' | 'book' | 'task';
  title: string;
  /** 계획에 잡힌 시간. 도서는 일정에 넣지 않으므로 없다 */
  hours?: number;
}
export interface ScheduleRow {
  skill: string;
  startWeek: number | null;
  endWeek: number | null;
  items: ScheduleItem[];
}

export function reviewSchedule(plan: Pick<PlanContent, 'def' | 'acts'>): ScheduleRow[] {
  const report = plan.def.learningReport;
  if (!report) return [];
  return report.skillOrder.filter(name => report.choices[name]?.enabled !== false).flatMap(name => {
    const skill = report.recommendations.skills.find(row => row.name === name);
    if (!skill) return [];
    const own = plan.acts.filter(act => act.skill === name);
    const items: ScheduleItem[] = [
      ...skill.courses.map(course => ({ kind: 'course' as const, title: course.title, hours: own.find(act => act.res === course.id)?.hours })),
      ...skill.books.map(book => ({ kind: 'book' as const, title: book.title })),
      ...own.filter(act => !act.res).map(task => ({ kind: 'task' as const, title: task.title, hours: task.hours })),
    ];
    const estimate = report.durationEstimates?.[name];
    // 서버가 계산한 주차가 없으면(이전 형식) 그 스킬 활동이 걸친 주차로 대신한다
    const weeks = own.flatMap(act => [act.wFrom, act.wTo]).filter(week => week > 0);
    const startWeek = estimate?.startWeek ?? (weeks.length ? Math.min(...weeks) : null);
    const endWeek = estimate?.endWeek ?? (weeks.length ? Math.max(...weeks) : null);
    return [{ skill: name, startWeek, endWeek, items }];
  });
}

export function weekLabel(row: Pick<ScheduleRow, 'startWeek' | 'endWeek'>): string {
  if (row.startWeek == null || row.endWeek == null) return '주차 미정';
  return row.startWeek === row.endWeek ? `${row.startWeek}주차` : `${row.startWeek}~${row.endWeek}주차`;
}

/** 1주차 첫날(start)을 기준으로 그 주차 구간의 날짜를 적는다 */
export function weekDates(start: Date, row: Pick<ScheduleRow, 'startWeek' | 'endWeek'>): string {
  if (row.startWeek == null || row.endWeek == null) return '';
  return `${md(addDays(start, (row.startWeek - 1) * 7))} ~ ${md(addDays(start, row.endWeek * 7 - 1))}`;
}

export type SkillChoice = { course: string | null; courses?: string[]; books: string[]; enabled?: boolean };
export type Choices = Record<string, SkillChoice>;
export function displayOrder(order: string[], choices: Choices): string[] {
  return [...order.filter(name => choices[name]?.enabled !== false), ...order.filter(name => choices[name]?.enabled === false)];
}

export const DURATION_METHOD = 'resource-hours-books/v3';
export type DurationEstimate = {
  method?: string; weeks?: number | null; basis?: string; course?: string | null; courses?: string[]; books?: string[];
  startWeek?: number | null; endWeek?: number | null; addedWeeks?: number; totalWeeks?: number;
  weeklyHours?: number; scheduleKey?: string; skillOrder?: string[];
  selection?: Record<string, {enabled: boolean; courses: string[]; books: string[]}>;
  unknownCourses?: string[]; estimatedCourses?: string[];
  courseWeeks?: number; bookWeeks?: number;
};
function courseIds(choice: SkillChoice): string[] { return choice.courses?.length ? [...new Set(choice.courses)] : choice.course ? [choice.course] : []; }
export function currentEstimates(order: string[], choices: Choices, estimates: Record<string, DurationEstimate>, weeklyHours?: number): Record<string, DurationEstimate> {
  const active = order.filter(name => choices[name]?.enabled !== false);
  const selected = order.map(name => [name, choices[name]?.enabled !== false, choices[name] ? courseIds(choices[name]) : [], [...(choices[name]?.books || [])].sort()]);
  const rows = active.map(name => estimates[name]);
  if (rows.some(row => !row || row.method !== DURATION_METHOD || !row.scheduleKey || row.scheduleKey !== rows[0]?.scheduleKey ||
    row.totalWeeks !== rows[0]?.totalWeeks || !Number.isInteger(row.totalWeeks) || (row.totalWeeks ?? -1) < 0 ||
    (weeklyHours != null && row.weeklyHours !== weeklyHours) || JSON.stringify(row.skillOrder) !== JSON.stringify(order) ||
    JSON.stringify(order.map(name => [name, row.selection?.[name]?.enabled, row.selection?.[name]?.courses, row.selection?.[name]?.books])) !== JSON.stringify(selected))) return {};
  return Object.fromEntries(active.map(name => [name, estimates[name]]));
}
export function currentWeeks(choice: SkillChoice, estimate?: DurationEstimate): number | null {
  if (!estimate || estimate.course !== choice.course || JSON.stringify([...(estimate.books || [])].sort()) !== JSON.stringify([...choice.books].sort())) return null;
  return typeof estimate.weeks === 'number' && Number.isInteger(estimate.weeks) && estimate.weeks >= 0 ? estimate.weeks : null;
}
export function totalWeeks(order: string[], choices: Choices, estimates: Record<string,DurationEstimate>, weeklyHours?: number): number | null {
  const active=order.filter(name=>choices[name]?.enabled!==false);
  if (!active.length) return order.length ? 0 : null;
  if (active.some(name => estimates[name]?.method?.startsWith('resource-hours-books/'))) {
    const current = currentEstimates(order, choices, estimates, weeklyHours);
    return active.every(name => current[name] && currentWeeks(choices[name], current[name]) !== null) ? current[active[0]].totalWeeks ?? null : null;
  }
  const weeks=active.map(name=>choices[name] ? currentWeeks(choices[name],estimates[name]) : null);
  return weeks.some(value=>value===null) ? null : weeks.reduce<number>((sum,value)=>sum+(value??0),0);
}

export function durationLabel(estimate: DurationEstimate): string {
  if (estimate.method !== DURATION_METHOD) return `예상 ${estimate.weeks}주`;
  const span = estimate.startWeek == null ? '자료 학습 0주' : estimate.startWeek === estimate.endWeek ? `${estimate.startWeek}주차` : `${estimate.startWeek}–${estimate.endWeek}주차`;
  const status = estimate.unknownCourses?.length ? ' · 시간 미확인' : estimate.estimatedCourses?.length ? ' · 추정 시간 포함' : '';
  return `${span} · 전체 일정 +${estimate.addedWeeks ?? 0}주${status}`;
}

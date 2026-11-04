/** 서버 duration_proposals와 같은 자료 일정. 기존 확정 기록에는 자동 적용하지 않는다. */
import type { MaterialResource } from '@/api/types/draft';
import type { PlanContent } from '@/api/types/plan';
import { DURATION_METHOD, type DurationEstimate, type SkillChoice } from '@/features/draft/result/skillOrder';

type Slot = {startWeek: number; endWeek: number; id: string; hours?: number | null; timeStatus?: string};
const courseIds = (choice: SkillChoice) => [...new Set(choice.courses?.length ? choice.courses : choice.course ? [choice.course] : [])];
const positive = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0;
// 시간의 부동소수점 합산이 정확한 주 경계를 한 주 늘리지 않도록 정규화한다.
const clean = (value: number) => Number(value.toPrecision(14));
const ceil = (value: number) => Math.ceil(clean(value));

export function applyMaterialSchedule(input: PlanContent): PlanContent {
  if (!Array.isArray(input.def.materialSchedule) || !input.def.learningReport) return input;
  const plan = structuredClone(input);
  const report = plan.def.learningReport!;
  const weekly = plan.hours;
  if (!positive(weekly)) throw new Error('주당 학습시간을 확인해 주세요.');
  const { choices, skillOrder: order } = report;
  plan.acts = plan.acts.filter(activity => choices[activity.skill || '']?.enabled !== false);
  const active = order.filter(name => choices[name]?.enabled !== false);
  const rows = new Map(report.recommendations.skills.map(row => [row.name, row]));
  const selection = Object.fromEntries(order.map(name => [name, {enabled: choices[name].enabled !== false, courses: courseIds(choices[name]), books: [...choices[name].books].sort()}]));
  const context = {skillOrder: order, selection, weeklyHours: weekly};
  const scheduleKey = JSON.stringify([DURATION_METHOD, report.recommendations.id, context]);
  const times = new Map<string, {hours: number; status: string; rank: number}>();
  const time = (resource: MaterialResource) => {
    const status = !positive(resource.hours) || resource.timeStatus === 'unknown' ? 'unknown' : resource.estimated?.includes('hours') || resource.timeStatus === 'estimated' ? 'estimated' : 'confirmed';
    return {hours: status === 'unknown' ? weekly : resource.hours!, status, rank: {unknown: 0, estimated: 1, confirmed: 2}[status]};
  };
  for (const name of active) {
    for (const resource of rows.get(name)?.courses || []) {
      if (!courseIds(choices[name]).includes(resource.id)) continue;
      const value = time(resource), previous = times.get(resource.id);
      if (!previous || value.rank > previous.rank || value.rank === previous.rank && value.hours > previous.hours) times.set(resource.id, value);
    }
  }
  let cursor = 0;
  const courses = new Map<string, Slot>(), books = new Map<string, Slot>();
  const estimates: Record<string, DurationEstimate> = {};
  const allocate = (hours: number, id: string): Slot => {
    const startWeek = Math.floor(clean(cursor / weekly)) + 1;
    cursor = clean(cursor + hours);
    return {id, startWeek, endWeek: ceil(cursor / weekly)};
  };
  for (const name of active) {
    const choice = choices[name], before = ceil(cursor / weekly), slots: Slot[] = [];
    for (const rid of courseIds(choice)) {
      if (!courses.has(rid)) {
        const value = times.get(rid);
        if (!value) throw new Error('선택한 강좌의 시간 근거를 확인해 주세요.');
        courses.set(rid, {...allocate(value.hours, rid), hours: value.status === 'unknown' ? null : value.hours, timeStatus: value.status});
      }
      slots.push(courses.get(rid)!);
    }
    const courseWeeks = ceil(cursor / weekly) - before;
    let bookWeeks = 0;
    for (const rid of [...choice.books].sort()) {
      if (!books.has(rid)) { books.set(rid, allocate(weekly, rid)); bookWeeks += 1; }
      slots.push(books.get(rid)!);
    }
    const startWeek = slots.length ? Math.min(...slots.map(slot => slot.startWeek)) : null;
    const endWeek = slots.length ? Math.max(...slots.map(slot => slot.endWeek)) : null;
    estimates[name] = {...context, weeks: startWeek == null || endWeek == null ? 0 : endWeek - startWeek + 1,
      startWeek, endWeek, addedWeeks: ceil(cursor / weekly) - before, courseWeeks, bookWeeks,
      method: DURATION_METHOD, scheduleKey, course: choice.course, courses: courseIds(choice), books: [...choice.books].sort(),
      unknownCourses: courseIds(choice).filter(rid => times.get(rid)?.status === 'unknown'),
      estimatedCourses: courseIds(choice).filter(rid => times.get(rid)?.status === 'estimated')};
  }
  plan.weeks = ceil(cursor / weekly);
  for (const estimate of Object.values(estimates)) estimate.totalWeeks = plan.weeks;
  report.durationEstimates = estimates;
  plan.def.materialSchedule = Object.entries(estimates).map(([skill, row]) => ({skill, weeks: row.weeks!, startWeek: row.startWeek, endWeek: row.endWeek, addedWeeks: row.addedWeeks, totalWeeks: plan.weeks}));
  const seen = new Set<string>();
  const seenBooks = new Set<string>();
  const seenOther = new Set<string>();
  let materialHours = 0, taskHours = 0, otherMaterialHours = 0;
  for (const activity of plan.acts) {
    const rid = activity.res || '', name = activity.skill || '';
    const resource = courses.get(rid);
    const book = books.get(rid);
    const slot = resource || book || estimates[name];
    if (slot) {
      activity.wFrom = slot.startWeek || Math.max(1, plan.weeks);
      activity.wTo = slot.endWeek || activity.wFrom;
    }
    if (resource || book) activity.resourceWindow = {from: slot.startWeek!, to: slot.endWeek!};
    if (resource) {
      activity.timeStatus = resource.timeStatus;
      activity.hoursEstimated = resource.timeStatus !== 'confirmed';
      activity.hours = resource.hours ?? weekly;
      if (resource.hours == null) activity.hoursBasis = '강좌 시간 미확인: 일정 계산용으로 1주 배정';
      if (seen.has(rid)) continue;
      seen.add(rid);
      materialHours += activity.hours;
    } else if (book) {
      if (activity.catalogHours === undefined) activity.catalogHours = activity.hours;
      activity.hours = weekly;
      activity.hoursAllocation = 'book-week';
      activity.hoursEstimated = true;
      activity.hoursBasis = '도서 1권당 1주 배정(주당 학습시간 기준), 실제 독서시간 아님';
      if (seenBooks.has(rid)) continue;
      seenBooks.add(rid);
      materialHours += weekly;
    } else if (!rid) {
      taskHours += positive(activity.hours) ? activity.hours : 0;
    } else if (!seenOther.has(rid)) {
      seenOther.add(rid);
      otherMaterialHours += positive(activity.hours) ? activity.hours : 0;
    }
  }
  plan.materialHours = clean(materialHours);
  plan.taskHours = clean(taskHours);
  plan.otherMaterialHours = clean(otherMaterialHours);
  plan.totalH = clean(materialHours + taskHours + otherMaterialHours);
  plan.totalHUnknown = [...courses.values()].some(row => row.timeStatus === 'unknown');
  plan.totalHEstimated = plan.acts.some(activity => activity.hoursEstimated);
  plan.durationBasis = 'materials-only';
  return plan;
}

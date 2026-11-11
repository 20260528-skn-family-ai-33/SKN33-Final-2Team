/* 결과 보고서 맨 위 개요 — 일정 줄과 스킬별 사전·사후 값. 화면과 분리한 순수 계산
   - 설문: 스킬마다 그 시점에 응답한 문항의 1~5 평균. 응답이 없는 문항은 평균에서 뺀다
   - 퀴즈: 스킬마다 채점한 문항 중 맞힌 비율. 사전·사후가 같은 개념의 다른 문제라 차이 값은 만들지 않는다
   - 일정: 계획의 주차와 보고서 시점에 고정한 완료 여부를 활동 ID로 맞춘다 */
import type { Activity, Report } from '@/api/types/plan';
import type { QuizComparison, SurveyComparison, Tally } from './comparison';

/** 레이더 축 하나(스킬). pre·post 는 0~1 로 맞춘 값이고, 값이 없으면 null(0으로 그리지 않는다) */
export interface SkillValue {
  skill: string;
  pre: number | null;
  post: number | null;
  preText: string;
  postText: string;
}

const NO_VALUE = '–';
const mean = (values: number[]): number | null => (values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null);
/** 평균은 소수 한 자리까지. 정수로 떨어지면 소수점을 붙이지 않는다 */
function scoreText(value: number | null): string {
  if (value === null) return NO_VALUE;
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function surveyBySkill(survey: SurveyComparison): SkillValue[] {
  const groups = new Map<string, { pre: number[]; post: number[] }>();
  for (const item of survey.items) {
    let group = groups.get(item.skill);
    if (!group) {
      group = { pre: [], post: [] };
      groups.set(item.skill, group);
    }
    if (item.pre !== null) group.pre.push(item.pre);
    if (item.post !== null) group.post.push(item.post);
  }
  return [...groups].map(([skill, group]) => {
    const pre = mean(group.pre);
    const post = mean(group.post);
    return { skill, pre: pre === null ? null : pre / 5, post: post === null ? null : post / 5, preText: scoreText(pre), postText: scoreText(post) };
  });
}

const ratioOf = (tally: Tally): number | null => (tally.graded ? tally.correct / tally.graded : null);
const tallyText = (tally: Tally): string => (tally.graded ? `${tally.correct}/${tally.graded}` : NO_VALUE);

export function quizBySkill(quiz: QuizComparison): SkillValue[] {
  return quiz.skills.map((skill) => ({ skill: skill.skill, pre: ratioOf(skill.pre), post: ratioOf(skill.post), preText: tallyText(skill.pre), postText: tallyText(skill.post) }));
}

/** 모든 스킬이 같은 수의 문항을 채점했으면 그 수(눈금 한 칸 = 1문항). 다르면 null → 비율 눈금을 쓴다 */
export function quizRingCount(quiz: QuizComparison): number | null {
  const counts = new Set(quiz.skills.flatMap((skill) => [skill.pre.graded, skill.post.graded]).filter((graded) => graded > 0));
  const [only] = counts;
  return counts.size === 1 && only <= 6 ? only : null;
}

export interface ScheduleRow {
  key: string;
  /** 자료 ID. 과제는 null */
  res: string | null;
  task: boolean;
  title: string;
  from: number;
  to: number;
  done: boolean;
}
export interface Schedule {
  weeks: number;
  rows: ScheduleRow[];
}

type Snapshot = NonNullable<Report['executionSnapshot']>;

/** 보고서 시점의 활동마다 계획한 주차를 붙인다. 주차를 모르는 활동이 하나라도 있으면 일부만 그리지 않고 null 을 돌려준다 */
export function buildSchedule(acts: Pick<Activity, 'id' | 'res' | 'wFrom' | 'wTo'>[], snapshot: Snapshot, planWeeks = 0): Schedule | null {
  const planned = new Map(acts.map((act) => [act.id, act]));
  const rows: ScheduleRow[] = [];
  for (const recorded of snapshot.activities) {
    const act = planned.get(recorded.id);
    if (!act || !(act.wFrom >= 1) || !(act.wTo >= act.wFrom)) return null;
    const done = recorded.status === 'done';
    // 한 강좌가 여러 스킬에 걸려 활동이 나뉘어 있으면 한 줄로 합친다(모두 완료해야 완료)
    const same = act.res ? rows.find((row) => row.res === act.res) : undefined;
    if (same) {
      same.from = Math.min(same.from, act.wFrom);
      same.to = Math.max(same.to, act.wTo);
      same.done = same.done && done;
      continue;
    }
    rows.push({ key: recorded.id, res: act.res || null, task: recorded.task, title: recorded.title, from: act.wFrom, to: act.wTo, done });
  }
  if (!rows.length) return null;
  return { weeks: Math.max(planWeeks, ...rows.map((row) => row.to)), rows };
}

/* 결과 보고서 맨 위 개요 — 일정 줄과 스킬별 사전·사후 값. 화면과 분리한 순수 계산
   - 설문: 스킬마다 사전·사후를 모두 응답한 문항의 1~5 평균. 카드 아래 높아짐·같음·낮아짐 수와 같은 문항을 쓴다
   - 퀴즈: 스킬마다 채점한 문항 중 맞힌 수. 0개여도 도형이 중심에 뭉치지 않게 눈금을 한 칸 밀어(0개 = 첫 눈금) 그린다.
     사전·사후가 같은 개념의 다른 문제라 차이 값은 만들지 않는다
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

/** 사전·사후를 모두 응답한 문항끼리 평균을 낸다(변화 수를 세는 문항과 같아야 도형과 숫자가 어긋나지 않는다).
    그런 문항이 없는 스킬은 사전 값을 만들지 않고, 사후는 응답한 문항으로만 낸다 */
export function surveyBySkill(survey: SurveyComparison): SkillValue[] {
  const groups = new Map<string, { pre: number[]; post: number[]; postOnly: number[] }>();
  for (const item of survey.items) {
    let group = groups.get(item.skill);
    if (!group) {
      group = { pre: [], post: [], postOnly: [] };
      groups.set(item.skill, group);
    }
    if (item.pre !== null && item.post !== null) {
      group.pre.push(item.pre);
      group.post.push(item.post);
    } else if (item.post !== null) group.postOnly.push(item.post);
  }
  return [...groups].map(([skill, group]) => {
    const pre = mean(group.pre);
    const post = mean(group.post.length ? group.post : group.postOnly);
    return { skill, pre: pre === null ? null : pre / 5, post: post === null ? null : post / 5, preText: scoreText(pre), postText: scoreText(post) };
  });
}

const tallyText = (tally: Tally): string => (tally.graded ? `${tally.correct}/${tally.graded}` : NO_VALUE);

/** 모든 스킬이 같은 수의 문항을 채점했으면 그 수(눈금 한 칸 = 1문항). 다르면 null → 비율 눈금을 쓴다 */
export function quizStepCount(quiz: QuizComparison): number | null {
  const counts = new Set(quiz.skills.flatMap((skill) => [skill.pre.graded, skill.post.graded]).filter((graded) => graded > 0));
  const [only] = counts;
  return counts.size === 1 && only <= 6 ? only : null;
}
/** 문항 수가 스킬마다 다를 때 쓰는 비율 눈금의 칸 수 */
const RATIO_STEPS = 3;

/** 퀴즈 레이더의 눈금 수. 0개 맞힘이 첫 눈금, 모두 맞힘이 마지막 눈금이라 칸 수보다 하나 많다 */
export function quizRingCount(quiz: QuizComparison): number {
  return (quizStepCount(quiz) ?? RATIO_STEPS) + 1;
}

/** 값은 (1 + 맞힌 칸 수) / 눈금 수: 하나도 못 맞혀도 첫 눈금에 놓여 도형이 유지된다. 글자는 실제 정답 수 그대로 */
export function quizBySkill(quiz: QuizComparison): SkillValue[] {
  const steps = quizStepCount(quiz) ?? RATIO_STEPS;
  const place = (tally: Tally): number | null => (tally.graded ? (1 + (steps * tally.correct) / tally.graded) / (steps + 1) : null);
  return quiz.skills.map((skill) => ({ skill: skill.skill, pre: place(skill.pre), post: place(skill.post), preText: tallyText(skill.pre), postText: tallyText(skill.post) }));
}

/** 보고서 근거에 나오는 스킬 수(설문·퀴즈 중 많은 쪽). 근거가 없으면 0 */
export function evidenceSkillCount(report: Pick<Report, 'surveyEvidence' | 'quizEvidence'>): number {
  const survey = new Set((report.surveyEvidence ?? []).map((row) => row.skill || row.area));
  const quiz = new Set((report.quizEvidence ?? []).map((row) => row.skill));
  return Math.max(survey.size, quiz.size);
}

export interface ScheduleRow {
  key: string;
  /** 자료 ID. 과제는 null */
  res: string | null;
  task: boolean;
  title: string;
  /** 계획한 주차 구간 [시작, 끝]. 떨어진 구간은 따로 두어 사이 주를 칠하지 않는다 */
  spans: [number, number][];
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
      same.spans = mergeSpans([...same.spans, [act.wFrom, act.wTo]]);
      same.done = same.done && done;
      continue;
    }
    rows.push({ key: recorded.id, res: act.res || null, task: recorded.task, title: recorded.title, spans: [[act.wFrom, act.wTo]], done });
  }
  if (!rows.length) return null;
  return { weeks: Math.max(planWeeks, ...rows.flatMap((row) => row.spans.map((span) => span[1]))), rows };
}

/** 겹치거나 바로 이어지는 구간만 합친다 */
function mergeSpans(spans: [number, number][]): [number, number][] {
  const merged: [number, number][] = [];
  for (const [from, to] of [...spans].sort((a, b) => a[0] - b[0])) {
    const last = merged[merged.length - 1];
    if (last && from <= last[1] + 1) last[1] = Math.max(last[1], to);
    else merged.push([from, to]);
  }
  return merged;
}

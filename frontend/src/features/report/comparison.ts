/* 결과 보고서의 사전·사후 비교 집계 (#116) — 화면과 분리한 순수 계산
   - 퀴즈: 사전·사후가 같은 개념의 다른 문제다. 개념마다 문항이 보통 1개라 정답 수는 스킬·전체 단위로 모은다
   - 설문: 같은 문항의 1~5 응답이다. 여기서는 문항별 높아짐·같음·낮아짐만 센다(스킬별 평균은 overview.ts)
   - '채점 근거 없음'·응답 없음은 0점으로 세지 않고 분모에서 뺀다 */
import type { Report } from '@/api/types/plan';

type QuizEvidence = NonNullable<Report['quizEvidence']>;
type SurveyEvidence = NonNullable<Report['surveyEvidence']>;

/** 한 문항의 채점 결과. none 은 정답 기준이 없어 채점하지 못한 문항 */
export type Mark = 'correct' | 'wrong' | 'none';
/** 채점한 문항 수(graded)와 그중 맞힌 수(correct) */
export interface Tally {
  correct: number;
  graded: number;
}
export interface QuizItem {
  concept: string;
  pre: Mark;
  post: Mark;
}
export interface ConceptRow {
  /** 측정 개념. 개념을 기록하지 않은 이전 보고서는 빈 문자열(스킬 단위) */
  concept: string;
  pre: Tally;
  post: Tally;
}
export interface SkillQuiz {
  skill: string;
  items: QuizItem[];
  concepts: ConceptRow[];
  pre: Tally;
  post: Tally;
}
export interface QuizComparison {
  skills: SkillQuiz[];
  pre: Tally;
  post: Tally;
  /** 사전이나 사후에 채점 근거가 없는 문항 수 */
  ungraded: number;
}

const markOf = (value: string): Mark => (value === '정답' ? 'correct' : value === '오답' ? 'wrong' : 'none');
const emptyTally = (): Tally => ({ correct: 0, graded: 0 });
function count(tally: Tally, mark: Mark): void {
  if (mark === 'none') return;
  tally.graded += 1;
  if (mark === 'correct') tally.correct += 1;
}

export function quizComparison(evidence: QuizEvidence): QuizComparison {
  const bySkill = new Map<string, SkillQuiz>();
  const total: QuizComparison = { skills: [], pre: emptyTally(), post: emptyTally(), ungraded: 0 };
  for (const row of evidence) {
    let skill = bySkill.get(row.skill);
    if (!skill) {
      skill = { skill: row.skill, items: [], concepts: [], pre: emptyTally(), post: emptyTally() };
      bySkill.set(row.skill, skill);
      total.skills.push(skill);
    }
    const concept = row.concept || '';
    const item: QuizItem = { concept, pre: markOf(row.pre), post: markOf(row.post) };
    skill.items.push(item);
    let conceptRow = skill.concepts.find((entry) => entry.concept === concept);
    if (!conceptRow) {
      conceptRow = { concept, pre: emptyTally(), post: emptyTally() };
      skill.concepts.push(conceptRow);
    }
    for (const tally of [conceptRow.pre, skill.pre, total.pre]) count(tally, item.pre);
    for (const tally of [conceptRow.post, skill.post, total.post]) count(tally, item.post);
    if (item.pre === 'none' || item.post === 'none') total.ungraded += 1;
  }
  return total;
}

/** 설문 1~5 응답의 선택지 문구 */
export const SURVEY_CHOICES = ['전혀 아니다', '아니다', '보통이다', '그렇다', '매우 그렇다'] as const;

export type Change = 'up' | 'same' | 'down' | 'unknown';
export interface SurveyItem {
  id: string;
  skill: string;
  text: string;
  /** 1~5. 응답이 없거나 범위를 벗어나면 null */
  pre: number | null;
  post: number | null;
  change: Change;
}
export interface SurveyComparison {
  items: SurveyItem[];
  counts: Record<Change, number>;
  /** 사전·사후 응답이 모두 있어 변화를 셀 수 있는 문항 수 */
  compared: number;
}

function ratingOf(value: string | number | null | undefined): number | null {
  const rating = Number(value);
  return Number.isInteger(rating) && rating >= 1 && rating <= 5 ? rating : null;
}

export function surveyComparison(evidence: SurveyEvidence): SurveyComparison {
  const counts: Record<Change, number> = { up: 0, same: 0, down: 0, unknown: 0 };
  const items = evidence.map((row): SurveyItem => {
    const pre = ratingOf(row.pre);
    const post = ratingOf(row.post);
    const change: Change = pre === null || post === null ? 'unknown' : post > pre ? 'up' : post < pre ? 'down' : 'same';
    counts[change] += 1;
    return { id: row.id, skill: row.skill || row.area, text: row.text, pre, post, change };
  });
  return { items, counts, compared: items.length - counts.unknown };
}

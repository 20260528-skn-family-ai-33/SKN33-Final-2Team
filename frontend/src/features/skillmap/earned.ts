/* 내 스킬 지도(누적) 계산 — 확정한 로드맵 전체와 결과 보고서에서 스킬별 뱃지를 뽑는다 (화면과 분리한 순수 계산 · 시제품)
   - 활동을 스킬로 묶는 기준은 내 로드맵 화면과 같다(groupLearningActivities). 팀 DB 스킬 이름과 같은 묶음만 지도에 올린다
   - 학습 중: 진행 중인 로드맵에 있고 아직 다 마치지 않은 스킬
   - 브론즈: 그 스킬의 활동(도서 제외)을 모두 완료로 기록한 스킬. 도서만 있는 스킬은 로드맵을 마쳤을 때
   - 실버: 결과 보고서 학습 점검의 사후 퀴즈에서 그 스킬 문항의 3분의 2 이상을 맞힌 적이 있는 스킬(3문항이면 2개)
   - 골드: 사후 퀴즈에서 그 스킬 문항을 모두 맞힌 적이 있는 스킬
   실버·골드는 활동을 다 마치지 않았어도 퀴즈 기록만으로 준다. 여러 로드맵에서 배웠으면 가장 높은 뱃지를 쓴다
   본인이 기록한 학습 이력이다. 역량 판정이 아니다 */
import type { ResourceMap, SkillMapData } from '@/api/types/catalog';
import type { PlanRecord, Report } from '@/api/types/plan';
import { groupLearningActivities, OTHER_LEARNING } from '@/features/roadmap/roadmapLearningData';
import { isBookResource, st } from '@/shared/lib/plan';

export type Medal = 'bronze' | 'silver' | 'gold';
export type SkillLevel = 'learning' | Medal;
const RANK: Record<SkillLevel, number> = { learning: 1, bronze: 2, silver: 3, gold: 4 };
export const LEVEL_TEXT: Record<SkillLevel, string> = { learning: '학습 중', bronze: '브론즈', silver: '실버', gold: '골드' };

/** 한 로드맵의 사후 퀴즈에서 그 스킬 문항을 몇 개 맞혔는지 */
export interface QuizScore {
  post: number;
  count: number;
}

export interface SkillMark {
  level: SkillLevel;
  /** 이 스킬을 배운 내 로드맵(뱃지가 높은 것부터). 개수가 학습한 횟수다 */
  plans: { id: string; title: string; level: SkillLevel; finished: boolean; quiz?: QuizScore }[];
}

export interface Earned {
  marks: Map<number, SkillMark>;
  /** 팀 DB 스킬 이름과 맞지 않아 지도에 올리지 못한 로드맵 스킬 이름 */
  unmatched: string[];
}

export const medalOf = (mark: SkillMark | undefined): Medal | undefined => (mark && mark.level !== 'learning' ? mark.level : undefined);
export const isEarned = (mark: SkillMark | undefined): boolean => !!medalOf(mark);

function quizScore(reports: Report[], planId: string, skill: string): QuizScore | undefined {
  const rows = reports.filter((report) => report.planId === planId).flatMap((report) => (report.quizEvidence || []).filter((row) => row.skill === skill));
  return rows.length ? { post: rows.filter((row) => row.post === '정답').length, count: rows.length } : undefined;
}

function quizMedal(quiz: QuizScore | undefined): Medal | undefined {
  if (!quiz) return undefined;
  if (quiz.post === quiz.count) return 'gold';
  return quiz.post * 3 >= quiz.count * 2 ? 'silver' : undefined;
}

export function earnedSkills(data: SkillMapData, records: PlanRecord[], reports: Report[], resources: ResourceMap): Earned {
  const idByName = new Map(data.skills.map((skill) => [skill.name, skill.id]));
  const marks = new Map<number, SkillMark>();
  const unmatched = new Set<string>();
  for (const record of records) {
    for (const group of groupLearningActivities(record.plan, resources)) {
      const id = idByName.get(group.name);
      if (id == null) {
        if (group.name !== OTHER_LEARNING) unmatched.add(group.name);
        continue;
      }
      const tracked = group.activities.filter((activity) => !isBookResource(activity.res ? resources[activity.res] : null));
      const finished = tracked.length ? tracked.every((activity) => st(record.progress, activity.id) === 'done') : record.status === 'done';
      const quiz = quizScore(reports, record.id, group.name);
      const level: SkillLevel | undefined = quizMedal(quiz) || (finished ? 'bronze' : record.status === 'active' ? 'learning' : undefined);
      if (!level) continue;
      const mark = marks.get(id) || { level, plans: [] };
      if (RANK[level] > RANK[mark.level]) mark.level = level;
      mark.plans.push({ id: record.id, title: record.plan.displayTitle || record.plan.goal, level, finished, quiz });
      marks.set(id, mark);
    }
  }
  marks.forEach((mark) => mark.plans.sort((a, b) => RANK[b.level] - RANK[a.level]));
  return { marks, unmatched: [...unmatched] };
}

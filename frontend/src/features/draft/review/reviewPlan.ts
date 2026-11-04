import type { ActDef, Handoff, OptionDef } from '@/api/types/draft';
import type { PlanContent } from '@/api/types/plan';
import { buildPlan, planWeeklyHours } from '@/shared/lib/plan';
import type { ReviewMaterials, ReviewResource } from './ReviewSkillBlocks';

export type ReviewActivity = ActDef & { skill: string; how: string; hours: number };
interface ReviewOption extends OptionDef { acts: ReviewActivity[] }
export type ReviewProposal = {
  id: string; key: string; skillProposalIds?: Record<string, string>; skillSummaries?: Record<string, string[]>;
  option: ReviewOption; selectedIds: string[];
};
export type ReviewPlanState = { scope: string; plan: PlanContent | null; error?: string };

/** 계산 대기·실패 중에는 확인 가능한 과제만 표시하고 자료의 원본 시간을 사용하지 않는다. */
export function reviewTaskDisplay(proposal: ReviewProposal | null, versions: ReviewProposal[], picks: Record<string, string>, start = 1): ReviewActivity[] {
  if (!proposal) return [];
  return proposal.option.acts.filter(act => !act.res).flatMap(task => {
    const id = picks[task.skill];
    const tasks = id ? versions.find(row => row.id === id && row.key === proposal.key)?.option.acts.filter(act => !act.res && act.skill === task.skill) : [task];
    return tasks?.length === 1 && tasks[0].stage >= start ? [structuredClone(tasks[0])] : [];
  });
}

/** 저장 시 compose_skill_selection → selection_option → build_plan과 같은 선택을 미리 계산한다. */
export function reviewPlan(proposal: ReviewProposal, versions: ReviewProposal[], picks: Record<string, string>,
  materials: ReviewMaterials, handoff: Pick<Handoff, 'startStage'> & { prefs: Pick<Handoff['prefs'], 'weeklyHours' | 'formatKey'> }, goal: string) {
  if (!materials.recommendations) throw new Error('검토할 자료를 불러오는 중이에요.');
  const acts = structuredClone(proposal.option.acts);
  for (const [skill, id] of Object.entries(picks)) {
    const source = versions.find(row => row.id === id && row.key === proposal.key);
    const tasks = source?.option.acts.filter(act => !act.res && act.skill === skill) || [];
    const index = acts.findIndex(act => !act.res && act.skill === skill);
    if (index < 0 || tasks.length !== 1) throw new Error('선택한 과제를 다시 확인해 주세요.');
    acts[index] = structuredClone(tasks[0]);
  }
  const selected = new Set(proposal.selectedIds);
  if (selected.size !== proposal.selectedIds.length || [...selected].some(id => !acts.some(act => act.id === id))) {
    throw new Error('선택한 활동이 현재 제안과 일치하지 않아요. 다시 불러와 주세요.');
  }
  const names = materials.skillOrder || materials.recommendations.skills.map(row => row.name);
  const resources = new Map<string, ReviewResource & { type: string }>();
  const recommendations = { skills: materials.recommendations.skills.map(row => {
    const choice = materials.choices[row.name];
    if (!choice) throw new Error('자료 선택 정보를 다시 확인해 주세요.');
    const courses = row.courses.filter(item => item.id === choice.course || choice.courses?.includes(item.id));
    const books = row.books.filter(item => choice.books.includes(item.id));
    courses.forEach(item => resources.set(item.id, { ...item, type: 'course' }));
    books.forEach(item => resources.set(item.id, { ...item, type: 'book' }));
    return { name: row.name, courses, books };
  }) };
  if (acts.some(act => act.res && !resources.has(act.res))) throw new Error('제안의 자료가 현재 선택과 달라요. 다시 불러와 주세요.');
  const def: OptionDef = { ...proposal.option, acts, materialSchedule: [], learningReport: {
    recommendations, choices: materials.choices, skillOrder: names, skillDetails: materials.skillDetails,
  } };
  const params = { start: handoff.startStage, hours: planWeeklyHours(handoff.prefs.weeklyHours, def.weeklyHours),
    format: handoff.prefs.formatKey };
  const lookup = (id: string | null | undefined) => id ? resources.get(id) || null : null;
  // 해제한 과제도 다시 고를 수 있게 카드에는 남기고 합계에는 선택한 활동만 넣는다.
  const display = buildPlan(def, params, goal, lookup);
  const plan = buildPlan({ ...def, acts: acts.filter(act => selected.has(act.id)) }, params, goal, lookup);
  return { plan, acts: display.acts.map(act => ({ ...act, skill: act.skill || '', how: act.how || '' })) };
}

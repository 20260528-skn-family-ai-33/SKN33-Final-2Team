import type { LearningSkill } from '@/api/types/draft';

export type CrashCoreRow = { name: string; outcome: string; criteria: string[] };
export type CrashCore = { rows: CrashCoreRow[]; followUp: string[] };

/** Crash 안의 최소 기능판 핵심 결과물·완료 기준과 후속 학습 범위. 기준이 없는 이전 안은 표시하지 않는다. */
export function crashCore(skills: LearningSkill[] | undefined): CrashCore | null {
  const rows: CrashCoreRow[] = [];
  for (const skill of skills || []) {
    const outcome = skill.coreOutcome?.trim();
    const criteria = (skill.coreCriteria || []).map(value => value.trim()).filter(Boolean);
    if (outcome && criteria.length) rows.push({ name: skill.name, outcome, criteria });
  }
  if (!rows.length) return null;
  const followUp = Array.from(new Set((skills || []).flatMap(skill => skill.followUpScope || [])
    .map(value => value.trim()).filter(Boolean)));
  return { rows, followUp };
}

export const crashCoreExpandable = (core: CrashCore | null) =>
  !!core && (
    core.rows.length > 2
    || core.followUp.length > 2
    || core.rows.some(row => row.criteria.length > 0 || row.outcome.length > 32)
    || core.followUp.some(value => value.length > 32)
  );

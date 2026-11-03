/** 한 스킬 재제안 시 다른 스킬에서 사용자가 제외한 과제를 다시 선택하지 않는다. */
export function preserveOtherSkillSelections(previousIds: string[], nextActs: { id: string; skill: string }[], proposedIds: string[], changedSkill: string) {
  const previous = new Set(previousIds), proposed = new Set(proposedIds);
  return nextActs.filter(act => (act.skill === changedSkill ? proposed : previous).has(act.id)).map(act => act.id);
}

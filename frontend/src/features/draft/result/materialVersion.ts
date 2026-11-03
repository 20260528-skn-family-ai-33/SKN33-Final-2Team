import type { OptionDef } from '@/api/types/draft';
/** Support results do not create a new roadmap/material version. */
export function materialVersionKey(option?: OptionDef): string {
  if (!option) return '';
  if (option.optionId) return JSON.stringify([option.optionId,option.learningSkillsVersion]);
  return JSON.stringify([option.id,option.name,option.scope,option.reason,option.tagline,option.acts,option.weeklyHours,
    option.learningSkills,option.learningSkillsVersion]);
}

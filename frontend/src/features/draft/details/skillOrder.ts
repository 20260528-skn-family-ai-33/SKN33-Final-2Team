import type { SelectedSkill } from '@/api/types/draft';
/** 학습할 스킬 상한. 서버 검사(track_policy.MAX_SKILLS)와 같은 값이다. */
export const MAX_SKILLS=3;
export const canIncludeSkill=(rows:SelectedSkill[])=>rows.length<MAX_SKILLS;
export const overSkillLimit=(rows:SelectedSkill[])=>Math.max(0,rows.length-MAX_SKILLS);
export function reorderSkills(rows: SelectedSkill[], source: string, target: string): SelectedSkill[] {
  const from=rows.findIndex(row=>row.name===source),to=rows.findIndex(row=>row.name===target);
  if(from<0||to<0||from===to)return rows;
  const next=[...rows];next.splice(to,0,next.splice(from,1)[0]);return next;
}

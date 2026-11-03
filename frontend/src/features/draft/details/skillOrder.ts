import type { SelectedSkill } from '@/api/types/draft';
export function reorderSkills(rows: SelectedSkill[], source: string, target: string): SelectedSkill[] {
  const from=rows.findIndex(row=>row.name===source),to=rows.findIndex(row=>row.name===target);
  if(from<0||to<0||from===to)return rows;
  const next=[...rows];next.splice(to,0,next.splice(from,1)[0]);return next;
}

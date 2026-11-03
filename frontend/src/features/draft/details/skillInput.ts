import type { DraftDoc } from '@/api/types/draft';
import { sortKeys } from '@/shared/lib/format';
/** Learning conditions affect the roadmap, not the chosen skills. */
export const skillInputKey=(draft: DraftDoc)=>JSON.stringify(sortKeys([draft.goal,draft.project,draft.doc?.status==='ok'?draft.doc.summary:null]));
export function skillsReady(draft:DraftDoc):boolean {
  if(!draft.selectedSkills?.length||!draft.skillInputKey)return false;
  if(draft.skillInputKey===skillInputKey(draft))return true;
  // Keep selections saved before learning conditions were separated from skills.
  try{
    const previous=JSON.parse(draft.skillInputKey);
    return Array.isArray(previous)&&previous.length===4&&JSON.stringify(sortKeys([previous[0],previous[1],previous[3]]))===skillInputKey(draft);
  }catch{return false;}
}

/** Visiting details must not replace an existing assessment/roadmap with a new skill flow. */
export const hasExistingSkillProgress=(draft:DraftDoc)=>!!(draft.v2Assessment||draft.quiz||draft.handoff||draft.gen||draft.genRun||draft.diag);
export const canContinueSkills=(draft:DraftDoc)=>skillsReady(draft)||hasExistingSkillProgress(draft);
export const shouldRecommendSkills=(draft:DraftDoc,explicit=false)=>explicit||(!skillsReady(draft)&&!hasExistingSkillProgress(draft));

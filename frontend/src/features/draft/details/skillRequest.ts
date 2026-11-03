import { waitJob } from '@/api/jobs';
import type { DraftDoc, SelectedSkill } from '@/api/types/draft';
import { ws } from '@/shared/state/workspace';
import { ensureDraft, flush } from '../draftSync';
import { skillInputKey } from './skillInput';
const flights=new Map<string,Promise<SelectedSkill[]>>();
export function summaryStage(draft: DraftDoc): 'ready'|'reading'|'missing' {
  if (!draft.project) return 'ready';
  if (draft.doc?.status==='reading') return 'reading';
  return draft.doc?.status==='ok' && !!draft.doc.summary?.trim() ? 'ready' : 'missing';
}
export async function loadSkills(owner: string|null, signature: string): Promise<SelectedSkill[]> {
  const current=()=>ws().owner===owner && skillInputKey(ws().draft)===signature;
  await flush(); if(!current())throw new Error('입력이 변경됐어요.');
  const id=await ensureDraft(); if(!current())throw new Error('입력이 변경됐어요.');
  const key=JSON.stringify([owner,id,signature]); const pending=flights.get(key); if(pending)return pending;
  const work=(async()=>{
    const response=await fetch(`/api/v2/drafts/${id}/skills`,{method:'POST',credentials:'same-origin',headers:{Prefer:'respond-async'}});
    let body=await response.json().catch(()=>null);
    if(!response.ok)throw new Error(body?.error?.message || (response.status===404?'현재 백엔드에 스킬 추천 API가 반영되지 않았어요. 백엔드 업데이트가 필요합니다.':`스킬 추천 요청에 실패했어요(HTTP ${response.status}).`));
    if(response.status===202)body=await waitJob<{skills:SelectedSkill[]}>(body.jobId);
    if(!Array.isArray(body?.skills)||!body.skills.length||body.skills.some((row:SelectedSkill)=>!row.name||!row.application))throw new Error('추천된 스킬을 확인하지 못했어요. 다시 제안받아 주세요.');
    return body.skills as SelectedSkill[];
  })();
  flights.set(key,work);void work.finally(()=>{if(flights.get(key)===work)flights.delete(key);}).catch(()=>{});return work;
}

import { draftsApi } from '@/api/endpoints/drafts';
import { ws } from '@/shared/state/workspace';
import { ensureDraft, flush, takeDraft } from './draftSync';
import { inputSignature } from './invalidation';
const flights = new Map<string, Promise<void>>();
const failures = new Map<string, unknown>();
export function prepareRoadmaps(): Promise<void> {
  const before=ws();
  if(before.draft.gen || Object.values(before.draft.genRun?.rows||{}).some(row=>row?.st==='run'))return Promise.resolve();
  const key=JSON.stringify([before.owner,before.draftId,inputSignature(before.draft),before.draft.v2Assessment?.generationId]);
  if(failures.has(key))return Promise.reject(failures.get(key));
  const pending=flights.get(key); if(pending)return pending;
  const work=(async()=>{
    await flush(); const id=await ensureDraft();
    const owner=ws().owner, signature=inputSignature(ws().draft), generation=ws().draft.v2Assessment?.generationId;
    if(!ws().draft.v2Assessment?.completed)throw new Error('역량 테스트를 먼저 완료해 주세요.');
    const result=await draftsApi.optionsStart(id);
    if(ws().owner===owner && ws().draftId===id && inputSignature(ws().draft)===signature && ws().draft.v2Assessment?.generationId===generation)takeDraft(result);
  })().catch(error=>{failures.set(key,error);throw error;});
  flights.set(key,work); void work.finally(()=>{if(flights.get(key)===work)flights.delete(key);}).catch(()=>{});return work;
}

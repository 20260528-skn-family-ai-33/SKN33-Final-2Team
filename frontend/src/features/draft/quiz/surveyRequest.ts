import { waitJob } from '@/api/jobs';
import { ensureDraft } from '../draftSync';
import type { Answers, Survey } from './assessment/flow';
export type Stored = Survey & { answers: Answers; completed: boolean };
const flights = new Map<string, Promise<Stored>>();
export class SurveyRequestError extends Error {
  constructor(message: string, readonly code: string) { super(message); }
}
export async function request(path: string, init?: RequestInit): Promise<Stored | null> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(init?.method === 'POST' ? { Prefer: 'respond-async' } : {}), ...init?.headers } });
  let body = await response.json().catch(() => null);
  if (response.status === 202 && body?.jobId) {
    const job = waitJob<{ survey: Stored }>(body.jobId);
    void job.catch(() => {});
    let stopped = false;
    const partial = (async () => {
      while (!stopped) {
        await new Promise(resolve => setTimeout(resolve, 800));
        if (stopped) break;
        try { const value = await request(path); if (value && value.quizStatus !== 'failed' && value.quizStatus !== 'interrupted') return { survey: value }; } catch { /* 작업 결과에서 오류 확인 */ }
      }
      return await job;
    })();
    try { body = await Promise.race([job, partial]); } finally { stopped = true; }
  }
  if (!response.ok) throw new SurveyRequestError(body?.error?.message ?? '설문 요청을 처리하지 못했어요.', body?.error?.code ?? 'REQUEST_FAILED');
  if (!body || typeof body !== 'object') throw new SurveyRequestError('설문 응답을 확인하지 못했어요. 다시 시도해 주세요.', 'EMPTY_RESPONSE');
  return body.survey ?? null;
}
export async function loadSurvey(owner: string): Promise<Stored> {
  const id=await ensureDraft();
  const key=`${owner}:${id}`;
  const pending=flights.get(key);if(pending)return pending;
  const work=(async()=>{
    const path=`/api/v2/drafts/${id}/survey`;
    const existing=await request(path);
    if (existing && (existing.quizStatus === 'failed' || existing.quizStatus === 'interrupted') && existing.groups?.some(g => g.surveys?.length)) {
      void request(path, { method: 'POST' }).catch(() => {});
      return { ...existing, quizStatus: 'pending' as const };
    }
    const result=(existing?.quizStatus==='failed'||existing?.quizStatus==='interrupted')?await request(path,{method:'POST'}):existing??await request(path,{method:'POST'});
    if(!result)throw new Error('설문을 불러오지 못했어요.');
    return result;
  })();
  flights.set(key,work);void work.finally(()=>{if(flights.get(key)===work)flights.delete(key);}).catch(()=>{});return work;
}
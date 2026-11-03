import { waitJob } from '@/api/jobs';
/** 검토 화면의 빈 응답·프록시 오류를 JSON 파싱 오류와 구분한다. POST 자동 재시도는 하지 않는다. */
export async function reviewRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(init?.method === 'POST' ? { Prefer: 'respond-async' } : {}), ...init?.headers } });
  const text = await response.text();
  let body: unknown;
  try { body = text.trim() ? JSON.parse(text) : null; }
  catch { throw new Error(`서버 응답을 확인하지 못했어요(HTTP ${response.status}). 잠시 후 다시 불러와 주세요.`); }
  const message = body && typeof body === 'object' && 'error' in body ? (body as { error?: { message?: string } }).error?.message : undefined;
  if (!response.ok) throw new Error(message || `서버 연결을 확인하지 못했어요(HTTP ${response.status}). 잠시 후 다시 불러와 주세요.`);
  if (!body || typeof body !== 'object') throw new Error('서버 응답이 비어 있거나 형식이 올바르지 않아요. 잠시 후 다시 불러와 주세요.');
  if (response.status === 202 && 'jobId' in body && typeof body.jobId === 'string') return waitJob<T>(body.jobId, { signal: init?.signal || undefined });
  return body as T;
}

/* 오래 걸리는 작업(202 → jobId)을 끝날 때까지 기다린다.
   서버가 GET /jobs/{id}?wait=10 을 최대 10초 붙잡았다가 응답하므로 따로 쉬지 않고 다시 묻는다.
   실패면 ApiError, 사용자가 멈췄으면 AbortError 를 던진다 */
import { ApiError, enc, http } from './client';
import type { JobView } from './types/common';

export interface WaitOptions {
  signal?: AbortSignal;
  onProgress?: (v: JobView) => void;
}

export function abortError(message = '사용자가 멈췄어요'): DOMException {
  return new DOMException(message, 'AbortError');
}

export const isAbort = (e: unknown): boolean => e instanceof DOMException && e.name === 'AbortError';

export async function waitJob<T = Record<string, unknown>>(id: string, opts: WaitOptions = {}): Promise<T> {
  for (;;) {
    const v = await http.get<JobView>(`/jobs/${enc(id)}?wait=10`, { signal: opts.signal });
    opts.onProgress?.(v);
    if (v.status === 'running' || v.status === 'queued') continue;
    if (v.status === 'done') return (v.result || {}) as T;
    if (v.status === 'cancelled') throw abortError();
    const e = v.error || {};
    throw new ApiError(502, { code: e.code, kind: e.kind, message: e.user, cause: e.text, hint: e.hint, raw: e.raw, retryable: e.retryable });
  }
}

export const getJob = (id: string) => http.get<JobView>(`/jobs/${enc(id)}`);
export const cancelJob = (id: string) => http.post<{ status: string }>(`/jobs/${enc(id)}/cancel`, {});

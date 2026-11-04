/* 서버 요청 공통 (설계서 v1.7 /api/v1)
   화면 컴포넌트는 fetch 를 직접 쓰지 않고 endpoints/ 의 함수만 쓴다. 백엔드를 바꿀 때 고칠 곳을 이 폴더로 모으기 위해서다.
   - 오류는 서버 형식 {error: {code, message, hint, retryable, kind, cause, raw}} 를 ApiError 로 바꿔 던진다
   - 오래 걸리는 작업은 'Prefer: respond-async' 로 보내 202 {jobId} 를 받는다(jobs.ts 의 waitJob 으로 끝날 때까지 기다림) */
import type { ApiErrorPayload } from './types/common';

export const API_BASE = '/api/v1';

export class ApiError extends Error {
  readonly status: number;
  readonly payload: ApiErrorPayload;

  constructor(status: number, payload: ApiErrorPayload | null | undefined) {
    const p = payload || {};
    super(p.raw || p.message || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.payload = p;
  }

  get code(): string | undefined {
    return this.payload.code;
  }
}

export interface RequestOptions {
  /** 'Prefer: respond-async' — 오래 걸리는 작업은 202 {jobId} 로 바로 돌려받는다 */
  async?: boolean;
  signal?: AbortSignal;
}

type Body = FormData | object | undefined;

export async function request<T>(method: string, path: string, body?: Body, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  let data: BodyInit | undefined;
  if (body instanceof FormData) data = body;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    data = JSON.stringify(body);
  }
  if (opts.async) headers.Prefer = 'respond-async';
  let r: Response;
  try {
    r = await fetch(API_BASE + path, { method, headers, body: data, credentials: 'same-origin', cache: 'no-store', signal: opts.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new ApiError(0, {
      code: 'SERVER',
      kind: 'server',
      message: 'AI 서버에 연결하지 못했어요',
      cause: '서버에 연결하지 못했어요',
      hint: '백엔드가 켜져 있는지 확인해 주세요(docker compose ps)',
      raw: String((e as Error)?.message || e),
      retryable: true,
    });
  }
  if (r.status === 204) return null as T;
  let j: unknown = null;
  try {
    j = await r.json();
  } catch {
    /* 본문 없음 */
  }
  if (!r.ok) {
    const err = (j as { error?: ApiErrorPayload } | null)?.error;
    throw new ApiError(r.status, err || { code: 'HTTP_' + r.status, kind: 'other', message: '요청을 처리하지 못했어요', raw: `HTTP ${r.status}` });
  }
  return j as T;
}

export const http = {
  get: <T>(p: string, o?: RequestOptions) => request<T>('GET', p, undefined, o),
  post: <T>(p: string, b: Body = {}, o?: RequestOptions) => request<T>('POST', p, b, o),
  put: <T>(p: string, b?: Body, o?: RequestOptions) => request<T>('PUT', p, b, o),
  patch: <T>(p: string, b?: Body, o?: RequestOptions) => request<T>('PATCH', p, b, o),
  del: <T>(p: string, o?: RequestOptions) => request<T>('DELETE', p, undefined, o),
};

export const enc = encodeURIComponent;

/** 파일 하나를 multipart 로 보낸다 */
export function fileForm(file: File, extra?: Record<string, string>): FormData {
  const f = new FormData();
  f.append('file', file, file.name);
  Object.entries(extra || {}).forEach(([k, v]) => {
    if (v) f.append(k, v);
  });
  return f;
}

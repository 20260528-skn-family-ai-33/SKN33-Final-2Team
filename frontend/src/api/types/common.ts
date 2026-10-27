/* 여러 API 가 함께 쓰는 형식 */

/** 서버 오류 본문 {error: …} — 사용자용 문구(message)와 운영자용 원인·조치·원문을 함께 보낸다 */
export interface ApiErrorPayload {
  code?: string;
  message?: string;
  hint?: string;
  retryable?: boolean;
  kind?: string;
  cause?: string;
  raw?: string;
}

/** 서버가 작업·기록에 저장해 두는 원인 객체(errors.cause) */
export interface StoredCause {
  kind?: string;
  text?: string;
  hint?: string;
  raw?: string;
  user?: string;
  code?: string;
  retryable?: boolean;
  stopped?: boolean;
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export interface JobView {
  jobId: string;
  kind: string;
  status: JobStatus;
  progress: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: StoredCause | null;
}

/** 202 응답 */
export interface JobStarted {
  jobId: string;
  status: 'running';
}

export interface Ok {
  ok: boolean;
}

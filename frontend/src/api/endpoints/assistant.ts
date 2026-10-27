/* 사내 생활 도우미 (API-09) — 작업(202 jobId)으로 돌고, 멈추면 작업을 취소한다.
   응답 모양은 backend/app/agents/regulation.py 의 ans() 기준 */
import { http } from '../client';
import type { RegBundle } from '../types/catalog';
import type { JobStarted } from '../types/common';

export type AnswerKind = 'regulation' | 'general' | 'clarify' | 'out';
/** regulation: ok·missing·unclear·none·scope · general: general · clarify · out */
export type AnswerLevel = 'ok' | 'missing' | 'unclear' | 'none' | 'scope' | 'general' | 'clarify' | 'out';

export interface AssistantAnswer {
  kind: AnswerKind;
  level: AnswerLevel;
  /** general 일 때 intranet(사내 홈페이지 안내)·work(업무·학습)·app(사용법) */
  source?: string;
  summary: string;
  apply: string;
  more: string[];
  /** 근거 조항 id */
  basis: string[];
  /** 적용 대상 아님(scope)일 때 참고로 찾은 조항 id */
  ref?: string[];
  missing: string[];
  /** 사내 홈페이지(가상) 메뉴 id (shared/constants/data.ts 의 D.intranet) */
  intranet: string[];
  question: string;
  options: string[];
  /** 앱 사용법 바로 가기 [5차 화면 ID, 이름] — 서버가 예전 화면 ID 로 준다 */
  links?: [string, string][];
  retrieved?: string[];
  dropped?: boolean;
}

export interface AssistantResult {
  answer: AssistantAnswer;
  reg: RegBundle;
  meta?: { ms?: number; loadMs?: number; [k: string]: unknown };
}

/** 앞 대화: 답을 받은 질문과 답(요약본)만 넘긴다 */
export interface HistoryTurn {
  q: string;
  a: Pick<AssistantAnswer, 'kind' | 'level' | 'source' | 'summary' | 'apply' | 'more' | 'basis' | 'missing' | 'intranet' | 'question' | 'options'>;
}

export const assistantApi = {
  ask: (question: string, history: HistoryTurn[], signal?: AbortSignal) => http.post<JobStarted>('/assistant/ask', { question, history }, { async: true, signal }),
};

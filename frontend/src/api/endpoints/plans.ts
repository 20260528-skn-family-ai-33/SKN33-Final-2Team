/* 내 로드맵·진행·수정안·코멘트·사후 점검·보고서 (API-36~52) */
import { enc, fileForm, http } from '../client';
import type { JobStarted } from '../types/common';
import type { PlanResponse, Report } from '../types/plan';

const a = { async: true } as const;

export const plansApi = {
  get: (id: string) => http.get<PlanResponse>(`/plans/${enc(id)}`),
  progress: (id: string, act: string, body: Record<string, unknown>) => http.put<PlanResponse>(`/plans/${enc(id)}/activities/${enc(act)}/progress`, body),
  attach: (id: string, act: string, file: File) =>
    http.post<{ fileId: string; name: string; size: number }>(`/plans/${enc(id)}/activities/${enc(act)}/attachments`, fileForm(file)),
  archive: (id: string) => http.post<PlanResponse>(`/plans/${enc(id)}/archive`),
  resume: (id: string) => http.post<PlanResponse>(`/plans/${enc(id)}/resume`),
  revise: (id: string, body: Record<string, unknown>) => http.post<JobStarted>(`/plans/${enc(id)}/revisions`, body, a),
  reviseSupportRetry: (id: string) => http.post<JobStarted>(`/plans/${enc(id)}/revisions/support/retry`, {}, a),
  acceptRevision: (rid: string) => http.post<PlanResponse>(`/revisions/${enc(rid)}/accept`),
  dropRevision: (rid: string) => http.del<null>(`/revisions/${enc(rid)}`),
  commentRead: (id: string, cid: string) => http.post<PlanResponse>(`/plans/${enc(id)}/comments/${enc(cid)}/read`),
  savePost: (id: string, body: Record<string, unknown>) => http.put<PlanResponse>(`/plans/${enc(id)}/post-assessment`, body),
  makeReport: (id: string) => http.post<JobStarted>(`/plans/${enc(id)}/reports`, {}, a),
  /** 설계서 밖 추가(10/23) · 사후 심화 질문 만들기 */
  postDeep: (id: string) => http.post<JobStarted>(`/plans/${enc(id)}/post-assessment/deep`, {}, a),
  reports: (planId?: string) => http.get<Report[]>(`/reports${planId ? `?planId=${enc(planId)}` : ''}`),
  confirmReport: (rid: string) => http.post<{ planStatus: string; planId: string }>(`/reports/${enc(rid)}/confirm`),
};

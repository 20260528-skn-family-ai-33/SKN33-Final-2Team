/* 새 로드맵 작성 (API-14~35) — 오래 걸리는 작업(문항·진단·기획서 요약)은 202 {jobId} 로 바로 돌려받고, 화면은 작성 문서를 다시 읽어 진행을 본다 */
import { enc, fileForm, http } from '../client';
import type { JobStarted } from '../types/common';
import type { DraftResponse, RegenRequest } from '../types/draft';

const a = { async: true } as const;

export const draftsApi = {
  current: () => http.get<DraftResponse>('/drafts/current'),
  create: (body: { draft: Record<string, unknown>; lastNew: string | null }) => http.post<DraftResponse>('/drafts', body),
  patch: (id: string, body: Record<string, unknown>) => http.patch<DraftResponse>(`/drafts/${enc(id)}`, body),
  remove: (id: string) => http.del<null>(`/drafts/${enc(id)}`),
  get: (id: string) => http.get<DraftResponse>(`/drafts/${enc(id)}/options`),
  changesApply: (id: string, kind: string) => http.post<DraftResponse>(`/drafts/${enc(id)}/changes/apply`, { kind }),
  changesRevert: (id: string, kind: string) => http.post<DraftResponse>(`/drafts/${enc(id)}/changes/revert`, { kind }),
  projectFile: (id: string, file: File) => http.post<DraftResponse>(`/drafts/${enc(id)}/project-file`, fileForm(file)),
  projectClear: (id: string) => http.del<DraftResponse>(`/drafts/${enc(id)}/project-file`),
  projectSummary: (id: string, skipImages: boolean) => http.post<JobStarted & Partial<DraftResponse>>(`/drafts/${enc(id)}/project-file/summary`, { skipImages }, a),
  assessment: (id: string) => http.post<JobStarted & Partial<DraftResponse>>(`/drafts/${enc(id)}/assessment`, {}, a),
  diagnosis: (id: string) => http.post<JobStarted & Partial<DraftResponse>>(`/drafts/${enc(id)}/diagnosis`, {}, a),
  overrides: (id: string, body: Record<string, unknown>) => http.put<DraftResponse>(`/drafts/${enc(id)}/diagnosis/overrides`, body),
  optionsStart: (id: string) => http.post<DraftResponse>(`/drafts/${enc(id)}/options`),
  optionRetry: (id: string, pid: string) => http.post<DraftResponse>(`/drafts/${enc(id)}/options/${enc(pid)}/retry`),
  acceptPartial: (id: string) => http.post<DraftResponse>(`/drafts/${enc(id)}/options/accept-partial`),
  /** request 가 null 이면 바라는 점 없이 다시 만든다 */
  regenerate: (id: string, pid: string, request: RegenRequest | null) => http.post<DraftResponse>(`/drafts/${enc(id)}/options/${enc(pid)}/regenerate`, { request }),
  /** perspective 가 null 이면 세 안 모두 다시 확인 */
  supportRetry: (id: string, perspective: string | null) => http.post<DraftResponse>(`/drafts/${enc(id)}/options/support/retry`, { perspective }),
  select: (id: string, perspective: string) => http.post<DraftResponse>(`/drafts/${enc(id)}/selection`, { perspective }),
  confirm: (id: string) => http.post<{ planId: string }>(`/drafts/${enc(id)}/confirm`),
};

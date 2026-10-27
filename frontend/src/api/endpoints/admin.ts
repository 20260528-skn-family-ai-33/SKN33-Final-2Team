/* 관리자 화면 API (관리자 전용 계정) — 인적·교육: 한 건은 확인(token) → 저장, 여러 건은 파일 미리보기 → 반영
   · 규정: 고치지 않고 원문 PDF 올리기·내려받기만 */
import { API_BASE, enc, fileForm, http } from '../client';
import type {
  AdminOverview,
  AdminRows,
  EditCheck,
  EditRow,
  EditSaved,
  GoalEmployee,
  GoalMode,
  RegulationDoc,
  RegulationUpload,
  UploadSummary,
  UploadView,
} from '../types/admin';

const qs = (o: Record<string, string | number>) => new URLSearchParams(Object.entries(o).map(([k, v]) => [k, String(v)])).toString();

export const adminApi = {
  overview: () => http.get<AdminOverview>('/admin/overview'),
  rows: (ds: string, sheet: string, q: { q?: string; limit?: number; offset?: number } = {}) =>
    http.get<AdminRows>(`/admin/datasets/${enc(ds)}/rows?${qs({ sheet, ...q })}`),
  /** save 가 없으면 확인만(바뀌는 칸·오류·token), save 면 확인 때 받은 token 으로 저장 */
  check: (ds: string, rows: EditRow[]) => http.post<EditCheck>(`/admin/datasets/${enc(ds)}/edit`, { rows }),
  save: (ds: string, rows: EditRow[], token: string, goalMode: 'mock' | null) =>
    http.post<EditSaved>(`/admin/datasets/${enc(ds)}/edit`, { rows, save: true, token, goalMode }),
  preview: (ds: string, file: File, sheet: string) => http.post<UploadView>(`/admin/datasets/${enc(ds)}/preview`, fileForm(file, { sheet })),
  upload: (uploadId: string) => http.get<UploadView>(`/admin/uploads/${enc(uploadId)}`),
  apply: (uploadId: string, goalMode: 'mock' | null) =>
    http.post<{ uploadId: string; dataset: string; applied: UploadView['applied']; goalCount: number }>(`/admin/uploads/${enc(uploadId)}/apply`, { goalMode }),
  discard: (uploadId: string) => http.del<null>(`/admin/uploads/${enc(uploadId)}`),
  uploads: (ds = '') => http.get<UploadSummary[]>(`/admin/uploads?dataset=${enc(ds)}`),
  goalEmployees: () => http.get<GoalEmployee[]>('/admin/goal-suggestions/employees'),
  /** employeeIds 가 있으면 그 직원만, 없으면 재직 직원 모두 */
  goalsAll: (mode: GoalMode, employeeIds?: number[]) =>
    http.post<{ employees: number; started: number; defaults: number; mode: string }>('/admin/goal-suggestions/regenerate-all', employeeIds ? { mode, employeeIds } : { mode }),
  /** 지금 규정(도우미가 쓰는 버전)과 원문 PDF 가 서버에 있는지 */
  regulations: () => http.get<RegulationDoc[]>('/admin/regulations'),
  regulationUploads: () => http.get<RegulationUpload[]>('/admin/regulations/uploads'),
  /** 새 규정 PDF 올리기(메모는 선택) — 시스템 관리자가 내려받아 도우미 검색에 반영한다 */
  uploadRegulation: (file: File, memo: string) => http.post<RegulationUpload>('/admin/regulations/uploads', fileForm(file, { memo })),
  /** 잘못 올린 PDF 지우기(서버 파일과 기록을 함께 · 되돌릴 수 없음) */
  deleteRegulationUpload: (uploadId: string) => http.del<null>(`/admin/regulations/uploads/${enc(uploadId)}`),
  /** 파일 내려받기는 링크로 연다(쿠키로 인증) */
  regulationPdfUrl: (regulationId: string) => `${API_BASE}/admin/regulations/${enc(regulationId)}/pdf`,
  regulationUploadPdfUrl: (uploadId: string) => `${API_BASE}/admin/regulations/uploads/${enc(uploadId)}/pdf`,
  downloadUrl: (ds: string, fmt: 'xlsx' | 'csv', sheet = '') => `${API_BASE}/admin/datasets/${enc(ds)}/export?${qs({ format: fmt, sheet })}`,
  templateUrl: (ds: string, fmt: 'xlsx' | 'csv', sheet = '') => `${API_BASE}/admin/datasets/${enc(ds)}/template?${qs({ format: fmt, sheet })}`,
};

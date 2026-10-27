/* 관리자 화면 (설계서 밖 추가 · 10/21) — 응답 모양은 backend/app/routers/admin.py · app/admin_io/__init__.py 기준 */

/** 화면에서 고치는 데이터. 규정은 고치지 않고 원문 PDF 만 올리고 내려받는다(2026-10-26 · RegulationDoc·RegulationUpload) */
export type DatasetId = 'hr' | 'education';
export type RowAction = 'add' | 'update' | 'delete' | 'error' | 'skip' | 'same';
export type UploadStatus = 'previewed' | 'applied' | 'rejected' | 'expired';

/** 목표 후보 다시 만들기 모델: 가데이터 · 관리자가 고른 모델 · null 이면 각 직원이 고른 AI 모드 */
export type GoalMode = 'mock' | 'ollama' | 'openai' | null;

/** 목표 후보를 다시 만들 직원 고르기 목록(재직 직원 · 지금 후보 상태와 만든 모드) */
export interface GoalEmployee {
  id: number;
  name: string;
  no: string;
  dept: string;
  grade: string;
  /** ready · default · running · failed · '' */
  status: string;
  /** mock · ollama · openai · default · '' */
  source: string;
  at: string;
}

export interface AdminOverview {
  hr: {
    active: number;
    retired: number;
    heads: number;
    noNumber: number;
    departments: number;
    evaluations: number;
    transfers: { at: string; name: string; from: string | null; to: string | null; headBefore: boolean; headAfter: boolean }[];
  };
  /** 지금 규정 수 · 원문 PDF 가 서버에 있는 규정 수 · 관리자가 올린 PDF 수와 마지막으로 올린 때 */
  regulations: { count: number; files: number; uploads: number; lastUpload: string | null };
  providers: Record<'ollama' | 'openai', { available: boolean }>;
  education:Partial<Record<'course' | 'book' | 'cert', { count: number; estimated: number }>>;
  /** 목표 후보 작업 상태별 개수 (ready·default·running·failed) */
  goals: Record<string, number>;
  uploads: UploadSummary[];
}

/** 고르기 목록: strict 면 목록 밖 값을 쓸 수 없다(고르기), 아니면 추천만 */
export interface ColumnOptions {
  strict?: boolean;
  items: { value: string; label?: string }[];
}

export interface AdminColumn {
  field: string;
  header: string;
  readonly: boolean;
  key: boolean;
  required: boolean;
  /** text | int | num | date | bool | choice | list */
  kind: string;
  help: string;
  choices: string[];
  default: string;
  options: ColumnOptions | null;
}

export interface SheetInfo {
  autoKey: boolean;
  deletable: boolean;
  help: string;
  deleteLabel: string;
}

export type AdminRow = Record<string, string>;

export interface AdminRows {
  dataset: DatasetId;
  sheet: string;
  columns: AdminColumn[];
  sheetInfo: SheetInfo;
  total: number;
  rows: AdminRow[];
}

/** 행 하나의 검사 결과(파일 미리보기·화면 수정 확인) */
export interface RowView {
  sheet: string;
  row: number;
  key: string;
  label: string;
  action: RowAction;
  changes: { col: string; before: string; after: string }[];
  errors: { col: string; msg: string }[];
  warnings: string[];
  tags: string[];
}

export type SheetCount = Record<RowAction, number>;

/** 반영 결과: 시트별 {add, update, delete, hidden} 개수 + 인사이동 이력 수 */
export interface Applied {
  transfers?: number;
  [sheet: string]: unknown;
}

export interface UploadView {
  uploadId: string;
  dataset: DatasetId;
  fileName: string;
  status: UploadStatus;
  summary: Record<string, SheetCount> | null;
  notes: string[];
  errorRows: number | null;
  changeRows: number | null;
  canApply: boolean;
  rows: RowView[];
  applied?: Applied | null;
  goalCount?: number | null;
  /** form: 화면에서 고침 · file: 엑셀·CSV 올리기 */
  source?: 'form' | 'file';
  createdAt?: string;
}

export interface UploadSummary {
  uploadId: string;
  /** 예전 규정 엑셀 기록은 'regulations' 로 남아 있다 */
  dataset: DatasetId | 'regulations';
  fileName: string;
  status: UploadStatus;
  summary: { changeRows?: number; errorRows?: number; source?: string } | null;
  createdAt: string;
  appliedAt: string | null;
  admin: string | null;
}

/** 화면에서 한 건 고치기: 고칠 때는 바뀐 칸만, 추가할 때는 적은 칸만 보낸다 */
export interface EditRow {
  sheet: string;
  key: Record<string, string> | null;
  values?: Record<string, string>;
  delete?: boolean;
}

export interface EditCheck {
  dataset: DatasetId;
  token: string;
  summary: Record<string, SheetCount>;
  notes: string[];
  errorRows: number;
  changeRows: number;
  canApply: boolean;
  rows: RowView[];
}

export interface EditSaved {
  uploadId: string;
  dataset: DatasetId;
  applied: Applied;
  goalCount: number;
  rows: RowView[];
}

/** 지금 규정(도우미가 쓰는 버전) · available 이 false 면 원문 PDF 가 서버에 없다 */
export interface RegulationDoc {
  id: string;
  name: string;
  category: string;
  /** 적용 직원 구분(일반직·실무직 등) · 없으면 '' */
  group: string;
  overseas: boolean;
  version: string;
  effective: string;
  fileName: string;
  size: number;
  available: boolean;
}

/** 관리자가 올린 규정 PDF (처리 상태 없음 · 시스템 관리자가 내려받아 반영) */
export interface RegulationUpload {
  id: string;
  fileName: string;
  size: number;
  memo: string;
  admin: string;
  createdAt: string;
}

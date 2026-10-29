/* 확정 로드맵·진행·수정안·코멘트·사후 점검·보고서 (API-36~52) — 서버 plans.record / plans.reports */
import type { RegBundle, ResourceMap } from './catalog';
import type { StoredCause } from './common';
import type { ActDef, DeepQuiz, DeepGrade, DeepJudge, Handoff, OptionDef, Prefs, QuizQuestion } from './draft';

/** 계획에 들어간 활동(주차 계산 포함) */
export interface Activity extends ActDef {
  hours: number;
  hoursEstimated?: boolean;
  hoursBasis?: string;
  wFrom: number;
  wTo: number;
}

export interface PlanParams {
  start: number;
  hours: number;
  format: string;
  patch: Record<string, Partial<Activity>>;
}

/** 계획 내용(작성 중인 고른 안 draftPlan 과 확정 계획 plan 이 같은 모양) */
export interface PlanContent {
  opt: string;
  name: string;
  short: string;
  tagline: string;
  goal: string;
  displayTitle?: string;
  def: OptionDef;
  params: PlanParams;
  start: number;
  hours: number;
  format: string;
  acts: Activity[];
  totalH: number;
  weeks: number;
  cost: number;
  costUnknown: boolean;
  // 확정 이후
  rid?: string;
  version?: number;
  why?: string;
  confirmedAt?: string;
  prefs?: Prefs;
  assess?: { domain: string; questions: QuizQuestion[]; answers: Record<string, string>; deep?: Record<string, unknown> | null };
  handoff?: Handoff;
  selection?: { at: string; name: string; agent: string; source: string; perspective: string } | null;
}

export interface Progress {
  status: 'doing' | 'done' | string;
  memo?: string;
  file?: { name: string; size?: number; fileId?: string } | null;
  at?: string;
}

export interface Comment {
  id: string;
  by: string;
  byCode: string;
  fit: string;
  fitText: string;
  level: string;
  levelText: string;
  free: string;
  at: string;
  editedAt: string | null;
  stamp: string;
  status: 'new' | 'read' | 'applied' | string;
  readAt: string | null;
  appliedVersion: number | null;
}

export interface PostDeep {
  status: 'none' | 'running' | 'ready' | 'failed' | string;
  quiz?: DeepQuiz | null;
  mcq?: Record<string, string>;
  essay?: Record<string, string>;
  grade?: Record<string, DeepGrade> | null;
  judge?: Record<string, DeepJudge> | null;
  fail?: { cause?: StoredCause } | null;
  jobId?: string | null;
  [k: string]: unknown;
}

export interface PostCheck {
  answers: Record<string, string>;
  goalSelf: string;
  file: { name: string; size?: number; fileId?: string } | null;
  running?: boolean;
  fail?: { cause?: StoredCause } | null;
  jobId?: string | null;
  deep?: PostDeep | null;
}

/** 수정안(받은 쪽 계획과 바뀌는 쪽 계획) */
export interface PendingRevision {
  key?: string;
  from: PlanContent;
  to: PlanContent & { def: OptionDef & { support?: OptionDef['support'] } };
  summary?: string;
  notes?: string[];
  request?: string;
  source?: string;
  prefsFrom?: Prefs;
  prefsTo?: Prefs;
  supFail?: { cause?: StoredCause } | null;
  /** 자료·자격·기간·비용이 그대로라 이전 버전의 지원 조건 확인 결과를 그대로 씀 */
  supSame?: boolean;
  [k: string]: unknown;
}

export interface RevisionState {
  id: string;
  status: 'running' | 'ready' | 'failed' | string;
  error: StoredCause | null;
  jobId: string | null;
  request: Record<string, unknown> | null;
}

/** 화면에서 쓰는 중인 수정 요청 양식(브라우저에만 둔다) */
export interface RevForm {
  on: Record<string, boolean>;
  v: {
    hours: number | string;
    weeks: number | string;
    budget: number | string;
    format: string;
    cert: string;
    etc: string;
    start: number | string;
    pid: string;
    remove: string[];
    replace: string[];
    replaceHow: string;
    addRes: string[];
    addTask: string;
  };
  note: string;
  fromComment: string | false;
  cmStamp?: string;
  running?: boolean;
  fail?: { cause?: StoredCause } | StoredCause | null;
  jobId?: string | null;
}

export interface PlanRecord {
  id: string;
  status: 'active' | 'done' | 'archived' | string;
  createdAt: string;
  doneAt: string | null;
  archivedAt: string | null;
  resumedAt: string | null;
  plan: PlanContent;
  versions: PlanContent[];
  progress: Record<string, Progress>;
  comments: Comment[];
  pending: PendingRevision | null;
  revision: RevisionState | null;
  post: PostCheck;
  /** 화면 전용: 쓰는 중인 수정 요청 */
  rev?: RevForm | null;
}

export interface ReportItem {
  skill: string;
  from: string;
  to: string;
}

export interface Report {
  id: string;
  planId: string;
  opt: string;
  version: number;
  goal: string;
  gained: ReportItem[];
  still: ReportItem[];
  doneTitles: string[];
  restTitles: string[];
  /** 부서장 화면에는 오지 않음(사후 점검 원본 응답 · 첨부 비공개) */
  goalSelf?: string;
  file?: { name: string; size?: number } | null;
  good: string[];
  improve: string[];
  next: { goal: string; why: string } | null;
  deep?: {
    concepts: { concept: string; pre: string; post: string }[];
    essays: { area: string; pre: string; post: string | null; why: string | null }[];
  } | null;
  confirmed: boolean;
  createdAt: string;
  source?: string;
}

export interface PlanResponse {
  plan: PlanRecord;
  res?: ResourceMap;
  reg?: RegBundle;
}

export interface Workspace {
  plans: Record<string, PlanRecord>;
  reports: Report[];
  res?: ResourceMap;
  reg?: RegBundle;
  draft: import('./draft').DraftResponse;
}

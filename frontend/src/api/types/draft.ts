/* 작성 중인 로드맵 (API-14~35) — 서버(drafts.present)가 돌려주는 작성 문서.
   화면이 고치는 칸(goal·project·prefs·detailsOk·answers·deep*·chosen·edit)과 서버만 쓰는 칸(quiz·diag·handoff·gen·…Run·…Fail·doc)이 섞여 있다.
   에이전트 결과 안쪽은 모델 출력이라 칸이 늘 수 있어 필요한 칸만 적는다 */
import type { RegBundle, ResourceMap } from './catalog';
import type { StoredCause } from './common';

/** 세부 사항(학습 여건) — 비우면 '알아서' */
export interface Prefs {
  format: string;
  cert: string;
  hours: number | string;
  weeks: number | string;
  budget: number | string;
  etc: string;
}

export interface QuizQuestion {
  id: string;
  area: string;
  text: string;
  skill?: string;
  dbId?: string;
}

/** 심화 질문(10/23) — 결과 전에는 정답·해설·모범 답안이 빠져 온다 */
export interface DeepMcq {
  q: string;
  options: string[];
  answer?: string;
  explain?: string;
  concept?: string;
}
export interface DeepEssay {
  id: string;
  area: string;
  q: string;
  model?: string;
  points?: string[];
}
export interface DeepQuiz {
  mcq: Record<string, DeepMcq>;
  essays: DeepEssay[];
}

export interface Quiz {
  key: string;
  base?: { doc: unknown; goal: string; project: unknown } | null;
  domain: string;
  questions: QuizQuestion[];
  deep?: DeepQuiz | null;
  source?: string;
}

export interface DeepGrade {
  result: string; // right · wrong · dk
  [k: string]: unknown;
}
export interface DeepJudge {
  level: string;
  why?: string;
  [k: string]: unknown;
}

export interface Diag {
  key: string;
  gaps: string[];
  known: string[];
  level: Record<string, number>;
  answers?: Record<string, string>;
  outcome: string;
  startStage: number;
  resourceIds: string[];
  startReason: string;
  competencies: string[];
  handoffNotes: string[];
  source?: string;
  deep?: { grade?: Record<string, DeepGrade>; judge?: Record<string, DeepJudge>; [k: string]: unknown } | null;
  [k: string]: unknown;
}

export interface HandoffPrefs {
  format: string;
  formatKey: string;
  certRes: string | null;
  certPlan: string;
  budgetWon: number;
  budgetAuto: boolean;
  budgetLimit: number | null;
  weeklyHours: number | null;
  hoursAuto: boolean;
  deadlineWeeks: number | null;
}

export interface Handoff {
  key: string;
  goal: string;
  domain: string;
  gaps: string[];
  focus: string[];
  known: string[];
  prefs: HandoffPrefs;
  outcome: string;
  userNotes: string[];
  agentNotes: string[];
  startStage: number;
  startSuggested: number;
  startReason: string;
  userEdited: string[];
  resourceHints: string[];
  projectFile: unknown;
  projectSummary: string | null;
  deepCheck?: Record<string, unknown> | null;
  profile?: Record<string, unknown> | null;
  [k: string]: unknown;
}

/** 에이전트가 쓴 활동(안 정의 안) */
export interface ActDef {
  id: string;
  stage: number;
  title: string;
  res?: string | null;
  task?: boolean;
  how?: string;
  hours?: number;
  skills?: string[];
  key?: string;
}

export interface Support {
  level: string; // ok · partial · none …
  summary: string;
  basis: string[];
  missing: string[];
  [k: string]: unknown;
}

/** 관점 하나의 로드맵 안(A1·A2·A3) */
export interface OptionDef {
  id: string;
  name: string;
  short: string;
  tagline: string;
  scope?: string;
  reason?: string;
  pros: string[];
  cons: string[];
  acts: ActDef[];
  source?: string;
  support?: Support | null;
  supportFail?: { cause?: StoredCause } | null;
  offDomain?: boolean;
  weeklyHours?: number;
  /** 다시 만든 버전의 설명 */
  revSummary?: string;
  revRequest?: string;
  revNotes?: string[];
  [k: string]: unknown;
  displayTitle?: string;
}

export interface Gen {
  key: string;
  missing: string[];
  options: Record<string, OptionDef>;
  /** 다시 만든 안은 버전으로 쌓는다(관점 → 버전 목록) · cur 은 보고 있는 버전 번호 */
  hist?: Record<string, OptionDef[]> | null;
  cur?: Record<string, number> | null;
  /** 안별 다시 만들기 작업(서버가 jobId 를 채운다) */
  regenRun?: Record<string, { jobId?: string; req?: RegenRequest | null; [k: string]: unknown }> | null;
  regenErr?: Record<string, StoredCause> | null;
  [k: string]: unknown;
}

export interface GenRow {
  st: 'run' | 'ok' | 'fail' | string;
  tries?: number;
  out?: OptionDef;
  err?: StoredCause;
  [k: string]: unknown;
}

export interface GenRun {
  key?: string;
  rows: Record<string, GenRow>;
  [k: string]: unknown;
}

export interface RunState {
  jobId?: string;
  key?: string;
  at?: string | number;
  [k: string]: unknown;
}

export interface FailState {
  key?: string;
  cause?: StoredCause;
  [k: string]: unknown;
}

export interface DocState {
  name: string;
  status: 'reading' | 'ok' | 'fail' | string;
  step?: 'extract' | 'vision' | 'summary' | string;
  summary?: string;
  text?: string;
  format?: string;
  pages?: number;
  chars?: number;
  warnings?: string[];
  imageTotal?: number;
  imagesRead?: number;
  imageSkipped?: Record<string, number>;
  visionWhy?: string;
  source?: string;
  fail?: { cause?: StoredCause } | null;
  [k: string]: unknown;
}

/** 점검 결과 수정 화면에서 고치는 중인 값 (화면이 저장하고 PATCH 로 서버에 남긴다) */
export interface EditDoc {
  start: number | string;
  competencies: string[];
  resourceIds: string[];
  outcome: string;
  known: string[];
  prefs: Prefs;
}

/** 3안 중 하나 다시 만들기 요청(API-29) */
export interface RegenRequest {
  wish: string;
  quick: string[];
  removeActs: { key: string; title: string }[];
  replaceActs: { key: string; title: string }[];
}

export interface DraftDoc {
  v2Assessment?: { generationId: string; completed: boolean; activitiesReady?: boolean };
  goal: string;
  project: { name: string; size?: number } | null;
  prefs: Prefs;
  detailsOk: boolean;
  quiz: Quiz | null;
  answers: Record<string, string>;
  deepOn: boolean;
  deepMcq: Record<string, string>;
  deepEssay: Record<string, string>;
  diag: Diag | null;
  startStage: number | null;
  fix: Record<string, unknown> | null;
  edit: EditDoc | null;
  handoff: Handoff | null;
  gen: Gen | null;
  chosen: string | null;
  quizFail: FailState | null;
  diagFail: FailState | null;
  genRun: GenRun | null;
  doc: DocState | null;
  genPrefs: Prefs | null;
  quizRun: RunState | null;
  diagRun: RunState | null;
  [k: string]: unknown;
}

/** 작성 문서 응답 공통 */
export interface DraftResponse {
  draftId: string | null;
  draft: DraftDoc | null;
  draftPlan: import('./plan').PlanContent | null;
  lastNew?: string | null;
  res?: ResourceMap;
  reg?: RegBundle;
  jobs?: Record<string, string>;
  jobId?: string;
}

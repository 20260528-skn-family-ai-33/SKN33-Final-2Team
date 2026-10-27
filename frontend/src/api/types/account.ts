/* 계정·내 정보 (API-01~08) */

export interface PersonRef {
  id: string;
  name: string;
  code: string;
}

export interface Evaluation {
  period: string;
  title: string;
  grade: string;
  score: string;
  consent: boolean;
  consentDefault: boolean;
}

export interface SelfProfile {
  workDesc?: string;
  expStatus?: string;
  expSummary?: string;
  devYears?: number | null;
  inputStatus?: Record<string, string>;
}

/** 직원 보기(profile.view) — 로그인 계정·부서장 소속 직원 목록에 같은 모양으로 온다 */
export interface User {
  id: string;
  code: string;
  name: string;
  role: string;
  source: string;
  hireDate: string;
  dept: string;
  parentDept: string;
  deptId: number;
  grade: string;
  jobFamily: string;
  position: string | null;
  job: string;
  task: string;
  supervisor: boolean;
  empGroup: string;
  status: string;
  accountStatus: string;
  validFrom: string;
  changeReason: string;
  gradeSince: string;
  supGroup: { name: string; id: string } | null;
  members: PersonRef[];
  planGroup: { name: string; id: string } | null;
  mySupervisor: PersonRef | null;
  profile: SelfProfile;
  tech: string[];
  certs: string[];
  learning: string[];
  projects: string[];
  evals: Evaluation[];
  edited: boolean;
  editedAt: string | null;
  education: string[];
}

export type ServerProvider = 'ollama' | 'openai';
export type FailSim = Record<string, boolean>;

export interface UserSettings {
  aiProvider: ServerProvider;
  demoMock: boolean;
  failSim: FailSim;
}

export type Account =
  | ({ accountType: 'employee'; user: User } & UserSettings)
  | { accountType: 'admin'; admin: { id: number; name: string } };

export interface DemoAccount {
  code: string;
  name: string;
  dept?: string;
  supervisor?: boolean;
  /** 팀이 넣은 테스트 계정 */
  team?: boolean;
  [k: string]: unknown;
}

export interface DemoAccounts {
  accounts: DemoAccount[];
  demoPassword?: string;
  adminLogin?: string;
}

export interface ProfileView {
  hr: Record<string, string | null>;
  permission: { role: string; supervisor: boolean | null; mySupervisor: PersonRef | null };
  self: {
    profile: SelfProfile;
    tech: string[];
    certs: string[];
    learning: string[];
    projects: string[];
    edited: boolean;
    editedAt: string | null;
  };
  evaluations: Evaluation[];
  view: User;
}

export interface GoalCandidate {
  goal: string;
  why: string;
  basis: string[];
}

export interface GoalSuggestions {
  status: string;
  source: string;
  note: string;
  used: string[];
  trigger: string;
  jobId: string | null;
  error: import('./common').StoredCause | null;
  stale: boolean;
  updatedAt: string;
  candidates: GoalCandidate[];
  who: string;
}

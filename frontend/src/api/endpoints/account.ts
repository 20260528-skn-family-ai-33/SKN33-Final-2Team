/* 인증·내 정보 (API-01~08) · AI 모델·시연 도구 (API-10~12) */
import { enc, http } from '../client';
import type { Account, DemoAccounts, GoalSuggestions, ProfileView, ServerProvider, UserSettings } from '../types/account';
import type { JobStarted } from '../types/common';
import type { Workspace } from '../types/plan';

export const accountApi = {
  /** 로그인 화면 '직원 고르기'(시연 전용) */
  demoAccounts: () => http.get<DemoAccounts>('/demo/accounts'),
  login: (employeeNo: string, password: string, keepSignedIn: boolean) => http.post<Account>('/auth/login', { employeeNo, password, keepSignedIn }),
  logout: () => http.post<null>('/auth/logout'),
  me: () => http.get<Account>('/me'),
  profile: () => http.get<ProfileView>('/me/profile'),
  saveSelf: (body: Record<string, unknown>) => http.put<ProfileView>('/me/profile/self', body),
  revertSelf: () => http.del<ProfileView>('/me/profile/self'),
  consent: (period: string, consent: boolean) => http.put<ProfileView>(`/me/evaluations/${enc(period)}/consent`, { consent }),
  goals: () => http.get<GoalSuggestions>('/me/goal-suggestions'),
  goalsRegenerate: () => http.post<Partial<JobStarted> & Partial<GoalSuggestions>>('/me/goal-suggestions/regenerate'),
  workspace: () => http.get<Workspace>('/me/workspace'),
};

export interface ProviderInfo {
  id: ServerProvider;
  label: string;
  available: boolean;
  reason: string;
  target?: string;
  models: { default: string; roadmap: string; embed: string; vision: string };
  timeout?: number;
}

export interface ProvidersResponse {
  current: ServerProvider;
  providers: ProviderInfo[];
  docLibs: Record<string, boolean>;
}

export interface ModelState {
  name: string;
  role: string;
  installed: boolean;
  loaded: boolean;
}

export interface AiStatusResponse {
  ok?: boolean;
  models?: ModelState[];
  version?: string;
  [k: string]: unknown;
}

export interface AgentLogEntry {
  at: string;
  /** 그 호출이 누구의 일이었는지(직원 번호·이름) · 시연·디버그용이라 모든 계정의 호출이 온다 */
  employeeId?: number;
  employee?: string;
  /** 관리자 화면에서 시작한 호출이면 '관리자' */
  by?: string;
  agent: string;
  task: string;
  model?: string;
  mode: string;
  ms: number;
  error?: string;
  input: string;
  output: string;
}

export const aiApi = {
  providers: () => http.get<ProvidersResponse>('/ai/providers'),
  setProvider: (provider: ServerProvider) => http.put<{ provider: ServerProvider }>('/me/ai-provider', { provider }),
  status: (provider: ServerProvider) => http.get<AiStatusResponse>(`/ai/status?provider=${enc(provider)}`),
  log: () => http.get<{ log: AgentLogEntry[] }>('/ai/log'),
};

export const demoApi = {
  settings: (body: Partial<UserSettings>) => http.put<UserSettings>('/me/demo-settings', body),
  reset: () => http.post<{ ok: boolean }>('/demo/reset'),
  jump: (stage: string) => http.post<{ entry?: string }>('/demo/jump', { stage }),
};

/* 인증·내 정보 (API-01~08) · AI 모델·시연 도구 (API-10~12) */
import { enc, http } from '../client';
import type { Account, DemoAccounts, GoalSuggestions, ProfileView, ReasoningPicks, ServerProvider, UserSettings } from '../types/account';
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
  consent: (period: string, consent: boolean) => http.put<{ period: string; consent: boolean }>(`/me/evaluations/${enc(period)}/consent`, { consent }),
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
  /** regulation: 규정 에이전트(도우미 답변·안별 지원 조건 확인) 모델 · 없는 옛 응답이면 default 를 쓴다 */
  models: { default: string; roadmap: string; regulation?: string; embed: string; vision: string };
  timeout?: number;
  /** 추론 정도: default 는 서버 기본값(.env · null 이면 모델 기본값). levels·modelDefault 는 OpenAI 만 여기서 오고
   *  (.env · 비면 기본 모델 gpt-6-luna 의 코드 값), RunPod-Ollama 는 모델마다 달라 levels 가 null — 연결 확인 때
   *  진단·로드맵 모델의 ModelState.think 에서 받는다. modelDefault 는 보내지 않을 때 모델이 쓰는 값(모르면 null) */
  reasoning?: { levels: string[] | null; default: string | null; modelDefault?: string | null };
}

/** 모델이 고를 수 있는 추론 정도(on·off 또는 low·medium·high 등). levels 가 비면 고를 단계 없음 */
export interface ThinkLevels {
  levels: string[];
  default: string | null;
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
  /** Ollama /api/show 로 확인한 이 모델의 추론 정도 단계(진단·로드맵 모델만 · 규정 모델은 늘 꺼서 null). null 이면 확인하지 못함 */
  think?: ThinkLevels | null;
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
  setReasoning: (provider: ServerProvider, level: string | null) => http.put<{ reasoning: ReasoningPicks }>('/me/reasoning', { provider, level }),
  status: (provider: ServerProvider) => http.get<AiStatusResponse>(`/ai/status?provider=${enc(provider)}`),
  log: () => http.get<{ log: AgentLogEntry[] }>('/ai/log'),
};

export const demoApi = {
  settings: (body: Partial<UserSettings>) => http.put<UserSettings>('/me/demo-settings', body),
  reset: () => http.post<{ ok: boolean }>('/demo/reset'),
  jump: (stage: string) => http.post<{ entry?: string }>('/demo/jump', { stage }),
};

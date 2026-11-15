/* 인증·내 정보 (API-01~08) · AI 모델·시연 도구 (API-10~12) */
import { enc, http } from '../client';
import type { Account, DemoAccounts, GoalSuggestions, ProfileView, ProviderPolicy, ReasoningPicks, ServerProvider, UserSettings } from '../types/account';
import type { JobStarted } from '../types/common';
import type { Workspace } from '../types/plan';

export const accountApi = {
  /** 로그인 화면 '직원 고르기'(시연 전용) */
  demoAccounts: () => http.get<DemoAccounts>('/demo/accounts'),
  login: (employeeNo: string, password: string, keepSignedIn: boolean) => http.post<Account>('/auth/login', { employeeNo, password, keepSignedIn }),
  logout: () => http.post<null>('/auth/logout'),
  me: () => http.get<Account>('/me'),
  profile: () => http.get<ProfileView>('/me/profile'),
  changePassword: (currentPassword: string, newPassword: string) =>
    http.put<null>('/me/password', { currentPassword, newPassword }),
  saveSelf: (body: Record<string, unknown>) => http.put<ProfileView>('/me/profile/self', body),
  revertSelf: () => http.del<ProfileView>('/me/profile/self'),

  goals: () => http.get<GoalSuggestions>('/me/goal-suggestions'),
  goalsEnsure: () => http.post<GoalSuggestions>('/me/goal-suggestions/ensure'),
  goalsRegenerate: () => http.post<Partial<JobStarted> & Partial<GoalSuggestions>>('/me/goal-suggestions/regenerate'),
  workspace: () => http.get<Workspace>('/me/workspace'),
};

export interface ProviderInfo {
  id: ServerProvider;
  label: string;
  available: boolean;
  reason: string;
  target?: string;
  /** regulation: 규정 에이전트(도우미 답변) 모델 · 없는 옛 응답이면 default 를 쓴다 */
  models: { default: string; roadmap: string; regulation?: string; embed: string; vision: string };
  timeout?: number;
  /** 추론 정도: default 는 서버 기본값(.env · null 이면 모델 기본값). OpenAI 는 levels 가 .env(비면 기본 모델
   *  gpt-6-luna 의 코드 값)이고 modelDefault 는 보내지 않을 때 모델이 쓰는 값(모르면 null).
   *  RunPod-Ollama 는 늘 추론 없이 불러 levels 가 빈 목록, default 가 'off' 다 */
  reasoning?: { levels: string[] | null; default: string | null; modelDefault?: string | null };
}

export interface ProvidersResponse {
  current: ServerProvider;
  policy?: ProviderPolicy;
  employeeReasoning?: ReasoningPicks;
  /** 서버의 시연 허용 여부. 구버전 응답의 누락은 허용하지 않는 것으로 처리한다. */
  demoMode?: boolean;
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

/** 에이전트 동작 기록 목록의 한 줄(요약). 입력·출력 전문은 길어서 펼칠 때 aiApi.logEntry(id) 로 받는다 */
export interface AgentLogEntry {
  id: number;
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
  traceId?: string;
  failedStage?: { id: string; label: string };
  /** 그 기록 안에서 실제 모델을 부른 횟수 */
  callCount: number;
}

/** 모델 호출 한 번: 실제로 보낸 메시지와 받은 원문 전체(자르지 않음 · 이미지는 개수만) */
export interface AgentModelCall {
  role: string;
  model: string;
  ms: number;
  error?: string;
  system: string;
  /** 시스템 지시 뒤의 메시지(이전 대화 → 마지막이 이번 입력) */
  messages: { role: string; content: string }[];
  images: number;
  output: string;
  stageId?: string;
}

/** 기록 한 건의 전문. 에이전트 실행 기록에만 input·output 이 있고, 모델을 바로 부른 기록은 calls 하나뿐 */
export interface AgentLogDetail extends Omit<AgentLogEntry, 'callCount'> {
  input?: string;
  output?: string;
  calls: AgentModelCall[];
  stages?: { id: string; label: string; status: 'running' | 'ok' | 'failed'; ms?: number; parentId?: string; errorType?: string }[];
}

export const aiApi = {
  providers: () => http.get<ProvidersResponse>('/ai/providers'),
  setProvider: (provider: ServerProvider) => http.put<{ provider: ServerProvider }>('/me/ai-provider', { provider }),
  setReasoning: (provider: ServerProvider, level: string | null) => http.put<{ reasoning: ReasoningPicks }>('/me/reasoning', { provider, level }),
  status: (provider: ServerProvider) => http.get<AiStatusResponse>(`/ai/status?provider=${enc(provider)}`),
  log: () => http.get<{ log: AgentLogEntry[] }>('/ai/log'),
  logEntry: (id: number) => http.get<AgentLogDetail>(`/ai/log/${enc(String(id))}`),
};

export const demoApi = {
  settings: (body: Partial<UserSettings>) => http.put<UserSettings>('/me/demo-settings', body),
  reset: () => http.post<{ ok: boolean }>('/demo/reset'),
  jump: (stage: string) => http.post<{ entry?: string }>('/demo/jump', { stage }),
};

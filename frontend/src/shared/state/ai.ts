/* AI 모드·연결 상태·오류 안내 (5차 gp-ai.js 를 옮김)
   값은 서버에서 받는다: 모드·모델 이름(/ai/providers) · 사용자가 고른 모드·시연 도구 설정(/me) · 연결 확인(/ai/status).
   고른 모드를 쓸 수 없으면 'off' — 가데이터나 다른 모드로 자동 대체하지 않는다(설계서 v1.7 그림 12). 다시 시도는 사용자가 누를 때만 */
import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';
import { ApiError } from '@/api/client';
import { canUseDemo } from '@/shared/lib/demoAccess';
import { aiApi, demoApi, type ModelState, type ProviderInfo } from '@/api/endpoints/account';
import type { FailSim, ProviderPolicy, ServerProvider, UserSettings } from '@/api/types/account';
import type { StoredCause } from '@/api/types/common';
import { signInSeq } from './session';

/** 화면은 4차처럼 'api' 를 OpenAI 로 쓰고, 서버에는 'openai' 로 보낸다 */
export type UiProvider = 'ollama' | 'api';
export type Mode = UiProvider | 'mock' | 'off';
/** 에이전트가 모델을 부르는 역할: 진단(default)·로드맵·규정·이미지 읽기 */
export type ModelRole = 'default' | 'roadmap' | 'regulation' | 'vision';

export const PROV: Record<string, string> = { ollama: 'RunPod-Ollama', api: 'OpenAI API', openai: 'OpenAI API', mock: '가데이터' };
export const toUi = (p: string): UiProvider => (p === 'openai' ? 'api' : (p as UiProvider));
export const toSrv = (p: string): ServerProvider => (p === 'api' ? 'openai' : (p as ServerProvider));

export interface Conn {
  state: 'idle' | 'checking' | 'ok' | 'cold' | 'error';
  provider: string;
  at: number;
  ms?: number;
  loadMs?: number;
  error?: string;
  raw?: string;
  kind?: string;
  hint?: string;
  via?: string;
  version?: string;
  models?: ModelState[] | null;
  waiting?: string[];
}

interface AiState {
  status: { checked: boolean; server?: boolean; policy?: ProviderPolicy; demoMode?: boolean; docLibs: Record<string, boolean>; providers: Record<string, ProviderInfo> };
  settings: UserSettings;
  conn: Conn;
}

export const useAi = create<AiState>(() => ({
  status: { checked: false, demoMode: false, providers: {}, docLibs: {} },
  settings: { aiProvider: 'ollama', demoMock: false, failSim: {}, reasoning: {} },
  conn: { state: 'idle', provider: '', at: 0 },
}));

const g = () => useAi.getState();
const prov = (p: string, s: AiState = g()): Partial<ProviderInfo> => s.status.providers[toSrv(p)] || {};
const choiceOf = (s: AiState): UiProvider => toUi(s.status.policy && s.status.policy !== 'employee' ? s.status.policy : s.settings.aiProvider || 'ollama');
const modeOf = (s: AiState): Mode => {
  const choice = choiceOf(s);
  return s.settings.demoMock ? 'mock' : prov(choice, s).available ? choice : 'off';
};

export const ai = {
  demoAllowed: (): boolean => g().status.demoMode === true,
  choice: (): UiProvider => choiceOf(g()),
  demoMock: (): boolean => !!g().settings.demoMock,
  available: (p: string): boolean => !!prov(p).available,
  unavailableWhy: (p: string): string => (!g().status.checked ? '확인 중…' : prov(p).reason || '설정을 확인해 주세요'),
  mode: (): Mode => modeOf(g()),
  live: (): boolean => ai.mode() === 'ollama' || ai.mode() === 'api',
  off: (): boolean => ai.mode() === 'off',
  modelName: (role: ModelRole = 'default'): string => {
    const m = prov(ai.mode()).models;
    if (!m) return '';
    return role === 'vision' ? m.vision || '' : role === 'default' ? m.default || '' : m[role] || m.default || '';
  },
  ollamaInfo: () => ({ model: prov('ollama').models?.default || '' }),
  openaiModel: (): string => prov('api').models?.default || '',
  /** 고를 수 있는 추론 정도 단계. OpenAI 는 서버 설정(.env) · 빈 목록이면 고를 단계가 없음.
   *  RunPod-Ollama 는 모든 생성을 추론 없이 부르므로 늘 빈 목록(고르는 칸을 두지 않음) */
  reasoningLevels: (p: UiProvider): string[] => (p === 'api' ? prov('api').reasoning?.levels || [] : []),
  /** 고르지 않았을 때 쓰는 값: 서버 기본값(.env) → OpenAI 는 서버가 아는 기본 모델 값. RunPod-Ollama 는 늘 'off'. null 이면 모름 */
  reasoningDefault: (p: UiProvider): string | null =>
    p === 'ollama' ? OLLAMA_THINK : prov(p).reasoning?.default ?? prov('api').reasoning?.modelDefault ?? null,
  /** 직원·관리자가 고른 단계. null 이면 기본값을 따름. RunPod-Ollama 는 예전에 저장된 값이 있어도 늘 'off' */
  reasoning: (p: UiProvider): string | null => (p === 'ollama' ? OLLAMA_THINK : g().settings.reasoning[toSrv(p)] ?? null),
  failSim: (): FailSim => ({ ...Object.fromEntries(SIM_KINDS.map((k) => [k, false])), ...(g().settings.failSim || {}) }),
};

/** RunPod-Ollama 의 추론 정도: 서버(config.OLLAMA_THINK)가 모든 호출에 think: false 를 보내는 고정값 */
export const OLLAMA_THINK = 'off';

const LEVEL_LABEL: Record<string, string> = { off: '끔', on: '켬', none: '없음', minimal: '최소', low: '낮음', medium: '보통', high: '높음', xhigh: '매우 높음', max: '최대' };
/** 단계 이름 → 화면 글자. 모르는 이름(모델이 정한 이름)은 그대로 */
export const levelLabel = (level: string): string => LEVEL_LABEL[level] || level;

export const unavailableWhyText = (): string => ai.unavailableWhy(ai.choice());

/** 화면 구독용: 모드·고른 모델·연결 상태가 바뀌면 다시 그린다(값은 ai.* 로 읽는다) */
export const useAiMode = (): { mode: Mode; choice: UiProvider; demo: boolean; checked: boolean; conn: Conn } =>
  useAi(
    useShallow((s) => ({ mode: modeOf(s), choice: choiceOf(s), demo: !!s.settings.demoMock, checked: s.status.checked, conn: s.conn })),
  );

export const DOC_CHARS = 6000;
export const SIM_KINDS = ['goal', 'doc', 'quiz', 'diag', 'gen', 'sup', 'report', 'reg', 'rev'];

/** 서버에서 적용 중인 시연 설정을 끌 도구가 이 화면 빌드에 없을 때만 복구를 제공한다. */
export function canClearHiddenDemoSettings({ status, settings }: AiState): boolean {
  return status.demoMode === true && !canUseDemo(status.demoMode)
    && (settings.demoMock || SIM_KINDS.some(kind => settings.failSim[kind]));
}

let statusRequest = 0;
export async function checkStatus(): Promise<void> {
  const request = ++statusRequest;
  const session = signInSeq();
  useAi.setState((s) => ({ status: { ...s.status, demoMode: false } }));
  try {
    const j = await aiApi.providers();
    if (request !== statusRequest || session !== signInSeq()) return;
    useAi.setState((s) => ({
      settings: { ...s.settings, aiProvider: j.current,
        reasoning: (j.policy && j.policy !== 'employee') || j.policy !== s.status.policy ? j.employeeReasoning ?? s.settings.reasoning : s.settings.reasoning },
      status: { checked: true, server: true, policy: j.policy ?? 'employee', demoMode: j.demoMode === true,
        docLibs: j.docLibs || {}, providers: Object.fromEntries(j.providers.map((p) => [p.id, p])) },
    }));
  } catch {
    if (request !== statusRequest || session !== signInSeq()) return;
    useAi.setState((s) => ({ status: { ...s.status, checked: true, server: false, demoMode: false } }));
  }
}

export function applySettings(s: Partial<UserSettings> | null | undefined): void {
  if (!s) return;
  useAi.setState((st) => ({
    settings: {
      aiProvider: s.aiProvider || st.settings.aiProvider,
      demoMock: !!s.demoMock,
      failSim: s.failSim || {},
      reasoning: s.reasoning !== undefined ? s.reasoning || {} : st.settings.reasoning,
    },
  }));
}

export async function setChoice(p: UiProvider): Promise<void> {
  const seq = signInSeq();
  try {
    const saved = await aiApi.setProvider(toSrv(p));
    if (seq === signInSeq()) useAi.setState((s) => ({ settings: { ...s.settings, aiProvider: saved.provider } }));
  } catch (error) {
    if (seq === signInSeq() && error instanceof ApiError && error.code === 'PROVIDER_MANAGED') await checkStatus();
    throw error;
  }
}

/* 추론 정도 저장은 하나씩 차례로 보낸다: 빠르게 바꾸면 앞 요청의 늦은 응답·실패가 마지막 선택을 덮지 않게
   (PR #40 리뷰). 화면은 마지막 선택만 서버 응답으로 맞추고, 그것이 실패하면 서버에 마지막으로 저장된 값으로 돌린다 */
let reasoningQueue: Promise<unknown> = Promise.resolve();
let reasoningLatest = 0;
/** 저장이 진행 중일 때 서버에 마지막으로 저장된 값(진행 중이 아니면 null · 화면 값이 곧 서버 값) */
let reasoningSaved: UserSettings['reasoning'] | null = null;

/** 모드별 추론 정도 저장(null 이면 기본값으로) */
export async function setReasoning(p: UiProvider, level: string | null): Promise<void> {
  const seq = ++reasoningLatest;
  const cur = g().settings.reasoning;
  if (reasoningSaved === null) reasoningSaved = cur;
  const next = { ...cur };
  if (level) next[toSrv(p)] = level;
  else delete next[toSrv(p)];
  useAi.setState((s) => ({ settings: { ...s.settings, reasoning: next } }));
  const req = reasoningQueue.then(() => aiApi.setReasoning(toSrv(p), level));
  reasoningQueue = req.catch(() => undefined);
  const show = (reasoning: UserSettings['reasoning']) => {
    if (seq !== reasoningLatest) return;
    useAi.setState((s) => ({ settings: { ...s.settings, reasoning } }));
    reasoningSaved = null;
  };
  try {
    reasoningSaved = (await req).reasoning || {};
    show(reasoningSaved);
  } catch (err) {
    show(reasoningSaved || cur);
    throw err;
  }
}

// 두 시연 옵션은 서버에서 같은 행을 읽고 저장하므로 요청도 함께 직렬화한다.
let demoQueue: Promise<unknown> = Promise.resolve();
let demoSession = -1;

/** 저장된 시연 옵션만 표시한다. 이전 로그인의 결과이면 호출자의 알림·연결 확인도 생략하도록 false를 반환한다. */
function saveDemoSettings(change: Partial<Pick<UserSettings, 'demoMock' | 'failSim'>>): Promise<boolean> {
  const seq = signInSeq();
  if (demoSession !== seq) {
    demoSession = seq;
    demoQueue = Promise.resolve();
  }
  const request = demoQueue.then(async () => {
    if (signInSeq() !== seq) return false;
    try {
      const saved = await demoApi.settings(change);
      if (signInSeq() !== seq) return false;
      // 제공자·추론값은 별도 API에서 바뀔 수 있으므로 이 응답으로 덮지 않는다.
      useAi.setState((s) => ({ settings: { ...s.settings, demoMock: !!saved.demoMock, failSim: saved.failSim || {} } }));
      return true;
    } catch (err) {
      if (signInSeq() !== seq) return false;
      throw err;
    }
  });
  // 실패는 호출자에게 전달하되 다음 시연 설정 저장을 막지 않는다.
  demoQueue = request.catch(() => undefined);
  return request;
}

export function setDemoMock(on: boolean): Promise<boolean> {
  return saveDemoSettings({ demoMock: on });
}

export function setFailSim(k: string, on: boolean): Promise<boolean> {
  return saveDemoSettings({ failSim: { [k]: on } });
}

export function clearDemoSettings(): Promise<boolean> {
  return saveDemoSettings({ demoMock: false, failSim: Object.fromEntries(SIM_KINDS.map(kind => [kind, false])) });
}

/* ── 연결 상태 (좌측 'AI 모델'·진단 에이전트 창 상단) ── */
function setConn(state: Conn['state'], extra: Partial<Conn>): void {
  const prev = g().conn;
  useAi.setState({ conn: { state, provider: ai.mode(), at: Date.now(), ms: 0, loadMs: 0, error: '', raw: '', kind: '', models: prev.models || null, ...extra } });
}

export const resetConn = (): void => useAi.setState({ conn: { state: 'idle', provider: '', at: 0 } });

export async function ping(): Promise<void> {
  const p = ai.mode();
  const c = g().conn;
  if (!ai.live() || (c.state === 'checking' && c.provider === p)) return;
  setConn('checking', { provider: p, models: c.provider === p ? c.models : null });
  const t0 = performance.now();
  try {
    const j = await aiApi.status(toSrv(p));
    if (ai.mode() !== p) return;
    setConn('ok', { provider: p, ms: Math.round(performance.now() - t0), via: 'ping', models: j.models || null, version: j.version || '' });
  } catch (err) {
    if (ai.mode() !== p) return;
    const k = cause(err);
    setConn('error', { provider: p, error: k.text, raw: k.raw, kind: k.kind, hint: k.hint, via: 'ping' });
  }
}

/** 실제 호출 결과로 연결 상태를 고친다: 연결 문제(서버·설정·Pod·모델·키)만 '연결 안 됨'으로 */
const CONN_KINDS = ['server', 'config', 'conn', 'model', 'auth'];
export function noteResult(k: Cause | null, meta?: { ms?: number; loadMs?: number }): void {
  if (!ai.live()) return;
  if (!k) {
    if (g().conn.state !== 'ok') setConn('ok', { provider: ai.mode(), via: 'call', ms: meta?.ms || 0, loadMs: meta?.loadMs || 0, models: g().conn.models });
    return;
  }
  if (CONN_KINDS.includes(k.kind)) setConn('error', { provider: ai.mode(), error: k.text, raw: k.raw, kind: k.kind, hint: k.hint, via: 'call' });
}

export function connFor(role: string, c: Conn = g().conn): Conn {
  if (c.provider !== ai.mode()) return { state: 'idle', provider: '', at: 0 };
  if (c.state !== 'ok' || !c.models) return c;
  let pick = c.models.filter((m) => (role === 'all' ? true : m.role === (role || 'default')));
  if (!pick.length) pick = c.models.filter((m) => m.role === 'default');
  const miss = pick.find((m) => !m.installed);
  if (miss)
    return {
      ...c,
      state: 'error',
      kind: 'model',
      error: `‘${miss.name}’ 모델이 Ollama에 없어요`,
      raw: `설치된 모델 목록(api/tags)에 ${miss.name}이 없음`,
      hint: 'Pod에서 팀 모델을 받아 growpath-27b·growpath-regulation-4b 이름으로 만든 뒤(RunPod 연결 절차 2-4) 다시 시도해 주세요. .env에 원본 모델 이름을 넣었다면 Pod의 ollama list 이름과 같은지 확인해 주세요',
    };
  const wait = pick.filter((m) => m.role !== 'embed' && !m.loaded).map((m) => m.name);
  if (wait.length) return { ...c, state: 'cold', waiting: wait };
  return c;
}

/* ── 오류 안내: 사용자에게는 쉬운 말과 할 일, 원인·조치·원문은 운영자용 ── */
const USER_TEXT: Record<string, string> = {
  off: '고른 AI 모델을 지금 쓸 수 없어요',
  lost: '진행 중이던 작업을 찾지 못했어요',
  server: 'AI 서버에 연결하지 못했어요',
  config: 'AI 모델 설정이 아직 준비되지 않았어요',
  conn: 'AI 모델이 지금 응답하지 않아요',
  model: 'AI 모델을 아직 쓸 수 없어요',
  auth: 'AI 모델을 쓸 권한을 확인하지 못했어요',
  timeout: 'AI 모델의 응답이 너무 오래 걸려 멈췄어요',
  memory: 'AI 모델이 지금 요청을 처리하지 못했어요',
  limit: '요청이 몰려 AI 모델을 잠시 쓸 수 없어요',
  format: 'AI가 만든 결과를 화면에 쓸 수 없었어요',
  other: '처리하는 중에 문제가 생겼어요',
  docfmt: '이 형식의 파일은 읽을 수 없어요',
  doclib: '이 형식을 읽는 도구가 아직 준비되지 않았어요',
  docread: '기획서 파일을 읽지 못했어요',
  docbig: '파일이 너무 커요(15MB까지)',
  visioncfg: '이미지를 볼 수 있는 AI 모델이 준비되지 않았어요',
};
export const userText = (kind?: string): string => USER_TEXT[kind || ''] || USER_TEXT.other;

export function userTodo(kind?: string): string[] {
  if (kind === 'employee_group') return ['인사 담당 부서에 직원 구분 등록 여부를 확인해 주세요.'];
  if (kind === 'docbig') return ['15MB 이하로 줄여 다시 골라 주세요.', '기획서 없이 목표만으로 진행해도 돼요.'];
  if (/^doc/.test(kind || '')) return ['DOCX·PPTX·HWPX·PDF·TXT 중 하나로 저장해 다시 골라 주세요.', '기획서 없이 목표만으로 진행해도 돼요.'];
  const other = ai.choice() === 'api' ? 'ollama' : 'api';
  const canSwitch = (!g().status.policy || g().status.policy === 'employee') && ai.available(other);
  if (kind === 'off')
    return ['서버 연결과 모델 설정을 확인해 주세요.', '자동 대체하지 않아요. 연결한 뒤 다시 시도해 주세요.'].concat(
      canSwitch ? [`좌측 ‘AI 모델’에서 ${PROV[other]}를 골라 볼 수도 있어요.`] : [],
    );
  if (kind === 'lost') return ['다시 시도하면 새로 만들어요.'];
  const t = [kind === 'format' ? '다시 시도하면 대부분 해결돼요.' : '잠시 뒤 다시 시도해 주세요.'];
  if (kind !== 'server' && !ai.demoMock() && canSwitch) t.push(`좌측 ‘AI 모델’에서 ${PROV[other]}를 골라 볼 수도 있어요.`);
  t.push('계속되면 담당자에게 알려 주세요.');
  return t;
}

/** 화면 원인 {kind, text(원인), hint(조치), raw(원문), user(사용자용)} */
export interface Cause {
  kind: string;
  text: string;
  hint: string;
  raw: string;
  user: string;
  code?: string;
  retryable?: boolean;
}

/** 서버 오류(ApiError) 또는 서버가 저장해 둔 원인 객체 → 화면 원인 */
export function cause(err: unknown): Cause {
  const e = err as (StoredCause & { kind?: string }) | null;
  if (e && !(err instanceof Error) && e.kind && (e.text !== undefined || e.user !== undefined))
    return { kind: e.kind, text: e.text || '', hint: e.hint || '', raw: e.raw || '', user: e.user || userText(e.kind), code: e.code, retryable: e.retryable };
  if (err instanceof ApiError) {
    const p = err.payload;
    const kind = p.kind || ({ AUTH_REQUIRED: 'server' } as Record<string, string>)[p.code || ''] || 'other';
    return { kind, text: p.cause || p.message || '', hint: p.hint || '', raw: p.raw || '', user: p.message || userText(kind), code: p.code, retryable: !!p.retryable };
  }
  if (e && typeof e === 'object' && !(err instanceof Error) && (e.text || e.user || e.hint)) {
    const kind = e.kind || 'other';
    return { kind, text: e.text || '', hint: e.hint || '', raw: e.raw || '', user: e.user || userText(kind) };
  }
  const m = String((err as Error)?.message || err || '');
  return { kind: 'server', text: m, hint: '백엔드가 켜져 있는지 확인해 주세요', raw: m, user: userText('server') };
}

/** 사용자 문장: '원인. 할 일' */
export const errText = (c: Partial<Cause> | null | undefined): string => `${c?.user || userText(c?.kind)}. ${userTodo(c?.kind).join(' ')}`;

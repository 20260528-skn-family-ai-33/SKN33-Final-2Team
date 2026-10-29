/* AI 모드·연결 상태·오류 안내 (5차 gp-ai.js 를 옮김)
   값은 서버에서 받는다: 모드·모델 이름(/ai/providers) · 사용자가 고른 모드·시연 도구 설정(/me) · 연결 확인(/ai/status).
   고른 모드를 쓸 수 없으면 'off' — 가데이터나 다른 모드로 자동 대체하지 않는다(설계서 v1.7 그림 12). 다시 시도는 사용자가 누를 때만 */
import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';
import { ApiError } from '@/api/client';
import { aiApi, demoApi, type ModelState, type ProviderInfo, type ThinkLevels } from '@/api/endpoints/account';
import type { FailSim, ServerProvider, UserSettings } from '@/api/types/account';
import type { StoredCause } from '@/api/types/common';

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
  status: { checked: boolean; server?: boolean; docLibs: Record<string, boolean>; providers: Record<string, ProviderInfo> };
  settings: UserSettings;
  conn: Conn;
}

export const useAi = create<AiState>(() => ({
  status: { checked: false, providers: {}, docLibs: {} },
  settings: { aiProvider: 'ollama', demoMock: false, failSim: {}, reasoning: {} },
  conn: { state: 'idle', provider: '', at: 0 },
}));

const g = () => useAi.getState();
const prov = (p: string, s: AiState = g()): Partial<ProviderInfo> => s.status.providers[toSrv(p)] || {};
const modeOf = (s: AiState): Mode => {
  const choice = toUi(s.settings.aiProvider || 'ollama');
  return s.settings.demoMock ? 'mock' : prov(choice, s).available ? choice : 'off';
};

export const ai = {
  choice: (): UiProvider => toUi(g().settings.aiProvider || 'ollama'),
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
  /** 고를 수 있는 추론 정도 단계. OpenAI 는 서버 설정(.env), RunPod-Ollama 는 연결 확인 때 진단·로드맵 모델이 알려 준 단계
   *  (규정 에이전트 모델은 늘 꺼서 고르지 않음). null 이면 아직 모름(연결 확인 전·실패), 빈 목록이면 이 모델은 고를 단계가 없음 */
  reasoningLevels: (p: UiProvider): string[] | null => (p === 'api' ? prov('api').reasoning?.levels || [] : (ollamaThink()?.levels ?? null)),
  /** 고르지 않았을 때 쓰는 값: 서버 기본값(.env) → (Ollama) 그 모델의 기본값. null 이면 모름 */
  reasoningDefault: (p: UiProvider): string | null => prov(p).reasoning?.default ?? (p === 'ollama' ? ollamaThink()?.default : null) ?? null,
  /** 직원이 고른 단계. null 이면 기본값을 따름 */
  reasoning: (p: UiProvider): string | null => g().settings.reasoning[toSrv(p)] ?? null,
  failSim: (): FailSim => ({ ...Object.fromEntries(SIM_KINDS.map((k) => [k, false])), ...(g().settings.failSim || {}) }),
};

/** RunPod-Ollama 진단·로드맵 모델의 추론 정도 단계(마지막 연결 확인 결과) */
function ollamaThink(): ThinkLevels | null {
  const c = g().conn;
  return (c.provider === 'ollama' && c.models?.find((m) => m.role === 'default')?.think) || null;
}

const LEVEL_LABEL: Record<string, string> = { off: '끔', on: '켬', none: '없음', minimal: '최소', low: '낮음', medium: '보통', high: '높음', xhigh: '매우 높음', max: '최대' };
/** 단계 이름 → 화면 글자. 모르는 이름(모델이 정한 이름)은 그대로 */
export const levelLabel = (level: string): string => LEVEL_LABEL[level] || level;

export const unavailableWhyText = (): string => ai.unavailableWhy(ai.choice());

/** 화면 구독용: 모드·고른 모델·연결 상태가 바뀌면 다시 그린다(값은 ai.* 로 읽는다) */
export const useAiMode = (): { mode: Mode; choice: UiProvider; demo: boolean; checked: boolean; conn: Conn } =>
  useAi(
    useShallow((s) => ({ mode: modeOf(s), choice: toUi(s.settings.aiProvider || 'ollama'), demo: !!s.settings.demoMock, checked: s.status.checked, conn: s.conn })),
  );

export const DOC_CHARS = 6000;
export const SIM_KINDS = ['goal', 'doc', 'quiz', 'diag', 'gen', 'sup', 'report', 'reg', 'rev'];

export async function checkStatus(): Promise<void> {
  try {
    const j = await aiApi.providers();
    useAi.setState({ status: { checked: true, server: true, docLibs: j.docLibs || {}, providers: Object.fromEntries(j.providers.map((p) => [p.id, p])) } });
  } catch {
    useAi.setState((s) => ({ status: { ...s.status, checked: true, server: false } }));
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
  useAi.setState((s) => ({ settings: { ...s.settings, aiProvider: toSrv(p) } }));
  await aiApi.setProvider(toSrv(p));
}

/** 모드별 추론 정도 저장(null 이면 기본값으로). 저장에 실패하면 화면 값을 되돌린다(서버 값과 어긋나지 않게) */
export async function setReasoning(p: UiProvider, level: string | null): Promise<void> {
  const prev = g().settings.reasoning;
  const next = { ...prev };
  if (level) next[toSrv(p)] = level;
  else delete next[toSrv(p)];
  useAi.setState((s) => ({ settings: { ...s.settings, reasoning: next } }));
  try {
    const r = await aiApi.setReasoning(toSrv(p), level);
    useAi.setState((s) => ({ settings: { ...s.settings, reasoning: r.reasoning || {} } }));
  } catch (err) {
    useAi.setState((s) => ({ settings: { ...s.settings, reasoning: prev } }));
    throw err;
  }
}

export async function setDemoMock(on: boolean): Promise<void> {
  useAi.setState((s) => ({ settings: { ...s.settings, demoMock: on } }));
  const r = await demoApi.settings({ demoMock: on });
  useAi.setState((s) => ({ settings: { ...s.settings, ...r } }));
}

export async function setFailSim(k: string, on: boolean): Promise<void> {
  useAi.setState((s) => ({ settings: { ...s.settings, failSim: { ...s.settings.failSim, [k]: on } } }));
  applySettings(await demoApi.settings({ failSim: { [k]: on } }));
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
  if (kind === 'docbig') return ['15MB 이하로 줄여 다시 골라 주세요.', '기획서 없이 목표만으로 진행해도 돼요.'];
  if (/^doc/.test(kind || '')) return ['DOCX·PPTX·HWPX·PDF·TXT 중 하나로 저장해 다시 골라 주세요.', '기획서 없이 목표만으로 진행해도 돼요.'];
  const other = ai.choice() === 'api' ? 'ollama' : 'api';
  if (kind === 'off')
    return ['서버 연결과 모델 설정을 확인해 주세요.', '자동 대체하지 않아요. 연결한 뒤 다시 시도해 주세요.'].concat(
      ai.available(other) ? [`좌측 ‘AI 모델’에서 ${PROV[other]}를 골라 볼 수도 있어요.`] : [],
    );
  if (kind === 'lost') return ['다시 시도하면 새로 만들어요.'];
  const t = [kind === 'format' ? '다시 시도하면 대부분 해결돼요.' : '잠시 뒤 다시 시도해 주세요.'];
  if (kind !== 'server' && !ai.demoMock() && ai.available(other)) t.push(`좌측 ‘AI 모델’에서 ${PROV[other]}를 골라 볼 수도 있어요.`);
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

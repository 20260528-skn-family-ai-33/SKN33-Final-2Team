import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/client';
import { demoApi } from '@/api/endpoints/account';
import type { UserSettings } from '@/api/types/account';
import { ai, applySettings, canClearHiddenDemoSettings, clearDemoSettings, setDemoMock, setFailSim, SIM_KINDS, useAi } from './ai';

const session = vi.hoisted(() => ({ seq: 0 }));
vi.mock('@/shared/state/session', () => ({ signInSeq: () => session.seq }));

const settings = (extra: Partial<UserSettings> = {}): UserSettings => ({
  aiProvider: 'openai', demoMock: false, failSim: {}, reasoning: { openai: 'low' }, ...extra,
});
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
};
const disabled = () => new ApiError(404, { code: 'NOT_FOUND', message: '요청한 기능을 찾을 수 없어요' });

beforeEach(() => {
  session.seq += 1;
  useAi.setState({
    settings: settings(),
    status: { checked: true, docLibs: {}, providers: {
      openai: { id: 'openai', label: 'OpenAI', available: true, reason: '', models: { default: 'test', roadmap: 'test', embed: 'test', vision: '' } },
    } },
  });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

describe('시연 도구가 없는 빌드에서 설정 해제', () => {
  it.each([
    ['off', true, true, false, true],
    ['off', true, false, true, true],
    ['off', true, false, false, false],
    ['on', true, true, true, false],
    ['off', false, true, true, false],
    ['on', false, true, true, false],
    ['off', undefined, true, true, false],
  ] as const)('화면 %s · 서버 %s · 가데이터 %s · 실패 시연 %s → 해제 버튼 %s', (build, server, mock, fail, visible) => {
    vi.stubEnv('VITE_DEMO_TOOLS', build);
    const state = useAi.getState();
    expect(canClearHiddenDemoSettings({ ...state, status: { ...state.status, demoMode: server },
      settings: settings({ demoMock: mock, failSim: { goal: fail } }) })).toBe(visible);
  });
  it('해제 실패 시 저장값을 유지하고 재시도 한 번으로 모든 실패 시연과 가데이터를 끈다', async () => {
    const previous = settings({ demoMock: true, failSim: { goal: true, doc: true } });
    applySettings(previous);
    const error = disabled();
    const save = vi.spyOn(demoApi, 'settings').mockRejectedValueOnce(error).mockResolvedValueOnce(settings());
    await expect(clearDemoSettings()).rejects.toBe(error);
    expect(useAi.getState().settings).toEqual(previous);
    expect(await clearDemoSettings()).toBe(true);
    expect(save).toHaveBeenLastCalledWith({ demoMock: false, failSim: Object.fromEntries(SIM_KINDS.map(k => [k, false])) });
    expect(useAi.getState().settings).toEqual(settings());
  });
});

describe('시연 설정은 서버에 저장된 뒤 표시한다', () => {
  it('가데이터 저장 응답 전에는 실제 모델 표시를 유지하고 성공 뒤에만 바꾼다', async () => {
    const request = deferred<UserSettings>();
    vi.spyOn(demoApi, 'settings').mockReturnValue(request.promise);
    const pending = setDemoMock(true);
    expect(ai.mode()).toBe('api');
    await Promise.resolve();
    expect(demoApi.settings).toHaveBeenCalledWith({ demoMock: true });
    request.resolve(settings({ demoMock: true }));
    expect(await pending).toBe(true);
    expect(ai.mode()).toBe('mock');
  });

  it.each([false, true])('404 실패 시 가데이터 기존값 %s와 모델 표시를 유지한다', async (initial) => {
    applySettings(settings({ demoMock: initial }));
    const error = disabled();
    vi.spyOn(demoApi, 'settings').mockRejectedValue(error);
    await expect(setDemoMock(!initial)).rejects.toBe(error);
    expect(ai.demoMock()).toBe(initial);
    expect(ai.mode()).toBe(initial ? 'mock' : 'api');
  });

  it('실패 시연 저장 실패 시 기존 항목을 보존하고 오류를 호출자에게 전달한다', async () => {
    const original = settings({ failSim: { doc: true } });
    applySettings(original);
    const error = disabled();
    vi.spyOn(demoApi, 'settings').mockRejectedValue(error);
    await expect(setFailSim('goal', true)).rejects.toBe(error);
    expect(useAi.getState().settings).toEqual(original);
  });

  it('저장 중 바뀐 AI 제공자와 추론값을 시연 API의 옛 응답으로 덮지 않는다', async () => {
    const request = deferred<UserSettings>();
    vi.spyOn(demoApi, 'settings').mockReturnValue(request.promise);
    const pending = setDemoMock(true);
    await Promise.resolve();
    useAi.setState((s) => ({ settings: { ...s.settings, aiProvider: 'ollama', reasoning: { ollama: 'high' } } }));
    request.resolve(settings({ demoMock: true }));
    await pending;
    expect(useAi.getState().settings).toEqual(settings({ demoMock: true, aiProvider: 'ollama', reasoning: { ollama: 'high' } }));
  });
});

describe('연속 저장과 로그인 전환', () => {
  it.each([
    [true, false, true],
    [false, true, false],
    [false, false, false],
  ])('켜기 성공=%s, 끄기 성공=%s이면 마지막 저장값 %s를 표시한다', async (firstOk, secondOk, finalValue) => {
    const first = deferred<UserSettings>();
    const second = deferred<UserSettings>();
    const save = vi.spyOn(demoApi, 'settings').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const enabling = setDemoMock(true).catch(() => false);
    const disabling = setDemoMock(false).catch(() => false);
    await Promise.resolve();
    expect(save).toHaveBeenCalledTimes(1);
    if (firstOk) first.resolve(settings({ demoMock: true }));
    else first.reject(disabled());
    await enabling;
    await Promise.resolve();
    expect(save).toHaveBeenCalledTimes(2);
    if (secondOk) second.resolve(settings({ demoMock: false }));
    else second.reject(disabled());
    await disabling;
    expect(ai.demoMock()).toBe(finalValue);
  });

  it('가데이터와 실패 시연을 함께 바꿔도 두 요청을 순서대로 저장한다', async () => {
    const first = deferred<UserSettings>();
    const second = deferred<UserSettings>();
    const save = vi.spyOn(demoApi, 'settings').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const mock = setDemoMock(true);
    const failure = setFailSim('goal', true);
    await Promise.resolve();
    expect(save).toHaveBeenCalledTimes(1);
    expect(useAi.getState().settings.failSim).toEqual({});
    first.resolve(settings({ demoMock: true }));
    await mock;
    await Promise.resolve();
    expect(save).toHaveBeenNthCalledWith(2, { failSim: { goal: true } });
    second.resolve(settings({ demoMock: true, failSim: { goal: true } }));
    expect(await failure).toBe(true);
    expect(useAi.getState().settings).toEqual(settings({ demoMock: true, failSim: { goal: true } }));
  });

  it.each([true, false])('재로그인 뒤 옛 요청 성공=%s와 대기 요청을 버리고 새 로그인 저장은 진행한다', async (succeeded) => {
    const old = deferred<UserSettings>();
    const save = vi.spyOn(demoApi, 'settings').mockReturnValueOnce(old.promise).mockResolvedValue(settings({ failSim: { doc: true } }));
    const inFlight = setDemoMock(true);
    const queued = setFailSim('goal', true);
    await Promise.resolve();
    session.seq += 1; // 같은 직원 재로그인도 별도 회차다.
    applySettings(settings());
    expect(await setFailSim('doc', true)).toBe(true);
    expect(save).toHaveBeenCalledTimes(2);
    if (succeeded) old.resolve(settings({ demoMock: true }));
    else old.reject(disabled());
    expect(await inFlight).toBe(false);
    expect(await queued).toBe(false);
    expect(save).toHaveBeenCalledTimes(2);
    expect(useAi.getState().settings).toEqual(settings({ failSim: { doc: true } }));
  });
});

/* 실패 원인 바꾸기: 서버 오류 본문·작업에 저장된 원인·네트워크 오류를 화면이 쓰는 한 모양(Cause)으로
   역할별 모델 이름: 진단·로드맵·규정 모델 고르기 (#33)
   추론 정도: 모드별 고를 수 있는 단계·기본값 순서·저장과 실패 때 되돌리기 · 규정 에이전트 모델은 고르지 않음 (#28) */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/client';
import { aiApi, type ProviderInfo } from '@/api/endpoints/account';
import type { ReasoningPicks } from '@/api/types/account';
import { ai, applySettings, cause, checkStatus, errText, levelLabel, setReasoning, useAi } from './ai';

const useOllama = (models: ProviderInfo['models']) =>
  useAi.setState({
    status: { checked: true, docLibs: {}, providers: { ollama: { id: 'ollama', label: 'RunPod-Ollama', available: true, reason: '', models } } },
    settings: { aiProvider: 'ollama', demoMock: false, failSim: {}, reasoning: {} },
  });

describe('서버 시연 허용 상태', () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([true, false, undefined])('서버 demoMode=%s를 받아 명시적으로 true일 때만 시연을 허용한다', async (demoMode) => {
    vi.spyOn(aiApi, 'providers').mockResolvedValue({ current: 'ollama', demoMode, providers: [], docLibs: {} });
    await checkStatus();
    expect(ai.demoAllowed()).toBe(demoMode === true);
  });

  it('조회 중과 조회 실패 뒤에는 이전 true를 남기지 않는다', async () => {
    useAi.setState((s) => ({ status: { ...s.status, demoMode: true } }));
    vi.spyOn(aiApi, 'providers').mockRejectedValue(new Error('network'));
    const pending = checkStatus();
    expect(ai.demoAllowed()).toBe(false);
    await pending;
    expect(ai.demoAllowed()).toBe(false);
    expect(useAi.getState().status.server).toBe(false);
  });

  it('새 조회가 off를 확인한 뒤 도착한 이전 on 응답은 시연을 다시 켜지 않는다', async () => {
    let finish!: (value: Awaited<ReturnType<typeof aiApi.providers>>) => void;
    const oldResponse = new Promise<Awaited<ReturnType<typeof aiApi.providers>>>((resolve) => { finish = resolve; });
    vi.spyOn(aiApi, 'providers').mockReturnValueOnce(oldResponse).mockResolvedValue({ current: 'ollama', demoMode: false, providers: [], docLibs: {} });
    const old = checkStatus();
    await checkStatus();
    finish({ current: 'ollama', demoMode: true, providers: [], docLibs: {} });
    await old;
    expect(ai.demoAllowed()).toBe(false);
  });
});

it('관리자 지정을 해제하면 다시 로그인하지 않아도 직원의 제공자와 추론 설정을 복원한다', async () => {
  useOllama({ default: 'team-model', roadmap: 'team-model', embed: '', vision: '' });
  const providers = vi.spyOn(aiApi, 'providers');
  try {
    providers.mockResolvedValueOnce({ current: 'openai', policy: 'openai', employeeReasoning: {}, providers: [], docLibs: {} });
    await checkStatus();
    applySettings({ aiProvider: 'ollama' });
    expect(ai.choice()).toBe('api');
    providers.mockResolvedValueOnce({ current: 'ollama', policy: 'employee', employeeReasoning: { openai: 'low' }, providers: [], docLibs: {} });
    await checkStatus();
    expect(ai.choice()).toBe('ollama');
    expect(ai.reasoning('api')).toBe('low');
  } finally {
    providers.mockRestore();
  }
});

describe('역할별 모델 이름', () => {
  it('규정 역할은 규정 모델을, 진단·로드맵은 각자의 모델을 쓴다', () => {
    useOllama({ default: 'ft-27b', roadmap: 'ft-27b', regulation: 'ft-4b', embed: 'text-embedding-3-small', vision: '' });
    expect(ai.modelName('regulation')).toBe('ft-4b');
    expect(ai.modelName('default')).toBe('ft-27b');
    expect(ai.modelName('roadmap')).toBe('ft-27b');
  });

  it('규정 모델이 없는 옛 응답이면 진단 모델을 쓴다', () => {
    useOllama({ default: 'qwen3.8:27b', roadmap: 'qwen3.8:27b', embed: 'text-embedding-3-small', vision: '' });
    expect(ai.modelName('regulation')).toBe('qwen3.8:27b');
  });

  it('이미지 읽기 모델이 비어 있으면 다른 모델로 대신하지 않는다', () => {
    useOllama({ default: 'ft-27b', roadmap: 'ft-27b', regulation: 'ft-4b', embed: '', vision: '' });
    expect(ai.modelName('vision')).toBe('');
  });
});

describe('cause', () => {
  it('서버 오류 본문의 사용자 문구·원인·조치를 그대로 쓴다', () => {
    const c = cause(new ApiError(409, { code: 'STALE_EDIT', kind: 'other', message: '확인한 뒤 데이터가 바뀌었어요', hint: '저장을 다시 눌러 주세요', retryable: false }));
    expect(c).toMatchObject({ kind: 'other', user: '확인한 뒤 데이터가 바뀌었어요', hint: '저장을 다시 눌러 주세요', code: 'STALE_EDIT', retryable: false });
  });

  it('로그인이 끊긴 오류는 서버 문제로 분류한다', () => {
    expect(cause(new ApiError(401, { code: 'AUTH_REQUIRED', message: '로그인이 필요해요' })).kind).toBe('server');
  });

  it('직원 구분을 확인할 수 없으면 원인과 인사 담당 부서 문의를 표시한다', () => {
    const error = new ApiError(502, {
      code: 'EMPLOYEE_GROUP_UNAVAILABLE', kind: 'employee_group',
      message: '로그인한 직원의 직원 구분을 확인할 수 없어요', retryable: false,
    });
    expect(errText(cause(error))).toBe('로그인한 직원의 직원 구분을 확인할 수 없어요. 인사 담당 부서에 직원 구분 등록 여부를 확인해 주세요.');
  });

  it('작업에 저장된 원인(kind·text)은 그대로 살린다', () => {
    const c = cause({ kind: 'timeout', text: '응답이 늦어요', hint: '잠시 뒤 다시', raw: 'ReadTimeout' });
    expect(c).toMatchObject({ kind: 'timeout', text: '응답이 늦어요', raw: 'ReadTimeout' });
    expect(c.user).toBeTruthy();
  });

  it('네트워크 오류처럼 모르는 오류는 서버 연결 문제로 보고 원문을 남긴다', () => {
    const c = cause(new TypeError('Failed to fetch'));
    expect(c).toMatchObject({ kind: 'server', raw: 'Failed to fetch' });
  });
});

describe('추론 정도', () => {
  const info = (id: 'ollama' | 'openai', reasoning: ProviderInfo['reasoning']): ProviderInfo => ({
    id,
    label: id,
    available: true,
    reason: '',
    models: { default: 'm', roadmap: 'm', embed: '', vision: '' },
    reasoning,
  });
  /** mine: 직원이 고른 값 · ollama/openai: 서버가 알려 준 추론 정도 */
  const setup = (o: {
    mine?: ReasoningPicks;
    ollama?: ProviderInfo['reasoning'];
    openai?: ProviderInfo['reasoning'];
  }) =>
    useAi.setState({
      settings: { aiProvider: 'ollama', demoMock: false, failSim: {}, reasoning: o.mine || {} },
      status: {
        checked: true,
        docLibs: {},
        providers: { ollama: info('ollama', o.ollama ?? { levels: [], default: 'off' }), openai: info('openai', o.openai) },
      },
      conn: { state: 'idle', provider: '', at: 0 },
    });

  afterEach(() => vi.restoreAllMocks());

  it('OpenAI 단계는 서버 설정(.env)에서, 없으면 고를 단계 없음', () => {
    setup({ openai: { levels: ['none', 'low', 'medium', 'high', 'xhigh'], default: null } });
    expect(ai.reasoningLevels('api')).toEqual(['none', 'low', 'medium', 'high', 'xhigh']);
    setup({});
    expect(ai.reasoningLevels('api')).toEqual([]);
  });

  it('RunPod-Ollama 는 고를 단계가 없고 기본값·적용 값 모두 추론 없음(off)이다', () => {
    // 예전 서버 응답(단계 null·기본값 없음)이나 예전에 저장한 직원 값이 있어도 화면은 늘 끔으로 본다
    for (const o of [{}, { ollama: { levels: null, default: null } }, { mine: { ollama: 'xhigh' } }]) {
      setup(o);
      expect(ai.reasoningLevels('ollama')).toEqual([]);
      expect(ai.reasoningDefault('ollama')).toBe('off');
      expect(ai.reasoning('ollama')).toBe('off');
    }
  });

  it('OpenAI 기본값은 서버 설정(.env)이 앞서고, 없으면 모름(null)', () => {
    setup({ openai: { levels: ['low', 'medium'], default: 'low' } });
    expect(ai.reasoningDefault('api')).toBe('low');
    setup({ openai: { levels: ['low', 'medium'], default: null } });
    expect(ai.reasoningDefault('api')).toBeNull();
  });

  it('OpenAI 는 .env 기본값이 없으면 서버가 아는 모델 기본값(gpt-6-luna: medium)을 보여 준다', () => {
    setup({ openai: { levels: ['none', 'low', 'medium', 'high', 'xhigh'], default: null, modelDefault: 'medium' } });
    expect(ai.reasoningDefault('api')).toBe('medium');
    setup({ openai: { levels: ['none', 'low', 'medium', 'high', 'xhigh'], default: 'high', modelDefault: 'medium' } });
    expect(ai.reasoningDefault('api')).toBe('high');
  });

  it('직원이 고른 값은 모드마다 따로 읽는다(화면 api = 서버 openai)', () => {
    setup({ mine: { openai: 'high' } });
    expect(ai.reasoning('api')).toBe('high');
    setup({});
    expect(ai.reasoning('api')).toBeNull();
  });

  it('설정 응답에 추론 정도가 없으면 고른 값을 지우지 않는다', () => {
    setup({ mine: { ollama: 'xhigh' } });
    applySettings({ demoMock: true, failSim: {} });
    expect(useAi.getState().settings.reasoning).toEqual({ ollama: 'xhigh' });
    applySettings({ reasoning: {} });
    expect(useAi.getState().settings.reasoning).toEqual({});
  });

  it('저장하면 서버가 돌려준 값을 쓰고, 기본값(null)으로 고르면 그 모드만 지운다', async () => {
    setup({ mine: { ollama: 'xhigh' } });
    const put = vi.spyOn(aiApi, 'setReasoning').mockResolvedValue({ reasoning: { ollama: 'xhigh', openai: 'low' } });
    await setReasoning('api', 'low');
    expect(put).toHaveBeenCalledWith('openai', 'low');
    expect(ai.reasoning('api')).toBe('low');
    put.mockResolvedValue({ reasoning: { openai: 'low' } });
    await setReasoning('ollama', null);
    expect(put).toHaveBeenLastCalledWith('ollama', null);
    expect(useAi.getState().settings.reasoning).toEqual({ openai: 'low' });
  });

  it('저장에 실패하면 화면 값을 되돌린다', async () => {
    setup({ mine: { openai: 'off' } });
    vi.spyOn(aiApi, 'setReasoning').mockRejectedValue(new ApiError(422, { code: 'BAD_REASONING', message: '추론 정도가 아니에요' }));
    await expect(setReasoning('api', 'xhigh')).rejects.toBeInstanceOf(ApiError);
    expect(useAi.getState().settings.reasoning).toEqual({ openai: 'off' });
  });

  /** 저장 요청을 붙잡아 두고 순서를 정해 끝낸다(늦은 응답·실패 재현) */
  const holdSaves = () => {
    const calls: { level: string | null; done: (r: { reasoning: ReasoningPicks }) => void; fail: (e: unknown) => void }[] = [];
    vi.spyOn(aiApi, 'setReasoning').mockImplementation(
      (_p, level) => new Promise((done, fail) => calls.push({ level, done, fail })),
    );
    return calls;
  };
  const tick = () => new Promise((r) => setTimeout(r, 0));

  it('빠르게 바꾸면 저장은 차례로 보내고, 앞 요청의 늦은 응답이 마지막 선택을 덮지 않는다', async () => {
    setup({});
    const calls = holdSaves();
    const first = setReasoning('api', 'low');
    const second = setReasoning('api', 'xhigh');
    await tick();
    expect(calls.map((c) => c.level)).toEqual(['low']);
    calls[0].done({ reasoning: { openai: 'low' } });
    await first;
    expect(ai.reasoning('api')).toBe('xhigh');
    await tick();
    expect(calls.map((c) => c.level)).toEqual(['low', 'xhigh']);
    calls[1].done({ reasoning: { openai: 'xhigh' } });
    await second;
    expect(ai.reasoning('api')).toBe('xhigh');
  });

  it('앞 요청이 실패해도 마지막 선택을 되돌리지 않는다', async () => {
    setup({ mine: { openai: 'off' } });
    const calls = holdSaves();
    const first = setReasoning('api', 'low');
    const second = setReasoning('api', 'xhigh');
    await tick();
    calls[0].fail(new ApiError(500, { code: 'SERVER', message: '저장하지 못했어요' }));
    await expect(first).rejects.toBeInstanceOf(ApiError);
    expect(ai.reasoning('api')).toBe('xhigh');
    await tick();
    calls[1].done({ reasoning: { openai: 'xhigh' } });
    await second;
    expect(ai.reasoning('api')).toBe('xhigh');
  });

  it('마지막 요청이 실패하면 서버에 마지막으로 저장된 값으로 돌린다', async () => {
    setup({ mine: { openai: 'off' } });
    const calls = holdSaves();
    const first = setReasoning('api', 'low');
    const second = setReasoning('api', 'xhigh');
    await tick();
    calls[0].done({ reasoning: { openai: 'low' } });
    await first;
    await tick();
    calls[1].fail(new ApiError(500, { code: 'SERVER', message: '저장하지 못했어요' }));
    await expect(second).rejects.toBeInstanceOf(ApiError);
    expect(useAi.getState().settings.reasoning).toEqual({ openai: 'low' });
  });

  it('단계 이름은 아는 것만 한글로, 모델이 정한 이름은 그대로 보인다', () => {
    expect(levelLabel('xhigh')).toBe('매우 높음');
    expect(levelLabel('off')).toBe('끔');
    expect(levelLabel('turbo')).toBe('turbo');
  });
});

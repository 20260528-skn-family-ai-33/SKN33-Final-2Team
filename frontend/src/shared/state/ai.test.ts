/* 실패 원인 바꾸기: 서버 오류 본문·작업에 저장된 원인·네트워크 오류를 화면이 쓰는 한 모양(Cause)으로
   역할별 모델 이름: 진단·로드맵·규정 모델 고르기 (#33)
   추론 정도: 모드별 고를 수 있는 단계·기본값 순서·저장과 실패 때 되돌리기 · 규정 에이전트 모델은 고르지 않음 (#28) */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/client';
import { aiApi, type ProviderInfo, type ThinkLevels } from '@/api/endpoints/account';
import type { ReasoningPicks } from '@/api/types/account';
import { ai, applySettings, cause, levelLabel, setReasoning, useAi } from './ai';

const useOllama = (models: ProviderInfo['models']) =>
  useAi.setState({
    status: { checked: true, docLibs: {}, providers: { ollama: { id: 'ollama', label: 'RunPod-Ollama', available: true, reason: '', models } } },
    settings: { aiProvider: 'ollama', demoMock: false, failSim: {}, reasoning: {} },
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
  /** 실제 Pod 에서 본 팀 진단·로드맵 모델(27b)의 단계(RunPod 연결 절차 · 2026-10-29) */
  const POD27: ThinkLevels = { levels: ['off', 'low', 'medium', 'xhigh'], default: null };
  /** mine: 직원이 고른 값 · ollamaDefault/openai: 서버 설정(.env) · think: 연결 확인 때 받은 모델별 단계 */
  const setup = (o: {
    mine?: ReasoningPicks;
    ollamaDefault?: string | null;
    openai?: ProviderInfo['reasoning'];
    think?: Partial<Record<'default' | 'regulation', ThinkLevels | null>>;
    connOf?: string;
  }) =>
    useAi.setState({
      settings: { aiProvider: 'ollama', demoMock: false, failSim: {}, reasoning: o.mine || {} },
      status: {
        checked: true,
        docLibs: {},
        providers: { ollama: info('ollama', { levels: null, default: o.ollamaDefault ?? null }), openai: info('openai', o.openai) },
      },
      conn: o.think
        ? {
            state: 'ok',
            provider: o.connOf || 'ollama',
            at: 1,
            models: Object.entries(o.think).map(([role, think]) => ({ role, name: role, installed: true, loaded: true, think })),
          }
        : { state: 'idle', provider: '', at: 0 },
    });

  afterEach(() => vi.restoreAllMocks());

  it('OpenAI 단계는 서버 설정(.env)에서, 없으면 고를 단계 없음', () => {
    setup({ openai: { levels: ['none', 'low', 'medium', 'high', 'xhigh'], default: null } });
    expect(ai.reasoningLevels('api')).toEqual(['none', 'low', 'medium', 'high', 'xhigh']);
    setup({});
    expect(ai.reasoningLevels('api')).toEqual([]);
  });

  it('RunPod-Ollama 는 진단·로드맵 모델이 알려 준 단계만 쓰고, 규정 모델 단계는 쓰지 않는다(규정 에이전트는 늘 끔)', () => {
    setup({ think: { default: POD27, regulation: { levels: ['off', 'on'], default: null } } });
    expect(ai.reasoningLevels('ollama')).toEqual(['off', 'low', 'medium', 'xhigh']);
    setup({ think: { regulation: { levels: ['off', 'on'], default: null } } });
    expect(ai.reasoningLevels('ollama')).toBeNull();
  });

  it('연결 확인 전·실패이면 단계를 모른다(null)', () => {
    setup({});
    expect(ai.reasoningLevels('ollama')).toBeNull();
    setup({ think: { default: POD27 }, connOf: 'api' });
    expect(ai.reasoningLevels('ollama')).toBeNull();
    setup({ think: { default: null } });
    expect(ai.reasoningLevels('ollama')).toBeNull();
  });

  it('기본값은 서버 설정(.env)이 앞서고, 없으면 그 모델의 기본값', () => {
    setup({ ollamaDefault: 'off', think: { default: { levels: ['off', 'on'], default: 'on' } } });
    expect(ai.reasoningDefault('ollama')).toBe('off');
    setup({ think: { default: { levels: ['off', 'on'], default: 'on' } } });
    expect(ai.reasoningDefault('ollama')).toBe('on');
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
    expect(ai.reasoning('ollama')).toBeNull();
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
    setup({ mine: { ollama: 'off' } });
    vi.spyOn(aiApi, 'setReasoning').mockRejectedValue(new ApiError(422, { code: 'BAD_REASONING', message: '추론 정도가 아니에요' }));
    await expect(setReasoning('ollama', 'xhigh')).rejects.toBeInstanceOf(ApiError);
    expect(useAi.getState().settings.reasoning).toEqual({ ollama: 'off' });
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
    const first = setReasoning('ollama', 'low');
    const second = setReasoning('ollama', 'xhigh');
    await tick();
    expect(calls.map((c) => c.level)).toEqual(['low']);
    calls[0].done({ reasoning: { ollama: 'low' } });
    await first;
    expect(ai.reasoning('ollama')).toBe('xhigh');
    await tick();
    expect(calls.map((c) => c.level)).toEqual(['low', 'xhigh']);
    calls[1].done({ reasoning: { ollama: 'xhigh' } });
    await second;
    expect(ai.reasoning('ollama')).toBe('xhigh');
  });

  it('앞 요청이 실패해도 마지막 선택을 되돌리지 않는다', async () => {
    setup({ mine: { ollama: 'off' } });
    const calls = holdSaves();
    const first = setReasoning('ollama', 'low');
    const second = setReasoning('ollama', 'xhigh');
    await tick();
    calls[0].fail(new ApiError(500, { code: 'SERVER', message: '저장하지 못했어요' }));
    await expect(first).rejects.toBeInstanceOf(ApiError);
    expect(ai.reasoning('ollama')).toBe('xhigh');
    await tick();
    calls[1].done({ reasoning: { ollama: 'xhigh' } });
    await second;
    expect(ai.reasoning('ollama')).toBe('xhigh');
  });

  it('마지막 요청이 실패하면 서버에 마지막으로 저장된 값으로 돌린다', async () => {
    setup({ mine: { ollama: 'off' } });
    const calls = holdSaves();
    const first = setReasoning('ollama', 'low');
    const second = setReasoning('ollama', 'xhigh');
    await tick();
    calls[0].done({ reasoning: { ollama: 'low' } });
    await first;
    await tick();
    calls[1].fail(new ApiError(500, { code: 'SERVER', message: '저장하지 못했어요' }));
    await expect(second).rejects.toBeInstanceOf(ApiError);
    expect(useAi.getState().settings.reasoning).toEqual({ ollama: 'low' });
  });

  it('단계 이름은 아는 것만 한글로, 모델이 정한 이름은 그대로 보인다', () => {
    expect(levelLabel('xhigh')).toBe('매우 높음');
    expect(levelLabel('off')).toBe('끔');
    expect(levelLabel('turbo')).toBe('turbo');
  });
});

/* 실패 원인 바꾸기: 서버 오류 본문·작업에 저장된 원인·네트워크 오류를 화면이 쓰는 한 모양(Cause)으로
   역할별 모델 이름: 진단·로드맵·규정 모델 고르기 (#33) */
import { describe, expect, it } from 'vitest';
import { ApiError } from '@/api/client';
import type { ProviderInfo } from '@/api/endpoints/account';
import { ai, cause, useAi } from './ai';

const useOllama = (models: ProviderInfo['models']) =>
  useAi.setState({
    status: { checked: true, docLibs: {}, providers: { ollama: { id: 'ollama', label: 'RunPod-Ollama', available: true, reason: '', models } } },
    settings: { aiProvider: 'ollama', demoMock: false, failSim: {} },
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

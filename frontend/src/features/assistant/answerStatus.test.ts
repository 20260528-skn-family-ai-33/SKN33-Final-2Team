import { describe, expect, it } from 'vitest';
import type { AssistantAnswer, EvidenceStatus } from '@/api/endpoints/assistant';
import { answerStatus } from './answerStatus';

const makeAnswer = (value: Partial<AssistantAnswer>) => ({ kind: 'general', level: 'general', ...value }) as AssistantAnswer;

describe('답변 근거 상태와 제공 금지 거절', () => {
  const states: [EvidenceStatus, string, string][] = [
    ['found', '근거 확인', 'ok'],
    ['partial', '근거 확인 불가', 'warn'],
    ['not_found', '근거 확인 불가', 'warn'],
    ['refused', '답변 불가', 'fail'],
  ];
  for (const [status, label, style] of states) {
    it(`사내 생활 DB: ${status}`, () => {
      expect(answerStatus(makeAnswer({ topic: 'life', evidenceStatus: status, knowledgeSources: [] }))).toEqual([`사내 생활 ${label}`, style]);
    });
  }
  it('질문의 일부만 답했어도 인용이 있으면 근거 확인으로 표시한다', () => {
    expect(answerStatus(makeAnswer({ kind: 'regulation', evidenceStatus: 'partial', basis: ['edu24'] })))
      .toEqual(['규정 근거 확인', 'ok']);
    for (const topic of ['company', 'life'] as const) {
      const prefix = topic === 'company' ? '회사' : '사내 생활';
      expect(answerStatus(makeAnswer({ topic, evidenceStatus: 'partial', knowledgeSources: [{} as never] })))
        .toEqual([`${prefix} 근거 확인`, 'ok']);
    }
  });
  for (const topic of ['regulation', 'company'] as const) {
    for (const [status, label, style] of states) {
      it(`${topic}: ${status}`, () => {
        expect(answerStatus(makeAnswer({ topic, evidenceStatus: status }))).toEqual([`${topic === 'regulation' ? '규정' : '회사'} ${label}`, style]);
      });
    }
  }
  it('사내 생활은 안내와 제공 금지 거절을 구분한다', () => {
    expect(answerStatus(makeAnswer({ topic: 'life', evidenceStatus: 'found' }))[0]).toBe('사내 생활 안내');
    expect(answerStatus(makeAnswer({ topic: 'life', evidenceStatus: 'refused' }))).toEqual(['사내 생활 답변 불가', 'fail']);
    expect(answerStatus(makeAnswer({ topic: 'life', evidenceStatus: 'not_found' }))[0]).toBe('사내 생활 안내');
  });
  it('이전 규정 대화와 가데이터도 유지한다', () => {
    expect(answerStatus(makeAnswer({ kind: 'regulation', level: 'ok' }))[0]).toBe('규정 근거 확인');
    expect(answerStatus(makeAnswer({ kind: 'regulation', level: 'scope' }))[0]).toBe('규정 근거 확인 불가');
  });
  it('가데이터의 이전 세부 주제는 규정 답변을 회사 답변으로 바꾸지 않는다', () => {
    for (const topic of ['edu', 'support', 'travel', 'hours', 'eval', 'promo']) {
      const answer = makeAnswer({ kind: 'regulation', level: 'ok' });
      Object.assign(answer, { topic });
      expect(answerStatus(answer)[0]).toBe('규정 근거 확인');
    }
  });
  it('이전 회사 답변의 유효한 인용을 근거 없음으로 표시하지 않는다', () => {
    expect(answerStatus(makeAnswer({ knowledgeSources: [{} as never] }))[0]).toBe('회사 근거 확인');
    expect(answerStatus(makeAnswer({ knowledgeSources: [] }))[0]).toBe('회사 근거 확인 불가');
  });
});

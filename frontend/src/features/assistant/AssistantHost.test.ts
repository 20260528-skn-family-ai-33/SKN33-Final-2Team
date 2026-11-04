import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { AssistantAnswer } from '@/api/endpoints/assistant';
import { RegCard } from './AssistantHost';

const makeAnswer = (value: Partial<AssistantAnswer>): AssistantAnswer => ({
  kind: 'general', level: 'general', source: 'intranet', topic: 'life', summary: '',
  basis: [], intranet: [], question: '', options: [], ...value,
});

describe('사내 생활 DB 근거 카드', () => {
  it('시연 답변을 별도 라벨로 표시한다', () => {
    const a = makeAnswer({ summary: '시연용 통근버스 안내예요.' });
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a, demo: true })));
    expect(html).toContain('시연용 가데이터');
    expect(html).toContain(a.summary);
    expect(html).not.toContain('근거 확인');
  });

  it('DB 답변·출처·가상 여부와 자료 제약을 표시한다', () => {
    const answer = makeAnswer({
      kind: 'general', level: 'general', source: 'intranet', topic: 'life', evidenceStatus: 'found',
      summary: '식당 위치는 생활 안내 문서에서 확인해요.', intranet: [],
      knowledgeSources: [{ chunkId: 'life-1', documentId: 'guide', documentTitle: '교육원 생활 안내', location: '안내 2절',
        sourceUrl: null, asOf: null, textSha256: 'a'.repeat(64), sourceFileSha256: null, textTruncated: false,
        isVirtual: true, sourceLimits: '시연용 가상 자료', excerpt: '식당 위치를 확인하는 메뉴 안내' }],
    });
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a: answer })));
    for (const text of ['식당 위치는 생활 안내', '근거 보기', '교육원 생활 안내', '가상 안내 자료',
      '시연용 가상 자료', '식당 위치를 확인하는 메뉴 안내']) expect(html).toContain(text);
    expect(html).not.toContain('맞는 메뉴를 찾지 못했어요');
  });

  it('DB 근거가 없으면 빈 메뉴 대신 자료 부족을 알린다', () => {
    const answer = makeAnswer({ evidenceStatus: 'not_found', summary: '검색 자료에서 확인할 수 없어요.', knowledgeSources: [] });
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a: answer })));
    expect(html).toContain('등록된 사내 생활 자료에서 답변 근거를 확인하지 못했어요');
    expect(html).not.toContain('<summary>');
  });

  it('답변 카드에 ML 분류와 LLM 근거 상태를 나란히 표시한다', () => {
    const a = makeAnswer({ evidenceStatus: 'partial', knowledgeSources: [] });
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a, mlLabel: '사내 생활안내' })));
    expect(html).toContain('title="ML 질문 분류">사내 생활안내</span>');
    expect(html).toContain('title="LLM 근거 상태">근거 일부 확인</span>');
  });

  it('회사 정보도 근거 보기에서 DB 원문과 위치를 표시한다', () => {
    const a = makeAnswer({ source: 'work', topic: 'company', evidenceStatus: 'found',
      summary: '수자원 관리 업무를 해요.', knowledgeSources: [{ chunkId: 'company', documentId: 'report',
        documentTitle: '회사 소개', sourceUrl: null, location: 'PDF 3쪽', asOf: '2025년 자료',
        isVirtual: false, sourceLimits: null, textSha256: 'a'.repeat(64), sourceFileSha256: null,
        textTruncated: false, excerpt: '수자원 관리 업무를 수행한다.' }] });
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a, mlLabel: '수자원공사 정보' })));
    for (const text of ['근거 보기', '회사 소개', 'PDF 3쪽', '2025년 자료', '수자원 관리 업무를 수행한다.']) expect(html).toContain(text);
  });

  it('범위 밖과 제공 금지 거절은 단일 결과 라벨로 표시한다', () => {
    for (const a of [makeAnswer({ kind: 'out' }), makeAnswer({ evidenceStatus: 'refused', knowledgeSources: [] })]) {
      const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a, mlLabel: '범위 밖' })));
      expect(html).not.toContain('title="ML 질문 분류"');
      expect(html).not.toContain('title="LLM 근거 상태"');
      expect(html).toContain(a.kind === 'out' ? '범위 밖' : '사내 생활 답변 불가');
    }
  });
});

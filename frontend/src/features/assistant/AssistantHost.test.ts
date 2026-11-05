import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { AssistantAnswer } from '@/api/endpoints/assistant';
import { useCatalog } from '@/shared/state/catalog';
import { RegCard } from './AssistantHost';

const makeAnswer = (value: Partial<AssistantAnswer>): AssistantAnswer => ({
  kind: 'general', level: 'general', source: 'intranet', topic: 'life', summary: '',
  basis: [], intranet: [], question: '', options: [], ...value,
});

describe('사내 생활 DB 근거 카드', () => {
  it('규정 답변의 적용 조건은 본문에, 인용과 원문은 접힌 근거 보기에 표시한다', () => {
    const { articles, regs } = useCatalog.getState();
    useCatalog.setState({
      articles: { ...articles, edu: { id: 'edu', reg: 'dev', no: '제7조 제2항', title: '학습시간', chapter: '',
        page: 2, text: '세부적인 인정기준 및 절차는 따로 정한다.', type: 'paragraph', node: '', path: '', group: '일반직', overseas: false } },
      regs: { ...regs, dev: { key: 'dev', name: '인재개발규정', rev: '22차', effective: '', overseas: false } },
    });
    try {
      const a = makeAnswer({ kind: 'regulation', topic: 'regulation', level: 'unclear', evidenceStatus: 'partial', basis: ['edu'],
        summary: '개인학습도 학습시간에 포함돼요 (「인재개발규정」 제7조 제2항). 세부 기준(승인 절차 포함)은 따로 확인해 주세요.\n\n출처: 인재개발규정 제7조 제2항' });
      const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a })));
      const [summary, details] = html.split('<details>');
      expect(summary).toContain('>근거 확인</span>');
      expect(summary).toContain('개인학습도 학습시간에 포함돼요. 세부 기준(승인 절차 포함)은 따로 확인해 주세요.');
      expect(summary).toContain('아래 ‘근거 보기’에서 확인해 주세요.');
      expect(summary).not.toContain('인재개발규정');
      expect(details).toContain('제7조 제2항');
      expect(details).toContain('세부적인 인정기준 및 절차는 따로 정한다.');
    } finally {
      useCatalog.setState({ articles, regs });
    }
  });

  it('시연 답변을 별도 라벨로 표시한다', () => {
    const a = makeAnswer({ summary: '시연용 통근버스 안내예요.' });
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a, demo: true })));
    expect(html).toContain('시연용 가데이터');
    expect(html).toContain(a.summary);
    expect(html).not.toContain('근거 확인');
  });

  it('DB 답변·출처·가상 여부와 자료 제약을 표시한다', () => {
    const answer = makeAnswer({
      kind: 'general', level: 'general', source: 'intranet', topic: 'life', evidenceStatus: 'partial',
      summary: '식당 위치는 생활 안내 문서에서 확인해요.', intranet: [],
      knowledgeSources: [{ chunkId: 'life-1', documentId: 'guide', documentTitle: '교육원 생활 안내', location: '안내 2절',
        sourceUrl: null, asOf: null, textSha256: 'a'.repeat(64), sourceFileSha256: null, textTruncated: false,
        isVirtual: true, sourceLimits: '시연용 가상 자료', excerpt: '식당 위치를 확인하는 메뉴 안내' }],
    });
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a: answer, mlLabel: '사내 생활안내' })));
    for (const text of ['식당 위치는 생활 안내', '근거 보기', '교육원 생활 안내', '가상 안내 자료',
      '시연용 가상 자료', '식당 위치를 확인하는 메뉴 안내']) expect(html).toContain(text);
    expect(html).not.toContain('맞는 메뉴를 찾지 못했어요');
    expect(html).toContain('title="LLM 근거 상태">근거 확인</span>');
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
    expect(html).toContain('title="LLM 근거 상태">근거 확인 불가</span>');
  });

  it('회사 정보도 근거 보기에서 DB 원문과 위치를 표시한다', () => {
    const a = makeAnswer({ source: 'work', topic: 'company', evidenceStatus: 'found',
      summary: '수자원 관리 업무를 해요.\n\n출처: 회사 소개 · PDF 3쪽', knowledgeSources: [{ chunkId: 'company', documentId: 'report',
        documentTitle: '회사 소개', sourceUrl: null, location: 'PDF 3쪽', asOf: '2025년 자료',
        isVirtual: false, sourceLimits: null, textSha256: 'a'.repeat(64), sourceFileSha256: null,
        textTruncated: false, excerpt: '수자원 관리 업무를 수행한다.' }] });
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a, mlLabel: '수자원공사 정보' })));
    expect(html.split('<details>')[0]).not.toContain('회사 소개');
    for (const text of ['근거 보기', '회사 소개', 'PDF 3쪽', '2025년 자료', '수자원 관리 업무를 수행한다.']) expect(html).toContain(text);
  });

  it('범위 밖과 제공 금지 거절은 단일 결과 라벨로 표시한다', () => {
    for (const a of [makeAnswer({ kind: 'out' }), makeAnswer({ evidenceStatus: 'refused', knowledgeSources: [] })]) {
      const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(RegCard, { a, mlLabel: '범위 밖' })));
      expect(html).not.toContain('title="ML 질문 분류"');
      expect(html).not.toContain('title="LLM 근거 상태"');
      expect(html).toContain('>답변 불가</span>');
    }
  });
});

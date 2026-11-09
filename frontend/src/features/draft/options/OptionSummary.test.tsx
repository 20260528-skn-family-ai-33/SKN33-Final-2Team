import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { OptionSummary } from './OptionSummary';

it('기존 Crash 저장값을 유지하면서 요약에서는 전용 핵심 결과물 UI를 표시하지 않는다', () => {
  const saved = { coreOutcome: 'API 구현', coreCriteria: ['응답 검증'], followUpScope: ['추가 학습'] };
  const before = structuredClone(saved);
  const html = renderToStaticMarkup(createElement(OptionSummary, {
    id: 'crash-summary', reason: '빠른 실습', pros: ['실습 중심'], expanded: true,
    ...saved,
  }));
  expect(html).toContain('추천 이유');
  expect(html).not.toContain('핵심 결과물');
  expect(html).not.toContain('후속 학습');
  expect(saved).toEqual(before);
});

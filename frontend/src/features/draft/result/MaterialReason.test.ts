import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { MaterialReason } from './MaterialReason';

const fallback = '프로젝트에 맞는 강좌를 찾지 못했어요.';
const detail = '후보의 커리큘럼을 확인했어요.';

it.each([
  ['no_candidates', '추천에 사용할 강좌 후보가 없어요.'],
  ['insufficient_evidence', '강좌 후보의 학습 내용을 확인할 근거가 부족해요.'],
  ['stack_mismatch', '강좌 후보가 다루는 기술이 프로젝트에서 쓰는 기술과 달라요.'],
  ['scope_gap', '강좌 후보가 필요한 학습 범위를 충분히 다루지 않아요.'],
] as const)('빈 강좌 목록에서 %s의 구체적인 사유를 보여 준다', (reason, summary) => {
  const markup = renderToStaticMarkup(createElement(MaterialReason, { kind: '강좌', hasOptions: false, diagnostic: { reason, detail }, fallback }));
  expect(markup).toContain(summary);
  expect(markup).toContain(detail);
  expect(markup).not.toContain(fallback);
});

it.each([
  ['no_candidates', '추천에 사용할 도서 후보가 없어요.'],
  ['insufficient_evidence', '도서 후보의 학습 내용을 확인할 근거가 부족해요.'],
  ['scope_gap', '도서 후보가 필요한 학습 범위를 충분히 다루지 않아요.'],
] as const)('최종 도서가 0권일 때 %s의 구체적인 사유를 보여 준다', (reason, summary) => {
  const markup = renderToStaticMarkup(createElement(MaterialReason, { kind: '도서', hasOptions: false, diagnostic: { reason, detail }, fallback }));
  expect(markup).toContain(summary);
  expect(markup).toContain(detail);
});

it('강좌 선택지가 있으면 더 긴 강좌의 추천 이유와 일부 후보의 범위 부족을 표시한다', () => {
  const render = (reason: 'longer_for_coverage' | 'scope_gap') =>
    renderToStaticMarkup(createElement(MaterialReason, { kind: '강좌', hasOptions: true, diagnostic: { reason, detail }, fallback }));
  expect(render('longer_for_coverage')).toContain('필요한 학습 범위를 채우기 위해 더 긴 강좌를 추천했어요.');
  expect(render('scope_gap')).toContain('일부 강좌 후보가 필요한 학습 범위를 충분히 다루지 않아요.');
});

it('기존 응답의 안내를 유지하고 표시할 강좌가 없으면 긴 강좌 추천을 단정하지 않는다', () => {
  expect(renderToStaticMarkup(createElement(MaterialReason, { kind: '강좌', hasOptions: false, fallback }))).toBe(`<p class="small muted">${fallback}</p>`);
  expect(renderToStaticMarkup(createElement(MaterialReason, { kind: '도서', hasOptions: true, fallback }))).toBe('');
  expect(renderToStaticMarkup(createElement(MaterialReason, { kind: '강좌', hasOptions: false, diagnostic: { reason: 'longer_for_coverage', detail }, fallback }))).toContain(fallback);
});

it('후보 제목이 들어간 표시 문구를 진단 원문보다 우선한다', () => {
  const diagnostic = { reason: 'scope_gap', detail: 'S1-C1에 실행 계획이 빠졌어요.',
    displayDetail: '「조인 실습」에 실행 계획이 빠졌어요.' } as const;
  const markup = renderToStaticMarkup(createElement(MaterialReason, { kind: '강좌', hasOptions: true, diagnostic, fallback }));
  expect(markup).toContain(diagnostic.displayDetail);
  expect(markup).not.toContain('S1-C1');
});

it('기존 응답은 내부 키 전체만 중립 표현으로 표시한다', () => {
  const diagnostic = { reason: 'scope_gap', detail: 'S1-C1 및 S1-C10의 범위가 달라요. SQL_S1-C1 예제와 B2B 문맥은 유지해요.' } as const;
  const markup = renderToStaticMarkup(createElement(MaterialReason, { kind: '강좌', hasOptions: true, diagnostic, fallback }));
  expect(markup).toContain('비교 후보 및 비교 후보의 범위가 달라요. SQL_S1-C1 예제와 B2B 문맥은 유지해요.');
  expect(markup).not.toContain('S1-C10');
});

it('표시 문구가 없는 도서 진단도 후보 키를 가리고 뒤 문장을 보존한다', () => {
  const note = '전처리 실습은 소개에서 확인되지 않아요.';
  const diagnostic = { reason: 'scope_gap', detail: `B1의 근거를 확인했어요. ${note}` } as const;
  const markup = renderToStaticMarkup(createElement(MaterialReason, { kind: '도서', hasOptions: false, diagnostic, fallback }));
  expect(markup).toContain(`비교 후보의 근거를 확인했어요. ${note}`);
  expect(markup).not.toContain('B1');
});

it.each(['도서 후보는 있지만 이번 추천에서는 선정되지 않았어요.', '이 스킬에 추천할 도서가 없어요.'])(
  '진단이 없는 도서 목록은 기존 안내를 표시한다 (%s)',
  fallback => {
    const markup = renderToStaticMarkup(createElement(MaterialReason, { kind: '도서', hasOptions: false, fallback }));
    expect(markup).toBe(`<p class="small muted">${fallback}</p>`);
  },
);

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { OutdatedRecommendations, UnverifiedTargets } from './ResourceNotices';

it('자료 카드에 서버가 계산한 미확인 범위를 표시한다', () => {
  const markup = renderToStaticMarkup(createElement(UnverifiedTargets, { topics: ['dbt 증분 처리', 'dbt 재처리·백필'] }));
  expect(markup).toContain('확인되지 않은 범위: dbt 증분 처리, dbt 재처리·백필');
});

it.each([undefined, []])('미확인 범위가 없으면 안내를 표시하지 않는다 (%s)', topics => {
  expect(renderToStaticMarkup(createElement(UnverifiedTargets, { topics }))).toBe('');
});

it('이전 기준 안내와 기존 계획 재생성 동작을 알려 준다', () => {
  const markup = renderToStaticMarkup(createElement(OutdatedRecommendations, { outdated: true, courseId: 'A2' }));
  expect(markup).toContain('이전 기준으로 추천된 자료예요.');
  expect(markup).toContain('다르게 다시 만들기');
  expect(markup).toContain('role="status"');
  expect(markup).not.toContain('<button');
});

it.each([false, undefined])('현재 기준 또는 기존 응답에는 이전 기준 안내가 없다 (%s)', outdated => {
  expect(renderToStaticMarkup(createElement(OutdatedRecommendations, { outdated }))).toBe('');
});

it('자료 선택 화면에서 실제 이전 화면과 계획 재생성 동작을 안내한다', () => {
  const markup = renderToStaticMarkup(createElement(OutdatedRecommendations, { outdated: true }));
  expect(markup).toContain('이전: 로드맵·자료 선택');
  expect(markup).toContain('다르게 다시 만들기');
  expect(markup).not.toContain('다시 추천하면');
  expect(markup).not.toContain('<button');
});

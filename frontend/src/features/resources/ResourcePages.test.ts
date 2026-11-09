import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';
import { ResKv } from './ResourcePages';
import { resourceImageUrl } from '@/shared/lib/resourceImageUrl';
import type { Resource } from '@/api/types/catalog';

it.each([
  ['UPPER_INTERMEDIATE', false, '목차 검토로 중상 확정', '중상'],
  ['INTERMEDIATE', true, '제공처 난이도 미기재로 추정', '중급'],
] as const)('상세 화면은 근거 없이 등급만 표시한다: %s', (difficulty, difficultyEstimated, difficultyBasis, level) => {
  const r: Resource = { id: 'course', type: 'course', title: '강좌', provider: '기관', kind: '강좌',
    difficulty, difficultyEstimated, difficultyBasis, detailsLoaded: true };
  const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(ResKv, { r })));
  expect(html).toContain(`<dt>난이도</dt><dd>${level}</dd>`);
  expect(html).not.toContain(difficultyBasis);
});

it('links every resource summary to its full introduction even without a public outline', () => {
  for (const type of ['course','book','cert']) {
    const r: Resource = { id:`${type}-fixture`, title:'자료', provider:'기관', kind:'자료', type,
      content:'목록 요약', detailsLoaded:false, curriculum:{ item_count:0, coverage:'description_only' } };
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(ResKv, { r })));
    expect(html).toContain(`href="/resources/${type}-fixture"`);
    expect(html).toContain('전체 소개·상세 보기');
  }
});

it('renders the complete introduction on detail without a redundant link to itself', () => {
  const r: Resource = { id:'book', title:'도서', provider:'기관', kind:'도서', type:'book',
    content:'전체 소개 '.repeat(100), detailsLoaded:true };
  const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(ResKv, { r })));
  expect(html).toContain(r.content!);
  expect(html).not.toContain('전체 소개·상세 보기');
});

it('사내교육 안내 주소가 열린 목차로 연결되고 과정 표지만 같은 사이트에서 표시된다', () => {
  const r: Resource = {id:'INTERNAL_CRASH_05', title:'Redis TTL', kind:'강좌', type:'course',
    platform:'사내교육', provider:'사내교육', url:'/resources/INTERNAL_CRASH_05?view=curriculum',
    cost:15000, detailsLoaded:true, curriculum:{coverage:'full_outline',item_count:1,items:[{title:'TTL 적용'}]}};
  const render = (showCurriculum:boolean) => renderToStaticMarkup(createElement(MemoryRouter,null,createElement(ResKv,{r,showCurriculum})));
  expect(render(false)).toContain(r.url);
  expect(render(true)).toMatch(/<details open/);
  expect(render(true)).not.toContain('사내교육 안내 보기');
  expect(render(true)).toContain('15,000');
  const cover='/images/internal-training/crash-05.webp';
  expect(resourceImageUrl(cover)).toBe(cover);
  expect(resourceImageUrl('/images/resource-course.svg')).toBe('/images/resource-course.svg');
  expect(resourceImageUrl('/images/internal-training/challenge-1000.webp')).toBe('/images/internal-training/challenge-1000.webp');
  expect(resourceImageUrl('//other.example/image')).toBe('');
  expect(resourceImageUrl('/images/internal-training/../secret')).toBe('');
});

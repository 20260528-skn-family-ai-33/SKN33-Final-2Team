import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it } from 'vitest';
import { ResKv, ResourcesPage } from './ResourcePages';
import { ResourcePagination } from './ResourcePagination';
import { listSearchOf, pageNumbers } from './resourceBrowse';
import { resourceImageUrl } from '@/shared/lib/resourceImageUrl';
import type { Resource } from '@/api/types/catalog';

it('여러 페이지의 첫·현재·마지막 번호와 직접 이동을 제공하고 한 페이지면 숨긴다', () => {
  const props = { page: 50, pages: 100, disabled: false, label: '페이지 이동', onChange: () => {} };
  const html = renderToStaticMarkup(createElement(ResourcePagination, props));
  expect(html).toContain('aria-label="1페이지"');
  expect(html).toContain('aria-label="50페이지" aria-current="page"');
  expect(html).toContain('aria-label="100페이지"');
  expect(html).not.toContain('aria-label="20페이지"');
  expect(html).toContain('max="100"');
  expect(renderToStaticMarkup(createElement(ResourcePagination, { ...props, page: 1, pages: 1 }))).toBe('');
});

it('좁은 화면은 현재 페이지 양옆 번호를 하나씩만 남기고 첫·마지막 번호는 유지한다', () => {
  expect(pageNumbers(40, 82, 2)).toEqual([1, 38, 39, 40, 41, 42, 82]);
  expect(pageNumbers(40, 82, 1)).toEqual([1, 39, 40, 41, 82]);
  expect(pageNumbers(1, 82, 1)).toEqual([1, 2, 3, 82]);
  expect(pageNumbers(82, 82, 1)).toEqual([1, 80, 81, 82]);
  expect(pageNumbers(2, 2, 1)).toEqual([1, 2]);
});

it('상세 복귀 주소는 표시 중인 응답의 조건으로 만든다', () => {
  expect(listSearchOf({ kind: '강좌', q: 'Python', platform: 'K-MOOC', sort: 'title_asc', page: 2 }))
    .toBe('kind=%EA%B0%95%EC%A2%8C&q=Python&platform=K-MOOC&sort=title_asc&page=2');
  expect(listSearchOf({ kind: '전체', q: '', platform: '', sort: 'default', page: 1 })).toBe('');
});

it('기존 자격 종류의 목록·탭·건수에 자격증을 표시한다', () => {
  const client = new QueryClient();
  client.setQueryData(['resource-browser', '자격', '', '', 'default', 1], {
    kind: '자격', term: '', page: 1, total: 1,
    items: [{ id: 'cert_test', title: '예시 시험', provider: '시험기관', type: 'cert', kind: '자격' }],
  });
  const html = renderToStaticMarkup(createElement(QueryClientProvider, { client },
    createElement(MemoryRouter, { initialEntries: ['/resources?kind=자격'] }, createElement(ResourcesPage))));
  expect(html).toContain('aria-pressed="true">자격증</button>');
  expect(html).toContain('자격증 1건');
  expect(html).toContain('자격증 · 시험기관');
  expect(html).not.toContain('강좌 사이트');
});

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

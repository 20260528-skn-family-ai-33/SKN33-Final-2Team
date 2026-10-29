import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';
import { ResKv } from './ResourcePages';
import type { Resource } from '@/api/types/catalog';

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

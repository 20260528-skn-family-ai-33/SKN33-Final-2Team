import { beforeEach, expect, it } from 'vitest';
import { mergeRes, useCatalog } from './catalog';

beforeEach(() => useCatalog.setState({ res:{} }));

it('keeps fetched detail when later list/lookup summaries update common metadata', () => {
  const base = { id:'course', title:'강좌', provider:'기관', kind:'강좌' };
  mergeRes({ course:{ ...base, content:'소개 일부', detailsLoaded:false, curriculum:{ item_count:1 } } });
  expect(useCatalog.getState().res.course.detailsLoaded).toBe(false);
  mergeRes({ course:{ ...base, content:'전체 소개', detailsLoaded:true, curriculum:{ items:[{ title:'SQL' }], item_count:1 } } });
  mergeRes({ course:{ ...base, title:'갱신된 강좌', content:'소개 일부', detailsLoaded:false, curriculum:{ item_count:1 } } });
  const result = useCatalog.getState().res.course;
  expect(result.title).toBe('갱신된 강좌');
  expect(result.detailsLoaded).toBe(true);
  expect(result.content).toBe('전체 소개');
  expect(result.curriculum?.items?.[0].title).toBe('SQL');
});

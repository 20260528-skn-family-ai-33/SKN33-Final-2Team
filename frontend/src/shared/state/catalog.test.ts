import { beforeEach, expect, it, vi } from 'vitest';
import { QueryClient, QueryObserver } from '@tanstack/react-query';
import { catalogApi } from '@/api/endpoints/catalog';
import { mergeRes, resourceDetailQuery, useCatalog } from './catalog';

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

it('refetches a fresh cached detail on reentry after an administrator changes the description', async () => {
  const base = { id:'course', title:'강좌', provider:'기관', kind:'강좌' };
  const old = { ...base, content:'이전 전체 소개', detailsLoaded:true };
  const latest = { ...base, content:'관리자가 수정한 최신 전체 소개', detailsLoaded:true };
  const api = vi.spyOn(catalogApi, 'resource').mockResolvedValue(latest);
  const client = new QueryClient({ defaultOptions:{ queries:{ retry:false, staleTime:Infinity, gcTime:Infinity } } });
  client.setQueryData(['resource','course'], old);
  mergeRes({ course:old });
  mergeRes({ course:{ ...base, content:'최신 목록 요약', detailsLoaded:false } });
  const observer = new QueryObserver(client, resourceDetailQuery('course'));
  let stop = () => {};
  try {
    await new Promise<void>((resolve) => {
      stop = observer.subscribe((result) => {
        if (result.isSuccess && !result.isFetching && result.data.content === latest.content) resolve();
      });
    });
    expect(api).toHaveBeenCalledExactlyOnceWith('course');
    expect(useCatalog.getState().res.course.content).toBe(latest.content);
  } finally {
    stop(); client.clear(); api.mockRestore();
  }
});

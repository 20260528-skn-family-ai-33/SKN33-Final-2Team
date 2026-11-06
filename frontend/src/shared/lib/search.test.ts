import { afterEach, describe, expect, it, vi } from 'vitest';
import { catalogApi } from '@/api/endpoints/catalog';
import { searchTerm } from './search';

afterEach(() => vi.unstubAllGlobals());

describe('입력하는 대로 찾기의 검색어 (#102)', () => {
  it('앞뒤 공백을 빼고 영문·숫자 검색어는 그대로 둔다', () => {
    expect(searchTerm('  Docker  ')).toBe('Docker');
    expect(searchTerm('Python 3')).toBe('Python 3');
    expect(searchTerm('   ')).toBe('');
  });

  it('한글 조합 중 끝에 남은 낱자는 빼서 완성된 음절까지만 찾는다', () => {
    expect(searchTerm('도ㅋ')).toBe('도');
    expect(searchTerm('데이터 ㅂ')).toBe('데이터');
    expect(searchTerm('SQLㄱ')).toBe('SQL');
    expect(searchTerm('ㅍ')).toBe('');
    expect(searchTerm('도커')).toBe('도커');
  });

  it('완성된 음절 사이의 낱자는 지우지 않는다', () => {
    expect(searchTerm('ㅋ커')).toBe('ㅋ커');
  });
});

describe('자료 검색 요청', () => {
  it('검색어가 바뀌어 필요 없어진 요청을 끊을 수 있게 signal 을 넘긴다', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })));
    vi.stubGlobal('fetch', fetch);
    const ctrl = new AbortController();
    await catalogApi.resources({ q: '도커', limit: 30, offset: 0 }, ctrl.signal);
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/resources?q=%EB%8F%84%EC%BB%A4&limit=30&offset=0');
    expect(fetch.mock.calls[0][1].signal).toBe(ctrl.signal);
  });

  it('끊긴 요청은 서버 연결 오류로 바꾸지 않고 취소로 끝낸다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')));
    await expect(catalogApi.resources({ q: 'RAG' }, new AbortController().signal)).rejects.toMatchObject({ name: 'AbortError' });
  });
});

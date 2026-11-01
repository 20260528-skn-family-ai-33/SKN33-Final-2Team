import { afterEach, describe, expect, it, vi } from 'vitest';
import { reviewRequest } from './reviewRequest';
afterEach(() => vi.unstubAllGlobals());
describe('검토 응답 처리', () => {
  it('빈 프록시 오류는 JSON 파싱 오류 대신 연결 안내를 보여주고 POST를 자동 재시도하지 않는다', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 502 }));
    vi.stubGlobal('fetch', fetcher);
    await expect(reviewRequest('/test', { method: 'POST' })).rejects.toThrow('HTTP 502');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('성공 코드여도 빈 응답을 정상 데이터로 처리하지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 200 })));
    await expect(reviewRequest('/test')).rejects.toThrow('응답이 비어');
  });
  it('HTML 오류와 잘못된 JSON을 처리한다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Bad Gateway</html>', { status: 502 })));
    await expect(reviewRequest('/test')).rejects.toThrow('서버 응답을 확인');
  });
  it('서버의 오류 설명과 정상 JSON을 유지한다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ error: { message: '자료가 변경됐어요.' } }), { status: 409 })).mockResolvedValueOnce(new Response(JSON.stringify({ versions: [] }))));
    await expect(reviewRequest('/test')).rejects.toThrow('자료가 변경됐어요.');
    await expect(reviewRequest('/test')).resolves.toEqual({ versions: [] });
  });
});

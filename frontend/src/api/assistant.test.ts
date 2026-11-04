import { afterEach, describe, expect, it, vi } from 'vitest';
import { assistantApi } from './endpoints/assistant';
import { waitJob } from './jobs';
import { http } from './client';

afterEach(() => vi.unstubAllGlobals());

describe('익명 챗봇 요청과 계정 요청 분리', () => {
  it('질문·조회·취소는 전용 경로를 쓰고 로그인 쿠키를 보내지 않는다', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ jobId: 'chat' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'done', result: { answer: '답변' } })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'cancelled' })));
    vi.stubGlobal('fetch', fetch);
    await assistantApi.ask('식당 위치', []);
    expect(await waitJob('chat', { pathPrefix: '/assistant/jobs' })).toEqual({ answer: '답변' });
    await assistantApi.cancelJob('chat');
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/assistant/ask', '/api/v1/assistant/jobs/chat?wait=10', '/api/v1/assistant/jobs/chat/cancel',
    ]);
    for (const [, options] of fetch.mock.calls) expect(options.credentials).toBe('omit');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ question: '식당 위치', history: [] });
  });

  it('기존 회원 API는 로그인 쿠키를 유지한다', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetch);
    await http.get('/me');
    expect(fetch.mock.calls[0][1].credentials).toBe('same-origin');
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';
import { assistantApi } from './endpoints/assistant';
import { cancelJob, waitJob } from './jobs';
import { http } from './client';

afterEach(() => vi.unstubAllGlobals());

describe('직원 로그인 세션을 사용하는 챗봇 요청', () => {
  it('질문·조회·취소에 로그인 쿠키를 보낸다', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ jobId: 'chat' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'done', result: { answer: '답변' } })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'cancelled' })));
    vi.stubGlobal('fetch', fetch);
    await assistantApi.ask('식당 위치', []);
    expect(await waitJob('chat')).toEqual({ answer: '답변' });
    await cancelJob('chat');
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/assistant/ask', '/api/v1/jobs/chat?wait=10', '/api/v1/jobs/chat/cancel',
    ]);
    for (const [, options] of fetch.mock.calls) expect(options.credentials).toBe('same-origin');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ question: '식당 위치', history: [] });
  });

  it('기존 회원 API는 로그인 쿠키를 유지한다', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetch);
    await http.get('/me');
    expect(fetch.mock.calls[0][1].credentials).toBe('same-origin');
  });
});

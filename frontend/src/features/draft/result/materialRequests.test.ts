import { afterEach, expect, it, vi } from 'vitest';

const waitJob = vi.hoisted(() => vi.fn());
vi.mock('@/api/jobs', () => ({ waitJob }));
vi.mock('../draftSync', () => ({ flush: async () => {} }));

import { loadRecommendations, type Result } from './materialRequests';

afterEach(() => {
  vi.unstubAllGlobals();
  waitJob.mockReset();
});

it('선로딩이 진행 중이면 자료 화면도 같은 생성 결과를 받는다', async () => {
  const ready: Result = { generationId: 'g1', recommendations: { id: 'r1', skills: [] }, choices: {} };
  let finish!: (result: Result) => void;
  waitJob.mockReturnValue(new Promise<Result>(resolve => { finish = resolve; }));
  const fetchMock = vi.fn<typeof fetch>()
    .mockResolvedValueOnce(Response.json({ ...ready, recommendations: null }))
    .mockResolvedValueOnce(Response.json({ jobId: 'job-1' }, { status: 202 }));
  vi.stubGlobal('fetch', fetchMock);

  const prefetched = loadRecommendations('draft-1', 'g1', 'A2', 'v1');
  await vi.waitFor(() => expect(waitJob).toHaveBeenCalledWith('job-1'));
  const screen = loadRecommendations('draft-1', 'g1', 'A2', 'v1');
  expect(screen).toBe(prefetched);

  finish(ready);
  await expect(Promise.all([prefetched, screen])).resolves.toEqual([ready, ready]);
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
});

it('제안 버전을 바꾸면 이전 버전의 진행 중인 조회를 재사용하지 않는다', async () => {
  const fetchMock = vi.fn<typeof fetch>()
    .mockImplementation(async () => Response.json({ generationId: 'g1', recommendations: { id: 'r1', skills: [] }, choices: {} }));
  vi.stubGlobal('fetch', fetchMock);

  const first = loadRecommendations('draft-1', 'g1', 'A2', 'v1');
  const next = loadRecommendations('draft-1', 'g1', 'A2', 'v2');
  expect(next).not.toBe(first);
  await Promise.all([first, next]);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

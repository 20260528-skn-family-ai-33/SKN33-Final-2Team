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
it('서버에서 로드맵 후 준비 중인 자료 작업을 재사용하고 POST하지 않는다', async () => {
  const ready: Result={generationId:'bg',recommendations:{id:'bg-r',skills:[]},choices:{}};
  waitJob.mockResolvedValue(ready);
  const fetchMock=vi.fn<typeof fetch>().mockResolvedValue(Response.json({...ready,recommendations:null,preparingJobId:'server-job'}));
  vi.stubGlobal('fetch',fetchMock);
  await expect(loadRecommendations('server-draft','bg','A3','server-version')).resolves.toEqual(ready);
  expect(waitJob).toHaveBeenCalledWith('server-job');
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][1]?.method).not.toBe('POST');
});

it.each([true, false])('진단 유무(%s)와 무관하게 기존 선택을 조회하고 생성 요청을 하지 않는다', async withDiagnostics => {
  const saved: Result = {
    courseId: 'A2', generationId: 'g1', choices: { SQL: { course: 'course_saved', books: [] } },
    recommendations: { id: 'r1', skills: [{
      name: 'SQL',
      courses: [
        { id: 'course_long', title: 'SQL 실행 계획 평가', hours: 12, cost: 0, why: '', knowledge: '', aiRecommended: true },
        { id: 'course_saved', title: 'SQL 실습', hours: 8, cost: 0, why: '', knowledge: '', aiRecommended: false },
      ],
      books: [], selectedCourse: 'course_long', selectedBooks: [],
      ...(withDiagnostics ? {
        courseDiagnostic: { reason: 'longer_for_coverage', detail: '쿼리 평가 실습까지 포함해요.' },
        bookDiagnostic: { reason: 'scope_gap', detail: '필요한 쿼리 평가가 빠져 있어요.' },
      } : {}),
    }] },
  };
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json(saved));
  vi.stubGlobal('fetch', fetchMock);

  await expect(loadRecommendations(`saved-draft-${withDiagnostics}`, 'g1', 'A2', 'v1')).resolves.toEqual(saved);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined();
});

it('자료 조회가 실패한 요청에서 추가 생성을 시도하지 않는다', async () => {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(
    Response.json({ error: { message: '추천 자료를 읽지 못했어요.' } }, { status: 503 }),
  );
  vi.stubGlobal('fetch', fetchMock);

  await expect(loadRecommendations('unavailable-draft', 'g1', 'A3', 'v1')).rejects.toThrow('추천 자료를 읽지 못했어요.');
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it.each([true, false, undefined])('이전 기준 여부(%s)를 전달하고 저장된 선택을 자동 재추천하지 않는다', async outdated => {
  const saved: Result = {
    courseId: 'A2', generationId: 'g1', choices: { SQL: { course: 'saved', books: [] } },
    recommendations: { id: 'old', outdated, skills: [{ name: 'SQL',
      courses: [{ id: 'saved', title: '저장 강좌', hours: 8, cost: 0, why: '', knowledge: '', aiRecommended: true }],
      books: [], selectedCourse: 'saved', selectedBooks: [],
    }] },
  };
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json(saved));
  vi.stubGlobal('fetch', fetchMock);

  await expect(loadRecommendations(`version-notice-${outdated}`, 'g1', 'A2', 'v1')).resolves.toEqual(saved);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined();
});

it.each([true, false])('빈 작업 완료 후 저장 자료를 조회한다 (%s)', async hasSaved => {
  const ready: Result = { generationId: 'g1', recommendations: { id: 'r1', skills: [] }, choices: {} };
  waitJob.mockResolvedValue({});
  const fetchMock = vi.fn<typeof fetch>()
    .mockResolvedValueOnce(Response.json({ recommendations: null, preparingJobId: 'job-empty' }))
    .mockResolvedValueOnce(Response.json(hasSaved ? ready : { recommendations: null }));
  vi.stubGlobal('fetch', fetchMock);
  const load = loadRecommendations('empty-job', 'g1', 'A3', 'v1');
  if (hasSaved) await expect(load).resolves.toEqual(ready);
  else await expect(load).rejects.toThrow('다시 시도');
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock.mock.calls[1][1]?.method).toBeUndefined();
});

it('작업 ID 발급 대기는 상한 이후 종료한다', async () => {
  vi.useFakeTimers();
  try {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ recommendations: null, preparingJobId: '' })));
    const load = loadRecommendations('pending-job', 'g1', 'A3', 'v1');
    const assertion = expect(load).rejects.toThrow('자료 준비가 지연');
    await vi.advanceTimersByTimeAsync(10200);
    await assertion;
    expect(waitJob).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});

import { beforeEach, expect, it, vi } from 'vitest';
const mock = vi.hoisted(() => ({ scope: 'S', flush: vi.fn(), request: vi.fn() }));
vi.mock('@/shared/state/workspace', () => ({ ws: () => ({}) }));
vi.mock('./reviewScope', () => ({ reviewScope: () => mock.scope }));
vi.mock('../draftSync', () => ({ flush: mock.flush }));
vi.mock('./reviewRequest', () => ({ reviewRequest: mock.request }));
import { initializeReview, readExisting } from './reviewInitial';
import { reviewTasks } from './reviewTasks';

const proposal = (id: string, summaries = true) => ({ id, key: 'k', selectedIds: ['t'], option: { acts: [] }, ...(summaries ? { skillSummaries: { SQL: ['요약'] } } : {}) });
const materials = { recommendations: { skills: [] }, choices: {} };
const saved = (p: ReturnType<typeof proposal> | null) => ({ proposal: p, versions: p ? [p] : [] });
function deferred<T>() { let resolve!: (value: T) => void; const work = new Promise<T>(done => { resolve = done; }); return { work, resolve }; }
const calls = () => mock.request.mock.calls.map(([path, init]) => `${(init as RequestInit | undefined)?.method || 'GET'} ${String(path).split('?')[0].split('/').pop()}`);
let server: Record<string, () => unknown>;
beforeEach(() => {
  vi.resetAllMocks(); reviewTasks.clear(); mock.scope = 'S'; mock.flush.mockResolvedValue(undefined);
  server = { 'GET activities': () => saved(proposal('base')), 'GET recommendations': () => materials };
  mock.request.mockImplementation(async (path: string, init?: RequestInit) => {
    const key = `${init?.method || 'GET'} ${path.split('?')[0].split('/').pop()}`;
    if (!server[key]) throw new Error(`예상하지 못한 요청: ${key}`);
    return server[key]();
  });
});
it('화면의 먼저 보여 주기와 준비 흐름이 동시에 시작해도 저장된 제안·자료 GET 은 각 1회만 보낸다', async () => {
  const [early, ready] = await Promise.all([readExisting('d', 'A2', 'S'), initializeReview('d', 'A2', 'S')]);
  expect(calls()).toEqual(['GET activities', 'GET recommendations']);
  expect(early).toEqual({ body: saved(proposal('base')), resources: materials });
  expect(ready).toEqual({ body: saved(proposal('base')), resources: materials, summaries: undefined });
});
it('같은 범위로 다시 들어오면 남겨 둔 준비 결과를 써서 GET 을 다시 보내지 않는다', async () => {
  await Promise.all([readExisting('d', 'A2', 'S'), initializeReview('d', 'A2', 'S')]);
  mock.request.mockClear();
  await Promise.all([readExisting('d', 'A2', 'S'), initializeReview('d', 'A2', 'S')]);
  expect(calls()).toEqual([]);
});
it('저장된 제안이 없으면 한 번 읽어 먼저 보여 준 뒤 제안과 역량 요약을 만든다', async () => {
  const generated = deferred<unknown>();
  server['GET activities'] = () => saved(null);
  server['POST activities'] = () => generated.work;
  server['POST learning-outcomes'] = () => ({ summaries: { SQL: ['새 요약'] } });
  const ready = initializeReview('d', 'A2', 'S');
  expect(await readExisting('d', 'A2', 'S')).toEqual({ body: saved(null), resources: materials });
  generated.resolve(saved(proposal('new', false)));
  expect(await ready).toMatchObject({ body: { proposal: { id: 'new' } }, summaries: { SQL: ['새 요약'] } });
  expect(calls()).toEqual(['GET activities', 'GET recommendations', 'POST activities', 'POST learning-outcomes']);
});
it('준비가 실패한 뒤 다시 들어오면 남겨 둔 읽기는 먼저 보여 주기에만 쓰고 준비 흐름은 최신 상태를 한 번 읽는다', async () => {
  server['GET activities'] = () => saved(null);
  server['POST activities'] = () => { throw new Error('생성 실패'); };
  await expect(Promise.all([readExisting('d', 'A2', 'S'), initializeReview('d', 'A2', 'S')])).rejects.toThrow('생성 실패');
  mock.request.mockClear(); server['GET activities'] = () => saved(proposal('base'));
  const [early, ready] = await Promise.all([readExisting('d', 'A2', 'S'), initializeReview('d', 'A2', 'S')]);
  expect(early.body.proposal).toBeNull();
  expect(ready.body.proposal?.id).toBe('base');
  expect(calls()).toEqual(['GET activities', 'GET recommendations']);
});
it('저장을 기다리는 동안 검토 범위가 바뀌면 읽지 않고 멈춘다', async () => {
  const saving = deferred<void>(); mock.flush.mockReturnValue(saving.work);
  const early = readExisting('d', 'A2', 'S'), ready = initializeReview('d', 'A2', 'S');
  mock.scope = 'T'; saving.resolve();
  await expect(early).rejects.toThrow('검토 입력이 변경됐어요.');
  await expect(ready).rejects.toThrow('검토 입력이 변경됐어요.');
  expect(mock.request).not.toHaveBeenCalled();
});

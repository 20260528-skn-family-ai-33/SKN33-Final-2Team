/* PR #84 리뷰: 다른 로그인의 늦은 응답(P1·P3) · 부서장 직원 기록 캐시 갱신(P2) · 본인 알림이 작성 중인 초안·저장 전 사후 점검 입력을 덮지 않음(P2) */
import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppNotification, NotificationInbox } from '@/api/types/notification';
import type { PlanRecord, Report } from '@/api/types/plan';

const m = vi.hoisted(() => ({ me: { id: 'A' } as { id: string } | null, seq: 1, read: vi.fn(), readAll: vi.fn(), readTarget: vi.fn(), get: vi.fn(), reports: vi.fn(), pull: vi.fn() }));
vi.mock('@/shared/state/session', () => ({ me: () => m.me, signInSeq: () => m.seq, isSup: () => true }));
vi.mock('@/api/endpoints/notifications', () => ({ notificationsApi: { read: m.read, readAll: m.readAll, readTarget: m.readTarget } }));
vi.mock('@/api/endpoints/plans', () => ({ plansApi: { get: m.get, reports: m.reports } }));
vi.mock('@/shared/state/catalog', () => ({ mergeRes: vi.fn(), mergeReg: vi.fn() }));
vi.mock('@/features/draft/draftSync', () => ({ pullDraftOrThrow: m.pull }));

type Actions = typeof import('./notificationActions');
type Ws = typeof import('@/shared/state/workspace');
let act: Actions;
let wsMod: Ws;

const A1 = { id: 'A', seq: 1 };
const box = (title: string): NotificationInbox => ({ items: [{ id: 'n1', planTitle: title } as AppNotification], unread: 1 });
const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
};
const note = (o: Partial<AppNotification>): AppNotification =>
  ({ id: 'n1', kind: 'report', audience: 'self', employee: { id: '8', name: '김직원' }, planId: 'p1', planTitle: '', track: '', reportId: 'r-new', createdAt: '', read: false, ...o }) as AppNotification;
const rec = (id: string, status: string, essay = '') =>
  ({ id, status, revision: null, pending: null, post: { answers: {}, goalSelf: '', file: null, deep: { essay: { e1: essay } } } }) as unknown as PlanRecord;
const rep = (id: string, planId: string) => ({ id, planId }) as Report;
const essayOf = (R: PlanRecord) => (R.post.deep as unknown as { essay: Record<string, string> }).essay.e1;

beforeEach(async () => {
  vi.resetModules();
  vi.resetAllMocks();
  m.me = { id: 'A' };
  m.seq = 1;
  act = await import('./notificationActions');
  wsMod = await import('@/shared/state/workspace');
});

describe('P1·P3 요청을 시작한 로그인에만 반영', () => {
  it('직원마다 다른 캐시 키를 쓰고, 로그인 정보는 직원 id 와 회차를 담는다', () => {
    expect(act.notificationKey('A')).not.toEqual(act.notificationKey('B'));
    expect(act.currentSignIn()).toEqual(A1);
    m.me = null;
    expect(act.currentSignIn()).toBeNull();
  });

  it('P1: 모두 읽음 응답이 오기 전에 다른 직원으로 바뀌면 어느 캐시에도 넣지 않는다', async () => {
    const qc = new QueryClient();
    const late = deferred<NotificationInbox>();
    m.readAll.mockReturnValue(late.promise);
    const pending = act.markRead(qc, A1);
    m.me = { id: 'B' }; // A 로그아웃 → B 로그인
    m.seq = 3;
    late.resolve(box('A만 볼 수 있는 로드맵'));
    expect(await pending).toBe(false);
    expect(qc.getQueryData(act.notificationKey('B'))).toBeUndefined();
    expect(qc.getQueryData(act.notificationKey('A'))).toBeUndefined();
  });

  it('P3: 같은 직원이 로그아웃 뒤 다시 로그인해도 이전 로그인의 늦은 응답은 버린다', async () => {
    const qc = new QueryClient();
    const late = deferred<NotificationInbox>();
    m.read.mockReturnValue(late.promise);
    const pending = act.markRead(qc, A1, 'n1');
    m.seq = 3; // 로그아웃(2) → 같은 A 로 로그인(3)
    late.resolve(box('이전 로그인에서 누른 알림'));
    expect(await pending).toBe(false);
    expect(act.stillSignedIn(A1)).toBe(false);
    expect(qc.getQueryData(act.notificationKey('A'))).toBeUndefined();
  });

  it('같은 로그인이면 그 직원 캐시에만 넣는다', async () => {
    const qc = new QueryClient();
    m.read.mockResolvedValue(box('내 로드맵'));
    expect(await act.markRead(qc, A1, 'n1')).toBe(true);
    expect(m.read).toHaveBeenCalledWith('n1');
    expect(qc.getQueryData(act.notificationKey('A'))).toEqual(box('내 로드맵'));
    expect(qc.getQueryData(act.notificationKey('B'))).toBeUndefined();
  });

  it('PR #107 리뷰: 한 건·모두 읽음도 소속 직원 목록·직원 기록 캐시를 무효화한다(새 로드맵·보고서 표시가 남지 않게)', async () => {
    for (const id of ['n1', undefined]) {
      const qc = new QueryClient();
      qc.setQueryData(['team'], { members: [] });
      qc.setQueryData(['team-member', '8'], { unseen: { plans: ['p1'], reports: [] } });
      (id ? m.read : m.readAll).mockResolvedValue(box('x'));
      expect(await act.markRead(qc, A1, id)).toBe(true);
      expect(qc.getQueryState(['team'])?.isInvalidated).toBe(true);
      expect(qc.getQueryState(['team-member', '8'])?.isInvalidated).toBe(true);
    }
  });

  it('다른 로그인의 늦은 읽음 응답은 목록 캐시도 건드리지 않는다', async () => {
    const qc = new QueryClient();
    qc.setQueryData(['team'], { members: [] });
    const late = deferred<NotificationInbox>();
    m.readAll.mockReturnValue(late.promise);
    const pending = act.markRead(qc, A1);
    m.seq = 3;
    late.resolve(box('이전 로그인'));
    expect(await pending).toBe(false);
    expect(qc.getQueryState(['team'])?.isInvalidated).toBe(false);
  });
});

describe('P2 부서장 알림: 이동 전에 그 직원 기록을 새로 받는다', () => {
  it('화면에서 쓰지 않고 캐시에만 남은 옛 기록도 다시 받아, 새 보고서가 들어 있게 한다', async () => {
    const { memberKey } = await import('@/features/team/teamData');
    const qc = new QueryClient();
    const fetchMember = vi.fn().mockResolvedValueOnce({ reports: [rep('r-old', 'p1')] }).mockResolvedValueOnce({ reports: [rep('r-new', 'p1')] });
    await qc.fetchQuery({ queryKey: memberKey('8'), queryFn: fetchMember });
    await act.refreshTarget(qc, A1, note({ audience: 'head' }));
    expect(fetchMember).toHaveBeenCalledTimes(2);
    expect(qc.getQueryData<{ reports: Report[] }>(memberKey('8'))?.reports[0].id).toBe('r-new');
    expect(m.get).not.toHaveBeenCalled(); // 부서장은 본인 작업 공간을 건드리지 않는다
  });
});

describe('P2 본인 알림: 화면에 있는 로드맵은 덮지 않고, 없는 것만 받는다', () => {
  const seed = (plans: Record<string, PlanRecord>) =>
    wsMod.useWs.setState(
      {
        ...wsMod.freshWs('A'),
        draft: { ...wsMod.freshDraft(), goal: '아직 저장 안 된 작성 중 목표' },
        plans,
        reports: [rep('r-old', 'p1'), rep('r-other', 'p2')],
      },
      true,
    );

  it('로드맵 알림: 이미 있는 로드맵이면 다시 받지 않아, 저장 전 사후 점검 서술형 답이 그대로 남는다', async () => {
    seed({ p1: rec('p1', 'active', '저장 전 새 답변') });
    await act.refreshTarget(new QueryClient(), A1, note({ kind: 'roadmap', reportId: null }));
    expect(m.get).not.toHaveBeenCalled();
    expect(m.reports).not.toHaveBeenCalled();
    expect(essayOf(wsMod.ws().plans.p1)).toBe('저장 전 새 답변');
    expect(wsMod.ws().draft.goal).toBe('아직 저장 안 된 작성 중 목표');
  });

  it('보고서 알림: 이미 있는 로드맵은 그대로 두고 그 로드맵의 보고서 목록만 바꾼다', async () => {
    seed({ p1: rec('p1', 'active', '저장 전 새 답변'), p2: rec('p2', 'active') });
    m.reports.mockResolvedValue([rep('r-new', 'p1')]);
    await act.refreshTarget(new QueryClient(), A1, note({}));
    const s = wsMod.ws();
    expect(m.get).not.toHaveBeenCalled();
    expect(m.reports).toHaveBeenCalledWith('p1');
    expect(essayOf(s.plans.p1)).toBe('저장 전 새 답변');
    expect(s.reports.map((r) => r.id)).toEqual(['r-new', 'r-other']);
    expect(s.draft.goal).toBe('아직 저장 안 된 작성 중 목표');
  });

  it('작업 공간에 없는 로드맵이면 받아서 넣는다(작성 중인 초안은 그대로)', async () => {
    seed({ p2: rec('p2', 'active') });
    m.get.mockResolvedValue({ plan: rec('p1', 'active', '서버 답변') });
    await act.refreshTarget(new QueryClient(), A1, note({ kind: 'roadmap', reportId: null }));
    expect(m.get).toHaveBeenCalledWith('p1');
    expect(essayOf(wsMod.ws().plans.p1)).toBe('서버 답변');
    expect(wsMod.ws().draft.goal).toBe('아직 저장 안 된 작성 중 목표');
  });

  it('받는 사이 로그인이 바뀌면(같은 직원의 재로그인 포함) 작업 공간에 넣지 않는다', async () => {
    seed({ p2: rec('p2', 'active') });
    const late = deferred<{ plan: PlanRecord }>();
    m.get.mockReturnValue(late.promise);
    m.reports.mockResolvedValue([rep('r-new', 'p1')]);
    const pending = act.refreshTarget(new QueryClient(), A1, note({}));
    m.seq = 3;
    late.resolve({ plan: rec('p1', 'done') });
    await pending;
    expect(wsMod.ws().plans.p1).toBeUndefined();
    expect(wsMod.ws().reports.map((r) => r.id)).toEqual(['r-old', 'r-other']);
  });
});

describe('markTargetRead (#96 · 부서장이 직원 기록 화면을 열 때)', () => {
  it('같은 로그인이면 바뀐 목록만(changed 빼고) 그 직원 캐시에 넣는다', async () => {
    const qc = new QueryClient();
    m.readTarget.mockResolvedValue({ ...box('읽음으로 바뀐 로드맵'), changed: 1 });
    expect(await act.markTargetRead(qc, A1, 'roadmap', 'p1')).toBe(true);
    expect(m.readTarget).toHaveBeenCalledWith('roadmap', 'p1');
    expect(qc.getQueryData(act.notificationKey('A'))).toEqual(box('읽음으로 바뀐 로드맵'));
  });

  it('PR #107 리뷰: 읽음이 된 알림이 있으면 먼저 받아 둔 소속 직원 목록·직원 기록 캐시를 무효화한다', async () => {
    const qc = new QueryClient();
    qc.setQueryData(['team'], { members: [] }); // 읽음 응답보다 먼저 끝난 목록 조회(옛 '새' 표시)
    qc.setQueryData(['team-member', '8'], { unseen: { plans: ['p1'], reports: [] } });
    m.readTarget.mockResolvedValue({ ...box('x'), changed: 1 });
    await act.markTargetRead(qc, A1, 'roadmap', 'p1');
    expect(qc.getQueryState(['team'])?.isInvalidated).toBe(true);
    expect(qc.getQueryState(['team-member', '8'])?.isInvalidated).toBe(true);
  });

  it('읽음이 된 알림이 없으면(이미 읽음·예전 기록) 목록 캐시를 건드리지 않는다', async () => {
    const qc = new QueryClient();
    qc.setQueryData(['team'], { members: [] });
    m.readTarget.mockResolvedValue({ ...box('x'), changed: 0 });
    await act.markTargetRead(qc, A1, 'report', 'r1');
    expect(qc.getQueryState(['team'])?.isInvalidated).toBe(false);
  });
  it('응답이 오기 전에 로그인이 바뀌면 넣지 않는다', async () => {
    const qc = new QueryClient();
    const late = deferred<NotificationInbox & { changed: number }>();
    m.readTarget.mockReturnValue(late.promise);
    const pending = act.markTargetRead(qc, A1, 'report', 'r1');
    m.seq = 3;
    qc.setQueryData(['team'], { members: [] });
    late.resolve({ ...box('이전 로그인'), changed: 1 });
    expect(await pending).toBe(false);
    expect(qc.getQueryData(act.notificationKey('A'))).toBeUndefined();
    expect(qc.getQueryState(['team'])?.isInvalidated).toBe(false); // 다른 로그인의 캐시도 건드리지 않는다
  });
});

describe('코멘트·작업 알림 (#96): 있는 로드맵은 바뀐 부분만 고친다', () => {
  const seed = (R: PlanRecord) => wsMod.useWs.setState({ ...wsMod.freshWs('A'), plans: { p1: R } });
  const server = (o: Partial<PlanRecord>) => ({ plan: { ...rec('p1', 'active', '서버 답변'), ...o } as PlanRecord });

  it('코멘트 알림: 새 코멘트를 받되 저장 전 사후 점검 입력은 덮지 않는다', async () => {
    seed(rec('p1', 'active', '저장 전 새 답변'));
    m.get.mockResolvedValue(server({ comments: [{ id: 'c1' }] as unknown as PlanRecord['comments'] }));
    await act.refreshTarget(new QueryClient(), A1, note({ kind: 'comment', audience: 'member', reportId: null }));
    expect(wsMod.ws().plans.p1.comments?.map((c) => c.id)).toEqual(['c1']);
    expect(essayOf(wsMod.ws().plans.p1)).toBe('저장 전 새 답변');
    expect(m.reports).not.toHaveBeenCalled();
  });

  it('수정안 작업 알림: 수정안을 받되 저장 전 입력은 덮지 않는다', async () => {
    seed(rec('p1', 'active', '저장 전 새 답변'));
    m.get.mockResolvedValue(server({ comments: [{ id: 'c2' }] as unknown as PlanRecord['comments'] }));
    await act.refreshTarget(new QueryClient(), A1, note({ kind: 'job', jobKind: 'revision', jobStatus: 'done', reportId: null }));
    expect(m.get).toHaveBeenCalledWith('p1');
    expect(wsMod.ws().plans.p1.comments?.map((c) => c.id)).toEqual(['c2']);
    expect(essayOf(wsMod.ws().plans.p1)).toBe('저장 전 새 답변');
  });

  it('보고서 작성 실패 알림: 실패 상태만 고치고 입력은 그대로 둔다', async () => {
    const R = rec('p1', 'active', '저장 전 새 답변');
    R.post.running = true;
    seed(R);
    const fresh = rec('p1', 'active', '서버 답변');
    fresh.post.running = false;
    fresh.post.fail = { cause: '실패' } as unknown as PlanRecord['post']['fail'];
    m.get.mockResolvedValue({ plan: fresh });
    await act.refreshTarget(new QueryClient(), A1, note({ kind: 'job', jobKind: 'report', jobStatus: 'failed', reportId: null }));
    const after = wsMod.ws().plans.p1.post;
    expect(after.running).toBe(false);
    expect(after.fail).toEqual({ cause: '실패' });
    expect(essayOf(wsMod.ws().plans.p1)).toBe('저장 전 새 답변');
  });

  it('로드맵 확정 전 작업 알림: 지금 작성 중인 문서면 다시 읽고, 다른 문서면 읽지 않는다 (PR #139 리뷰)', async () => {
    wsMod.useWs.setState({ ...wsMod.freshWs('A'), draftId: 'd1' });
    const job = note({ kind: 'job', jobKind: 'options', jobStatus: 'done', planId: null, reportId: null, draftId: 'd1' });
    await act.refreshTarget(new QueryClient(), A1, job);
    expect(m.pull).toHaveBeenCalledTimes(1);
    expect(m.get).not.toHaveBeenCalled();
    await act.refreshTarget(new QueryClient(), A1, { ...job, draftId: 'old' });
    expect(m.pull).toHaveBeenCalledTimes(1);
  });

  it('과제 알림: 보고서 목록과 그 로드맵의 과제를 새로 받는다 (#96)', async () => {
    seed(rec('p1', 'active', '저장 전 새 답변'));
    m.reports.mockResolvedValue([rep('r-new', 'p1')]);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    await act.refreshTarget(qc, A1, note({ kind: 'task', audience: 'member', reportId: 'r-new', taskId: 't1' }));
    expect(m.get).not.toHaveBeenCalled();
    expect(wsMod.ws().reports.map((r) => r.id)).toEqual(['r-new']);
    expect(essayOf(wsMod.ws().plans.p1)).toBe('저장 전 새 답변');
    expect(spy).toHaveBeenCalledWith({ queryKey: ['report-tasks', 'p1'] });
  });

  it('과제 결과 알림: 부서장은 그 직원 기록과 과제를 새로 받는다 (#96)', async () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    await act.refreshTarget(qc, A1, note({ kind: 'task_result', audience: 'head', reportId: 'r1', taskId: 't1' }));
    expect(spy).toHaveBeenCalledWith({ queryKey: ['report-tasks', 'p1'] });
    expect(m.reports).not.toHaveBeenCalled();
  });

  describe('보고 있는 화면의 알림 (PR #139 리뷰): 내용을 받은 뒤에 읽음으로', () => {
    const comment = () => note({ id: 'n9', kind: 'comment', audience: 'member', reportId: null });
    const qcAndSeed = () => {
      seed(rec('p1', 'active'));
      return new QueryClient();
    };

    it('받은 다음 읽음으로 바꾼다', async () => {
      const order: string[] = [];
      m.get.mockImplementation(async () => {
        order.push('get');
        return server({});
      });
      m.read.mockImplementation(async () => {
        order.push('read');
        return { items: [], unread: 0 };
      });
      expect(await act.readViewed(qcAndSeed(), A1, comment(), () => true)).toBe(true);
      expect(order).toEqual(['get', 'read']);
      expect(m.read).toHaveBeenCalledWith('n9');
    });

    it('받기가 실패하면 읽음으로 바꾸지 않는다', async () => {
      m.get.mockRejectedValue(new Error('network'));
      await expect(act.readViewed(qcAndSeed(), A1, comment(), () => true)).rejects.toThrow('network');
      expect(m.read).not.toHaveBeenCalled();
    });

    it('작성 중인 문서를 다시 읽지 못하면 읽음으로 바꾸지 않는다', async () => {
      wsMod.useWs.setState({ ...wsMod.freshWs('A'), draftId: 'd1' });
      m.pull.mockRejectedValue(new Error('network'));
      const job = note({ id: 'n8', kind: 'job', jobKind: 'options', jobStatus: 'done', planId: null, reportId: null, draftId: 'd1' });
      await expect(act.readViewed(new QueryClient(), A1, job, () => true)).rejects.toThrow('network');
      expect(m.read).not.toHaveBeenCalled();
    });

    it('받는 사이 화면을 떠나면 읽음으로 바꾸지 않는다', async () => {
      m.get.mockResolvedValue(server({}));
      expect(await act.readViewed(qcAndSeed(), A1, comment(), () => false)).toBe(false);
      expect(m.read).not.toHaveBeenCalled();
    });

    it('받는 사이 로그인이 바뀌면 읽음으로 바꾸지 않는다', async () => {
      m.get.mockImplementation(async () => {
        m.seq = 2;
        return server({});
      });
      expect(await act.readViewed(qcAndSeed(), A1, comment(), () => true)).toBe(false);
      expect(m.read).not.toHaveBeenCalled();
    });
  });

  it('받는 사이 로그인이 바뀌면 넣지 않는다', async () => {
    seed(rec('p1', 'active', '저장 전 새 답변'));
    m.get.mockImplementation(async () => {
      m.seq = 2;
      return server({ comments: [{ id: 'c1' }] as unknown as PlanRecord['comments'] });
    });
    await act.refreshTarget(new QueryClient(), A1, note({ kind: 'comment', audience: 'member', reportId: null }));
    expect(wsMod.ws().plans.p1.comments).toBeUndefined();
  });
});

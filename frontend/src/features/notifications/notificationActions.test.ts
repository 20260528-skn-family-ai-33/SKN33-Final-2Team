/* PR #84 리뷰 3건: 계정이 바뀐 뒤 늦게 온 읽음 응답(P1) · 부서장 직원 기록 캐시 갱신(P2) · 본인 알림이 작성 중인 초안을 덮지 않음(P2) */
import { QueryClient } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppNotification, NotificationInbox } from '@/api/types/notification';
import type { PlanRecord, Report } from '@/api/types/plan';

const m = vi.hoisted(() => ({ me: { id: 'A' } as { id: string } | null, read: vi.fn(), readAll: vi.fn(), get: vi.fn(), reports: vi.fn() }));
vi.mock('@/shared/state/session', () => ({ me: () => m.me, isSup: () => true }));
vi.mock('@/api/endpoints/notifications', () => ({ notificationsApi: { read: m.read, readAll: m.readAll } }));
vi.mock('@/api/endpoints/plans', () => ({ plansApi: { get: m.get, reports: m.reports } }));
vi.mock('@/shared/state/catalog', () => ({ mergeRes: vi.fn(), mergeReg: vi.fn() }));

type Actions = typeof import('./notificationActions');
type Ws = typeof import('@/shared/state/workspace');
let act: Actions;
let wsMod: Ws;

const box = (title: string): NotificationInbox => ({ items: [{ id: 'n1', planTitle: title } as AppNotification], unread: 1 });
const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
};
const note = (o: Partial<AppNotification>): AppNotification =>
  ({ id: 'n1', kind: 'report', audience: 'self', employee: { id: '8', name: '김직원' }, planId: 'p1', planTitle: '', track: '', reportId: 'r-new', createdAt: '', read: false, ...o }) as AppNotification;
const rec = (id: string, status: string) => ({ id, status, revision: null, pending: null, post: null }) as unknown as PlanRecord;
const rep = (id: string, planId: string) => ({ id, planId }) as Report;

beforeEach(async () => {
  vi.resetModules();
  vi.resetAllMocks();
  m.me = { id: 'A' };
  act = await import('./notificationActions');
  wsMod = await import('@/shared/state/workspace');
});

describe('P1 계정별 알림 캐시', () => {
  it('직원마다 다른 캐시 키를 쓴다', () => {
    expect(act.notificationKey('A')).not.toEqual(act.notificationKey('B'));
  });

  it('모두 읽음 응답이 오기 전에 다른 계정으로 바뀌면 응답을 어느 캐시에도 넣지 않는다', async () => {
    const qc = new QueryClient();
    const late = deferred<NotificationInbox>();
    m.readAll.mockReturnValue(late.promise);
    const pending = act.markRead(qc, 'A');
    m.me = { id: 'B' }; // A 로그아웃 → B 로그인
    late.resolve(box('A만 볼 수 있는 로드맵'));
    expect(await pending).toBe(false);
    expect(qc.getQueryData(act.notificationKey('B'))).toBeUndefined();
    expect(qc.getQueryData(act.notificationKey('A'))).toBeUndefined();
  });

  it('같은 직원이면 그 직원 캐시에만 넣는다', async () => {
    const qc = new QueryClient();
    m.read.mockResolvedValue(box('내 로드맵'));
    expect(await act.markRead(qc, 'A', 'n1')).toBe(true);
    expect(m.read).toHaveBeenCalledWith('n1');
    expect(qc.getQueryData(act.notificationKey('A'))).toEqual(box('내 로드맵'));
    expect(qc.getQueryData(act.notificationKey('B'))).toBeUndefined();
  });
});

describe('P2 부서장 알림: 이동 전에 그 직원 기록을 새로 받는다', () => {
  it('화면에서 쓰지 않고 캐시에만 남은 옛 기록도 다시 받아, 새 보고서가 들어 있게 한다', async () => {
    const { memberKey } = await import('@/features/team/teamData');
    const qc = new QueryClient();
    const fetchMember = vi.fn().mockResolvedValueOnce({ reports: [rep('r-old', 'p1')] }).mockResolvedValueOnce({ reports: [rep('r-new', 'p1')] });
    await qc.fetchQuery({ queryKey: memberKey('8'), queryFn: fetchMember });
    await act.refreshTarget(qc, 'A', note({ audience: 'head' }));
    expect(fetchMember).toHaveBeenCalledTimes(2);
    expect(qc.getQueryData<{ reports: Report[] }>(memberKey('8'))?.reports[0].id).toBe('r-new');
    expect(m.get).not.toHaveBeenCalled(); // 부서장은 본인 작업 공간을 건드리지 않는다
  });
});

describe('P2 본인 알림: 그 로드맵·보고서만 합치고 작성 중인 초안은 그대로', () => {
  const seed = () =>
    wsMod.useWs.setState(
      {
        ...wsMod.freshWs('A'),
        draft: { ...wsMod.freshDraft(), goal: '아직 저장 안 된 작성 중 목표' },
        plans: { p1: rec('p1', 'active'), p2: rec('p2', 'active') },
        reports: [rep('r-old', 'p1'), rep('r-other', 'p2')],
      },
      true,
    );

  it('보고서 알림: 로드맵과 그 로드맵 보고서만 바꾸고 초안·다른 로드맵은 그대로 둔다', async () => {
    seed();
    m.get.mockResolvedValue({ plan: rec('p1', 'done') });
    m.reports.mockResolvedValue([rep('r-new', 'p1')]);
    await act.refreshTarget(new QueryClient(), 'A', note({}));
    const s = wsMod.ws();
    expect(s.draft.goal).toBe('아직 저장 안 된 작성 중 목표');
    expect(s.plans.p1.status).toBe('done');
    expect(s.plans.p2.status).toBe('active');
    expect(s.reports.map((r) => r.id)).toEqual(['r-new', 'r-other']);
    expect(m.reports).toHaveBeenCalledWith('p1');
  });

  it('로드맵 알림은 보고서를 다시 받지 않는다', async () => {
    seed();
    m.get.mockResolvedValue({ plan: rec('p1', 'active') });
    await act.refreshTarget(new QueryClient(), 'A', note({ kind: 'roadmap', reportId: null }));
    expect(m.reports).not.toHaveBeenCalled();
    expect(wsMod.ws().reports.map((r) => r.id)).toEqual(['r-old', 'r-other']);
  });

  it('받는 사이 다른 계정으로 바뀌면 작업 공간에 넣지 않는다', async () => {
    seed();
    const late = deferred<{ plan: PlanRecord }>();
    m.get.mockReturnValue(late.promise);
    m.reports.mockResolvedValue([rep('r-new', 'p1')]);
    const pending = act.refreshTarget(new QueryClient(), 'A', note({}));
    m.me = { id: 'B' };
    late.resolve({ plan: rec('p1', 'done') });
    await pending;
    expect(wsMod.ws().plans.p1.status).toBe('active');
    expect(wsMod.ws().reports.map((r) => r.id)).toEqual(['r-old', 'r-other']);
  });
});

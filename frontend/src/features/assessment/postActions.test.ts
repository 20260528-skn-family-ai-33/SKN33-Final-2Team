/* 사후 점검 응답 저장이 실패하면 결과 보고서를 만들지 않는다 — 서버에 남은 예전 응답으로 보고서가 나오지 않게(PR #23 리뷰 2026-10-27) */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/client';
import type { PlanRecord } from '@/api/types/plan';

const api = vi.hoisted(() => ({ savePost: vi.fn(), makeReport: vi.fn(), toast: vi.fn(), takePlan: vi.fn() }));
vi.mock('@/api/endpoints/plans', () => ({ plansApi: { savePost: api.savePost, makeReport: api.makeReport } }));
vi.mock('@/api/jobs', () => ({ waitJob: vi.fn(() => new Promise(() => {})) }));
vi.mock('@/features/roadmap/planActions', () => ({ takePlan: api.takePlan, pullPlan: vi.fn(async () => null) }));
vi.mock('@/features/draft/draftSync', () => ({ reloadWorkspace: vi.fn() }));
vi.mock('@/shared/lib/fail', () => ({ failToast: api.toast }));

type Actions = typeof import('./postActions');
type Ws = typeof import('@/shared/state/workspace');
let act: Actions;
let wsMod: Ws;
const go = vi.fn();

beforeEach(async () => {
  vi.resetModules();
  vi.resetAllMocks(); // 앞 시험에서 다 쓰지 않은 응답(…Once)이 넘어오지 않게
  act = await import('./postActions');
  wsMod = await import('@/shared/state/workspace');
  // 화면에서 사후 응답을 q1=4 로 바꾼 상태(서버에는 예전에 다 채운 응답이 있다고 가정)
  const R = { id: 'p1', post: { answers: { q1: 4 }, goalSelf: '3', deep: null, running: false, fail: null, jobId: null, file: null } } as unknown as PlanRecord;
  wsMod.useWs.setState({ ...wsMod.freshWs('u1'), plans: { p1: R } }, true);
});

describe('사후 점검 저장 실패 뒤 보고서 막기', () => {
  it('저장이 503 으로 실패하면 보고서를 요청하지 않고 입력과 상태를 그대로 둔다', async () => {
    api.savePost.mockRejectedValue(new ApiError(503, { message: '잠시 뒤 다시 시도해 주세요' }));
    await act.makeReport(go as never, 'p1');
    expect(api.makeReport).not.toHaveBeenCalled();
    const post = wsMod.ws().plans.p1.post;
    expect(post.running).toBe(false);
    expect(post.answers).toEqual({ q1: 4 });
    expect(api.toast).toHaveBeenCalledTimes(1);
  });

  it('savePost 는 실패하면 false, 성공하면 true 를 돌려준다', async () => {
    api.savePost.mockRejectedValueOnce(new ApiError(503, {})).mockResolvedValueOnce({});
    expect(await act.savePost('p1')).toBe(false);
    expect(await act.savePost('p1')).toBe(true);
  });

  it('저장에 성공하면 보고서를 한 번 요청하고 진행 중으로 바꾼다', async () => {
    api.savePost.mockResolvedValue({});
    api.makeReport.mockResolvedValue({ jobId: 'j1' });
    await act.makeReport(go as never, 'p1');
    expect(api.savePost.mock.calls[0][1]).toMatchObject({ answers: { q1: 4 } });
    expect(api.makeReport).toHaveBeenCalledTimes(1);
    expect(wsMod.ws().plans.p1.post.running).toBe(true);
  });
});

/* 사전 점검에서 세부 질문을 고른 로드맵: 사후 심화 문항이 준비되면 저장 뒤 화면의 심화 답을 다시 넣는다(immer 상태 · 이슈 #48) */
describe('사후 심화 문항이 준비된 로드맵의 저장', () => {
  const deep = (mcq: Record<string, string>, essay: Record<string, string>) => ({ status: 'ready', judge: null, mcq, essay });

  beforeEach(() => {
    wsMod.updateWs((s) => void (s.plans.p1.post.deep = deep({ m1: 'a' }, { e1: '처음 답' })));
    // 실제 takePlan 처럼 서버 응답(JSON)으로 만든 새 객체로 바꾼다. 서버 응답은 보낼 때의 심화 답을 담고 있다
    api.takePlan.mockImplementation(() => wsMod.updateWs((s) => void (s.plans.p1.post.deep = deep({ m1: 'a' }, { e1: '처음 답' }))));
  });

  it('저장에 성공하면 알림 없이 true 를 돌려주고, 보내는 사이 더 쓴 서술형을 서버 응답이 덮지 않는다', async () => {
    api.savePost.mockImplementation(async () => {
      wsMod.updateWs((s) => void (s.plans.p1.post.deep!.essay = { e1: '처음 답에 더 쓴 답' }));
      return {};
    });
    expect(await act.savePost('p1')).toBe(true);
    expect(api.toast).not.toHaveBeenCalled();
    expect(api.savePost.mock.calls[0][1]).toMatchObject({ deepMcq: { m1: 'a' }, deepEssay: { e1: '처음 답' } });
    expect(wsMod.ws().plans.p1.post.deep).toMatchObject({ mcq: { m1: 'a' }, essay: { e1: '처음 답에 더 쓴 답' } });
  });

  it('저장에 성공하면 결과 보고서를 요청한다', async () => {
    api.savePost.mockResolvedValue({});
    api.makeReport.mockResolvedValue({ jobId: 'j1' });
    await act.makeReport(go as never, 'p1');
    expect(api.toast).not.toHaveBeenCalled();
    expect(api.makeReport).toHaveBeenCalledTimes(1);
    expect(wsMod.ws().plans.p1.post.running).toBe(true);
  });
});

/* 작성 문서 저장 실패 뒤에는 다음 작업(에이전트 호출·안 고르기·확정)을 하지 않는다 — 서버의 예전 값으로 생성되지 않게(PR #23 리뷰 2026-10-27) */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ patch: vi.fn(), create: vi.fn(), get: vi.fn(), toast: vi.fn() }));
vi.mock('@/api/endpoints/drafts', () => ({ draftsApi: { patch: api.patch, create: api.create, get: api.get } }));
vi.mock('@/shared/lib/fail', () => ({ failToast: api.toast }));

type Sync = typeof import('./draftSync');
type Ws = typeof import('@/shared/state/workspace');
let sync: Sync;
let wsMod: Ws;
// 모듈을 매번 새로 불러오므로 코드와 같은 ApiError 클래스를 쓴다(404 판단이 instanceof)
let ApiError: typeof import('@/api/client').ApiError;

const saved = (draftId: string) => ({ draftId, draft: { ...wsMod.freshDraft(), goal: '새 목표' } });

beforeEach(async () => {
  vi.resetModules();
  vi.resetAllMocks(); // 앞 시험에서 다 쓰지 않은 응답(…Once)이 넘어오지 않게
  sync = await import('./draftSync');
  wsMod = await import('@/shared/state/workspace');
  ({ ApiError } = await import('@/api/client'));
  // 서버에는 예전 목표가 있고, 화면에서 목표를 바꾼 상태
  wsMod.useWs.setState({ ...wsMod.freshWs('u1'), draftId: 'd1', draft: { ...wsMod.freshDraft(), goal: '새 목표' } }, true);
});

describe('저장 실패 뒤 진행 막기', () => {
  it('저장이 503 으로 실패하면 draftCall 은 다음 호출을 하지 않고, 알림은 한 번만 띄운다', async () => {
    api.patch.mockRejectedValue(new ApiError(503, { message: '잠시 뒤 다시 시도해 주세요' }));
    const next = vi.fn();
    expect(await sync.draftCall('문항을 만들지 못했어요', next)).toBeNull();
    expect(next).not.toHaveBeenCalled();
    expect(api.toast).toHaveBeenCalledTimes(1);
    expect(api.toast.mock.calls[0][1]).toBe('작성 내용을 저장하지 못했어요');
  });

  it('flush 는 저장 실패를 DraftSaveError 로 알린다(안 고르기·확정이 멈춤)', async () => {
    api.patch.mockRejectedValue(new ApiError(503, {}));
    await expect(sync.flush()).rejects.toBeInstanceOf(sync.DraftSaveError);
  });

  it('실패 뒤 다음 저장이 성공하면 같은 입력을 다시 보내고 진행한다', async () => {
    api.patch.mockRejectedValueOnce(new ApiError(503, {})).mockResolvedValueOnce(saved('d1'));
    const next = vi.fn(async () => ({}));
    expect(await sync.draftCall('문항을 만들지 못했어요', next)).toBeNull();
    await sync.draftCall('문항을 만들지 못했어요', next);
    expect(api.patch).toHaveBeenCalledTimes(2);
    expect(api.patch.mock.calls[1][1]).toMatchObject({ goal: '새 목표' });
    expect(next).toHaveBeenCalledTimes(1);
    expect(next).toHaveBeenCalledWith('d1');
  });

  it('작성 문서가 서버에서 없어졌으면(404) 지금 입력으로 새로 만들고 진행한다', async () => {
    api.patch.mockRejectedValue(new ApiError(404, {}));
    api.create.mockResolvedValue(saved('d2'));
    const next = vi.fn(async () => ({}));
    await sync.draftCall('문항을 만들지 못했어요', next);
    expect(api.create).toHaveBeenCalledTimes(1);
    expect(next).toHaveBeenCalledWith('d2');
    expect(api.toast).not.toHaveBeenCalled();
  });
});


describe('새 작성 건의 시작 방식 저장', () => {
  beforeEach(() => wsMod.useWs.setState({ ...wsMod.freshWs('u1'), draftId: null, draft: wsMod.freshDraft() }, true));

  it('목표를 입력하기 전이어도 고른 시작 방식만으로 작성 문서를 만들어 새로고침 뒤에도 남긴다', async () => {
    api.create.mockResolvedValue({ draftId: 'd9', draft: { ...wsMod.freshDraft(), startMode: 'after' } });
    wsMod.updateWs((s) => void (s.draft.startMode = 'after'));
    await sync.flush();
    expect(api.create).toHaveBeenCalledTimes(1);
    expect(api.create.mock.calls[0][0].draft).toMatchObject({ startMode: 'after', goal: '' });
    expect(wsMod.ws().draftId).toBe('d9');
    expect(wsMod.ws().draft.startMode).toBe('after');
  });

  it('시작 방식을 고르지 않았고 입력도 없으면 작성 문서를 만들지 않는다', async () => {
    await sync.flush();
    expect(api.create).not.toHaveBeenCalled();
    expect(wsMod.ws().draftId).toBeNull();
  });
});

describe('조회 실패 전달 (PR #139 리뷰)', () => {
  it('네트워크 오류: pullDraftOrThrow 는 던지고 pullDraft 는 넘어가며, 작성 중인 문서는 그대로 둔다', async () => {
    api.get.mockRejectedValue(new ApiError(503, { message: '잠시 뒤 다시 시도해 주세요' }));
    await expect(sync.pullDraftOrThrow()).rejects.toBeInstanceOf(ApiError);
    await expect(sync.pullDraft()).resolves.toBe(true);
    expect(wsMod.ws().draftId).toBe('d1');
    expect(wsMod.ws().draft.goal).toBe('새 목표');
  });

  it('문서가 없어졌으면(404) 둘 다 던지지 않고 작성 문서를 비운다', async () => {
    api.get.mockRejectedValue(new ApiError(404, { message: '없음' }));
    await expect(sync.pullDraftOrThrow()).resolves.toBe(true);
    expect(wsMod.ws().draftId).toBeNull();
  });
});

describe('늦은 조회 응답의 단계 되돌림 방지', () => {
  it('자료 저장 전에 시작한 조회가 늦게 끝나도 6번 완료 상태를 해제하지 않는다', async () => {
    wsMod.updateWs(s=>{s.draft.chosen='A1';s.draft.v2Assessment={generationId:'g',completed:true,materialsReady:false};});
    const old={draftId:'d1',draft:structuredClone(wsMod.ws().draft),draftPlan:null};
    let finish!:(value:unknown)=>void;api.get.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
    const pending=sync.pullDraft();
    wsMod.updateWs(s=>{s.draft.v2Assessment={generationId:'g',completed:true,materialsReady:true,materialsKey:'new'};});
    finish(old);await pending;
    expect(wsMod.ws().draft.v2Assessment?.materialsReady).toBe(true);
    expect(wsMod.ws().draft.v2Assessment?.materialsKey).toBe('new');
  });
});

describe('점검 완료 직후 전환', () => {
  it('실제 스토어에서 응답 변경 표시를 해제하여 다음 자동 저장이 완료 상태를 되돌리지 않는다', () => {
    wsMod.updateWs(s=>{s.pendingFlow='answers';s.draft.detailsOk=true;s.draft.v2Assessment={generationId:'g',completed:false};});
    const completed={draftId:'d1',draft:{...wsMod.ws().draft,v2Assessment:{generationId:'g',completed:true}},draftPlan:null};
    sync.takeDraft(completed);
    expect(wsMod.ws().pendingFlow).toBeUndefined();
    expect(wsMod.ws().draft.v2Assessment?.completed).toBe(true);
    sync.takeDraft(completed,true);
    expect(wsMod.ws().draft.v2Assessment?.completed).toBe(true);
  });
});

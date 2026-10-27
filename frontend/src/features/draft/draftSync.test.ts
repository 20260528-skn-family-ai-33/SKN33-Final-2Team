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

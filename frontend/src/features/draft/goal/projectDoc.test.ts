import { beforeEach, expect, it, vi } from 'vitest';
import { draftsApi } from '@/api/endpoints/drafts';
import type { DraftResponse } from '@/api/types/draft';
import { freshWs, updateWs, useWs, ws } from '@/shared/state/workspace';
import { blockedTo } from '../model';
import { takeDraft } from '../draftSync';
import { useGoalStore } from './goalStore';
import { clearProject, docDoneText, uploadProject } from './projectDoc';

vi.mock('@/shared/state/session', () => ({ me: () => ({ id: 'u' }) }));
vi.mock('../draftSync', () => ({
  DraftSaveError: class extends Error { original: unknown = null; },
  ensureDraft: vi.fn(async () => 'd'),
  takeDraft: vi.fn(),
  draftCall: vi.fn(async () => null),
}));

const file = (name: string) => new File(['기획서'], name, { type: 'text/plain' });
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((ok, no) => { resolve = ok; reject = no; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.mocked(takeDraft).mockClear();
  useWs.setState(freshWs('u'));
  updateWs((s) => { s.draftId = 'd'; s.draft.goal = '점검 절차 검색'; });
  useGoalStore.setState({ gs: null, docErr: null });
});

it('올리는 동안과 요약하는 동안 1단계를 마치지 않은 것으로 보고, 올리는 동안 빼기·다른 파일 올리기를 막는다', async () => {
  const upload = deferred<DraftResponse>();
  const post = vi.spyOn(draftsApi, 'projectFile').mockReturnValue(upload.promise);
  const first = uploadProject(file('first.txt'));
  await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(ws().docUpload).not.toBeNull();
  expect(blockedTo(ws(), 'details')).toBe('/new/goal');

  expect(await uploadProject(file('second.txt'))).toBe(false);
  await clearProject();
  expect(post).toHaveBeenCalledTimes(1);
  expect(ws().draft.project?.name).toBe('first.txt');

  upload.resolve({ draftId: 'd' } as DraftResponse);
  expect(await first).toBe(true);
  expect(takeDraft).toHaveBeenCalledTimes(1);
  expect(ws().docUpload).toBeNull();
  // 업로드가 끝나도 요약 중이면 상단 단계·주소 진입도 하단 버튼처럼 막는다
  expect(ws().draft.doc?.status).toBe('reading');
  expect(blockedTo(ws(), 'details')).toBe('/new/goal');
  updateWs((s) => { s.draft.doc = { name: 'first.txt', status: 'ok', summary: '요약' }; });
  expect(blockedTo(ws(), 'details')).toBeNull();
  updateWs((s) => { s.draft.doc = { name: 'first.txt', status: 'fail', step: 'summary' }; });
  expect(blockedTo(ws(), 'details')).toBeNull();
});

it('업로드가 실패하면 그 파일만 지우고 안내를 남긴 뒤 막음을 푼다', async () => {
  vi.spyOn(draftsApi, 'projectFile').mockRejectedValue(new Error('422'));
  await uploadProject(file('broken.txt'));
  expect(ws().draft.project).toBeNull();
  expect(ws().draft.doc).toBeNull();
  expect(useGoalStore.getState().docErr?.name).toBe('broken.txt');
  expect(ws().docUpload).toBeNull();
});

it('계정이 바뀐 뒤 늦게 끝난 업로드는 새 상태에 반영하지 않는다', async () => {
  const upload = deferred<DraftResponse>();
  vi.spyOn(draftsApi, 'projectFile').mockReturnValue(upload.promise);
  const pending = uploadProject(file('late.txt'));
  await vi.waitFor(() => expect(ws().docUpload).not.toBeNull());
  useWs.setState(freshWs('other'));
  upload.reject(new Error('late failure'));
  await pending;
  expect(useGoalStore.getState().docErr).toBeNull();
  expect(takeDraft).not.toHaveBeenCalled();
  expect(ws().owner).toBe('other');
  expect(ws().docUpload).toBeNull();
});

it('완료 상자와 알림은 같은 조건(요약 글 유무)으로 문구를 고른다', () => {
  const summarized = docDoneText({ summary: '점검 절차 RAG 도우미 기획' });
  expect(summarized.title).toBe('기획서 요약 완료');
  expect(summarized.toast).toContain('요약을 마쳤어요');
  for (const summary of ['', '   ', undefined]) {
    const empty = docDoneText({ summary });
    expect(empty.title).toBe('기획서 읽기 완료');
    expect(empty.toast).toContain('찾지 못했어요');
    expect(empty.toast).not.toContain('요약을 마쳤어요');
  }
});

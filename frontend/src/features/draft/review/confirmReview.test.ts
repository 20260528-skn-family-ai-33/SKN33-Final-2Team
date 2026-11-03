import { beforeEach, expect, it, vi } from 'vitest';
const mock=vi.hoisted(()=>({
  state:{owner:'u' as string|null,draftId:'d' as string|null,lastNew:'old' as string|null,draft:{goal:'검색 구현',prefs:{hours:4},chosen:'A1',v2Assessment:{generationId:'g',materialsKey:'m'}}},
  flush:vi.fn(),confirm:vi.fn(),reload:vi.fn(),toast:vi.fn(),
}));
vi.mock('@/shared/state/workspace',()=>({ws:()=>mock.state,updateWs:(fn:(s:typeof mock.state)=>void)=>fn(mock.state)}));
vi.mock('@/api/endpoints/drafts',()=>({draftsApi:{confirm:mock.confirm}}));
vi.mock('@/shared/lib/fail',()=>({failToast:mock.toast}));
vi.mock('../draftSync',()=>({flush:mock.flush,reloadWorkspace:mock.reload,DraftSaveError:class extends Error{}}));
import { confirmReview } from './confirmReview';
function deferred<T>() {let resolve!:(value:T)=>void; const work=new Promise<T>(done=>{resolve=done;});return {work,resolve};}
beforeEach(()=>{
  vi.resetAllMocks();mock.state.owner='u';mock.state.draftId='d';mock.state.lastNew='old';mock.state.draft.goal='검색 구현';mock.state.draft.chosen='A1';
  mock.flush.mockResolvedValue(undefined);mock.confirm.mockResolvedValue({planId:'plan'});mock.reload.mockResolvedValue(true);
});
it('연속 확정 클릭은 산출물 저장·확정·화면 이동을 각각 한 번만 실행한다',async()=>{
  const pending=deferred<boolean>(),save=vi.fn(()=>pending.work),go=vi.fn();
  const first=confirmReview(go,save),second=confirmReview(go,save);
  await vi.waitFor(()=>expect(save).toHaveBeenCalledOnce());expect(mock.confirm).not.toHaveBeenCalled();pending.resolve(true);
  expect(await first).toBe(true);expect(await second).toBe(true);
  expect(mock.confirm).toHaveBeenCalledExactlyOnceWith('d');expect(mock.reload).toHaveBeenCalledOnce();expect(go).toHaveBeenCalledExactlyOnceWith('/roadmaps/plan/confirmed',{force:true});
});
it('자동 저장 대기 중 입력이 바뀌면 산출물 저장·확정을 시작하지 않는다',async()=>{
  const pending=deferred<void>();mock.flush.mockReturnValue(pending.work);const save=vi.fn(),go=vi.fn();
  const work=confirmReview(go,save);await Promise.resolve();mock.state.draft.goal='다른 목표';pending.resolve();
  expect(await work).toBe(false);expect(save).not.toHaveBeenCalled();expect(mock.confirm).not.toHaveBeenCalled();expect(go).not.toHaveBeenCalled();
});
it('산출물 저장 중 코스가 바뀌면 이전 선택을 확정하지 않는다',async()=>{
  const pending=deferred<boolean>(),go=vi.fn();const work=confirmReview(go,()=>pending.work);
  await vi.waitFor(()=>expect(mock.flush).toHaveBeenCalled());mock.state.draft.chosen='A3';pending.resolve(true);
  expect(await work).toBe(false);expect(mock.confirm).not.toHaveBeenCalled();expect(go).not.toHaveBeenCalled();
});
it('산출물 저장 실패 시 확정을 막고 다음 명시적 시도를 허용한다',async()=>{
  const go=vi.fn();expect(await confirmReview(go,async()=>false)).toBe(false);expect(mock.confirm).not.toHaveBeenCalled();
  expect(await confirmReview(go,async()=>true)).toBe(true);expect(mock.confirm).toHaveBeenCalledOnce();
});
it('확정 응답 도착 전 직원·초안이 바뀌면 새 작업 공간을 덮어쓰지 않는다',async()=>{
  const pending=deferred<{planId:string}>();mock.confirm.mockReturnValue(pending.work);const go=vi.fn();const work=confirmReview(go);
  await vi.waitFor(()=>expect(mock.confirm).toHaveBeenCalled());mock.state.owner='other';mock.state.draftId='other';pending.resolve({planId:'old-plan'});
  expect(await work).toBe(false);expect(mock.reload).not.toHaveBeenCalled();expect(go).not.toHaveBeenCalled();expect(mock.state.lastNew).toBe('old');
});
it('작업 공간 조회가 현재 입력에 맞지 않으면 완료 화면으로 이동하지 않는다',async()=>{
  mock.reload.mockImplementation(async(accept:()=>boolean)=>{mock.state.draft.chosen='A3';return accept();});const go=vi.fn();
  expect(await confirmReview(go)).toBe(false);expect(go).not.toHaveBeenCalled();expect(mock.state.lastNew).toBe('old');
});
it('확정 오류는 자동 재시도하지 않고 사용자가 다시 클릭할 때만 재시도한다',async()=>{
  mock.confirm.mockRejectedValueOnce(Error('offline')).mockResolvedValue({planId:'plan'});const go=vi.fn();
  expect(await confirmReview(go)).toBe(false);expect(mock.confirm).toHaveBeenCalledOnce();expect(mock.toast).toHaveBeenCalledOnce();
  expect(await confirmReview(go)).toBe(true);expect(mock.confirm).toHaveBeenCalledTimes(2);
});

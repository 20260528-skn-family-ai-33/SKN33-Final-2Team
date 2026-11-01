import { beforeEach, expect, it, vi } from 'vitest';
const mock=vi.hoisted(()=>({flush:vi.fn(),takeDraft:vi.fn(),get:vi.fn(),state:{draftId:'d',draft:{goal:'검색 구현',project:null,prefs:{hours:4},chosen:'A1'}}}));
vi.mock('../draftSync',()=>({flush:mock.flush,takeDraft:mock.takeDraft}));
vi.mock('@/api/endpoints/drafts',()=>({draftsApi:{get:mock.get}}));
vi.mock('@/shared/state/workspace',()=>({ws:()=>mock.state}));
import { completeMaterialSelection } from './materialTransition';
beforeEach(()=>{vi.resetAllMocks();mock.state.draft.chosen='A1';mock.flush.mockResolvedValue(undefined);});
const ready=()=>({draftId:'d',draft:{...mock.state.draft,v2Assessment:{generationId:'g',completed:true,materialsReady:true}},draftPlan:{opt:'A1'}});
it('이전 자동 저장이 끝나기 전에는 자료 저장이나 화면 이동을 시작하지 않는다',async()=>{
 let finish!:()=>void;mock.flush.mockReturnValue(new Promise<void>(resolve=>{finish=resolve;}));
 const save=vi.fn().mockResolvedValue(true),go=vi.fn();mock.get.mockResolvedValue(ready());
 const work=completeMaterialSelection(save,go);expect(save).not.toHaveBeenCalled();expect(go).not.toHaveBeenCalled();
 finish();await work;expect(save).toHaveBeenCalledOnce();expect(mock.takeDraft).toHaveBeenCalledOnce();expect(go).toHaveBeenCalledWith('/new/review');
});
it('조회 도중 계획이 바뀌면 오래된 결과로 검토 화면에 진입하지 않는다',async()=>{
 let finish!:(value:unknown)=>void;const old=ready();mock.get.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
 const go=vi.fn();const work=completeMaterialSelection(vi.fn().mockResolvedValue(true),go);
 await vi.waitFor(()=>expect(mock.get).toHaveBeenCalled());mock.state.draft.chosen='A3';finish(old);
 await expect(work).rejects.toThrow('검토 계획');expect(go).not.toHaveBeenCalled();expect(mock.takeDraft).not.toHaveBeenCalled();
});
it('자료 저장 실패나 저장되지 않은 자료로 넘어가지 않는다',async()=>{
 const go=vi.fn();expect(await completeMaterialSelection(vi.fn().mockResolvedValue(false),go)).toBe(false);
 mock.get.mockResolvedValue({...ready(),draft:{...ready().draft,v2Assessment:{materialsReady:false}}});
 await expect(completeMaterialSelection(vi.fn().mockResolvedValue(true),go)).rejects.toThrow('검토 계획');expect(go).not.toHaveBeenCalled();
});

it('7단계 결과가 아직 없어도 자료 저장이 확인되면 검토 화면으로 이동한다',async()=>{
 const go=vi.fn();mock.get.mockResolvedValue({...ready(),draftPlan:null});
 expect(await completeMaterialSelection(vi.fn().mockResolvedValue(true),go)).toBe(true);
 expect(go).toHaveBeenCalledWith('/new/review');
});

import { beforeEach, expect, it, vi } from 'vitest';
const mock = vi.hoisted(()=>({state:{owner:'u',draftId:'d',draft:{goal:'goal',doc:{status:'ok',summary:'original'}}},flush:vi.fn(),patch:vi.fn(),take:vi.fn()}));
vi.mock('@/shared/state/workspace',()=>({ws:()=>mock.state}));
vi.mock('@/api/endpoints/drafts',()=>({draftsApi:{patch:mock.patch}}));
vi.mock('../draftSync',()=>({flush:mock.flush,takeDraft:mock.take}));
vi.mock('../invalidation',()=>({inputSignature:(draft:unknown)=>JSON.stringify(draft)}));
import {saveProjectSummary} from './projectSummary';
beforeEach(()=>{
  vi.resetAllMocks();
  mock.state={owner:'u',draftId:'d',draft:{goal:'goal',doc:{status:'ok',summary:'original'}}};
  mock.flush.mockResolvedValue(undefined);mock.patch.mockResolvedValue({draft:{doc:{summary:'changed'},gen:null}});
});
it('unchanged summary does not save or invalidate results',async()=>{
  expect(await saveProjectSummary('original')).toBe(false);
  expect(mock.patch).not.toHaveBeenCalled();expect(mock.take).not.toHaveBeenCalled();
});
it('changed summary applies the server response only after successful save',async()=>{
  expect(await saveProjectSummary('changed')).toBe(true);
  expect(mock.patch).toHaveBeenCalledWith('d',{docSummary:'changed'});
  expect(mock.take).toHaveBeenCalledWith({draft:{doc:{summary:'changed'},gen:null}});
  expect(mock.state.draft.doc.summary).toBe('original');
});
it('save failure preserves original state and permits retry',async()=>{
  mock.patch.mockRejectedValueOnce(new Error('network'));
  await expect(saveProjectSummary('changed')).rejects.toThrow('network');
  expect(mock.state.draft.doc.summary).toBe('original');expect(mock.take).not.toHaveBeenCalled();
  expect(await saveProjectSummary('changed')).toBe(true);
});
it('input change while flushing prevents the old request',async()=>{
  mock.flush.mockImplementation(async()=>{mock.state.draft.goal='other';});
  await expect(saveProjectSummary('changed')).rejects.toThrow('입력 내용이 바뀌었어요');
  expect(mock.patch).not.toHaveBeenCalled();
});
it('late response cannot overwrite another draft',async()=>{
  mock.patch.mockImplementation(async()=>{mock.state.draftId='other';return {draft:{}};});
  await expect(saveProjectSummary('changed')).rejects.toThrow('이전 저장 응답');
  expect(mock.take).not.toHaveBeenCalled();
});
it('reading or invalid summary never calls save',async()=>{
  for(const value of ['', 'x'.repeat(1501)]) await expect(saveProjectSummary(value)).rejects.toThrow();
  mock.state.draft.doc.status='reading';await expect(saveProjectSummary('changed')).rejects.toThrow('요약 준비');
  expect(mock.patch).not.toHaveBeenCalled();
});

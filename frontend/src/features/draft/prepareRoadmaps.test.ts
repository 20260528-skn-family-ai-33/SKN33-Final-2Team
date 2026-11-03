import { afterEach,expect,it,vi } from 'vitest';
const mocks=vi.hoisted(()=>({state:{owner:'u',draftId:'d',draft:{goal:'goal',v2Assessment:{generationId:'g',completed:true}}},start:vi.fn(),take:vi.fn()}));
vi.mock('@/shared/state/workspace',()=>({ws:()=>mocks.state}));
vi.mock('@/api/endpoints/drafts',()=>({draftsApi:{optionsStart:mocks.start}}));
vi.mock('./draftSync',()=>({flush:async()=>{},ensureDraft:async()=>mocks.state.draftId,takeDraft:mocks.take}));
vi.mock('./invalidation',()=>({inputSignature:(draft:{goal:string})=>draft.goal}));
import { prepareRoadmaps } from './prepareRoadmaps';
afterEach(()=>{vi.clearAllMocks();});
it('completion and result screen share one background request',async()=>{
 let finish!:(v:unknown)=>void;mocks.state.draft.v2Assessment.generationId='one';mocks.start.mockReturnValue(new Promise(r=>{finish=r;}));
 const first=prepareRoadmaps(),second=prepareRoadmaps();await vi.waitFor(()=>expect(mocks.start).toHaveBeenCalledOnce());finish({draft:{}});await Promise.all([first,second]);expect(mocks.take).toHaveBeenCalledOnce();
});
it('late response cannot overwrite changed inputs',async()=>{
 let finish!:(v:unknown)=>void;mocks.state.draft.v2Assessment.generationId='two';mocks.start.mockReturnValue(new Promise(r=>{finish=r;}));
 const work=prepareRoadmaps();await vi.waitFor(()=>expect(mocks.start).toHaveBeenCalledOnce());mocks.state.draft.goal='changed';finish({draft:{}});await work;expect(mocks.take).not.toHaveBeenCalled();
});
it('failed background generation does not silently retry when results mount',async()=>{
 mocks.state.draft.v2Assessment.generationId='failed';mocks.start.mockRejectedValue(new Error('failed'));
 await expect(prepareRoadmaps()).rejects.toThrow('failed');await expect(prepareRoadmaps()).rejects.toThrow('failed');expect(mocks.start).toHaveBeenCalledOnce();
});

it('already generated plans are reused without another POST',async()=>{
 Object.assign(mocks.state.draft,{gen:{options:{}}});await prepareRoadmaps();expect(mocks.start).not.toHaveBeenCalled();delete (mocks.state.draft as {gen?:unknown}).gen;
});

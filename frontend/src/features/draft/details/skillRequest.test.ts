import {afterEach,expect,it,vi} from 'vitest';
import type {DraftDoc} from '@/api/types/draft';
const mock=vi.hoisted(()=>({ensure:vi.fn(async()=> 'd'),flush:vi.fn(async()=>{}),wait:vi.fn(),state:{owner:'u',draftId:'d',draft:{goal:'SQL 검증',project:null,prefs:{}}}}));
vi.mock('../draftSync',()=>({ensureDraft:mock.ensure,flush:mock.flush}));
vi.mock('@/shared/state/workspace',()=>({ws:()=>mock.state}));
vi.mock('@/api/jobs',()=>({waitJob:mock.wait}));
import {loadSkills,summaryStage} from './skillRequest';
import {skillInputKey} from './skillInput';
afterEach(()=>{vi.unstubAllGlobals();vi.clearAllMocks();});
it('중복 진입은 한 요청을 공유하고 다시 제안하면 새로 요청한다',async()=>{
 let resolve!:(v:unknown)=>void;mock.wait.mockReturnValue(new Promise(done=>{resolve=done;}));
 const fetch=vi.fn().mockResolvedValue({ok:true,status:202,json:async()=>({jobId:'j'})});vi.stubGlobal('fetch',fetch);
 const key=skillInputKey(mock.state.draft as DraftDoc),a=loadSkills('u',key),b=loadSkills('u',key);
 await vi.waitFor(()=>expect(mock.wait).toHaveBeenCalledOnce());resolve({skills:[{name:'SQL',application:'집계'}]});
 await Promise.all([a,b]);expect(fetch).toHaveBeenCalledOnce();
 mock.wait.mockResolvedValue({skills:[{name:'SQL',application:'조인'}]});expect((await loadSkills('u',key))[0].application).toBe('조인');expect(fetch).toHaveBeenCalledTimes(2);
});
it('404는 요약 부족 대신 API 미반영을 안내한다',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:404,json:async()=>({detail:'Not Found'})}));
 await expect(loadSkills('u',skillInputKey(mock.state.draft as DraftDoc))).rejects.toThrow('API가 반영되지');
});
it('요약 생성 중과 실패를 구분하고 첨부 없는 목표도 추천 가능하다',()=>{
 const d=mock.state.draft as DraftDoc;expect(summaryStage(d)).toBe('ready');
 const project={name:'기획서'} as DraftDoc['project'];
 expect(summaryStage({...d,project,doc:{name:'기획서',status:'reading'}})).toBe('reading');
 expect(summaryStage({...d,project,doc:{name:'기획서',status:'ok',summary:'요약'}})).toBe('ready');
 expect(summaryStage({...d,project,doc:{name:'기획서',status:'fail'}})).toBe('missing');
});

it('explicit goal-only fallback unblocks missing summaries but never bypasses a running summary',()=>{
 const d=mock.state.draft as DraftDoc,project={name:'기획서'} as DraftDoc['project'];
 expect(summaryStage({...d,project,doc:{name:'기획서',status:'fail'}},true)).toBe('ready');
 expect(summaryStage({...d,project,doc:{name:'기획서',status:'ok',summary:' '}},true)).toBe('ready');
 expect(summaryStage({...d,project,doc:{name:'기획서',status:'reading'}},true)).toBe('reading');
 expect(summaryStage({...d,project,doc:{name:'기획서',status:'fail'}})).toBe('missing');
});

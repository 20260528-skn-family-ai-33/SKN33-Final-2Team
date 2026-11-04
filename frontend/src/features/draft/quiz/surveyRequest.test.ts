import { afterEach,expect,it,vi } from 'vitest';
const mocks=vi.hoisted(()=>({ensure:vi.fn(async()=> 'draft'),wait:vi.fn()}));
vi.mock('../draftSync',()=>({ensureDraft:mocks.ensure}));
vi.mock('@/api/jobs',()=>({waitJob:mocks.wait}));
import { loadSurvey } from './surveyRequest';
afterEach(()=>{vi.unstubAllGlobals();vi.clearAllMocks();});
it('confirmation prefetch and quiz share one pending generation',async()=>{
 let resolve!:(v:unknown)=>void;const generated=new Promise(r=>{resolve=r;});
 const survey={generationId:'g',groups:[],questionCount:0,answers:{},completed:false};
 mocks.wait.mockReturnValue(generated);
 const fetch=vi.fn().mockResolvedValueOnce({ok:true,status:200,json:async()=>({survey:null})}).mockResolvedValueOnce({ok:true,status:202,json:async()=>({jobId:'j'})});vi.stubGlobal('fetch',fetch);
 const first=loadSurvey('u:inputs'),second=loadSurvey('u:inputs');
 await vi.waitFor(()=>expect(mocks.wait).toHaveBeenCalledOnce());resolve({survey});
 expect(await first).toEqual(survey);expect(await second).toEqual(survey);expect(fetch).toHaveBeenCalledTimes(2);
});
it('a changed input cannot reuse another pending generation',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({survey:{generationId:'g',groups:[],questionCount:0}})});vi.stubGlobal('fetch',fetch);
 await Promise.all([loadSurvey('u:old'),loadSurvey('u:new')]);expect(fetch).toHaveBeenCalledTimes(2);
});
it('failure releases the pending entry so explicit retry can succeed',async()=>{
 const fetch=vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ok:true,status:200,json:async()=>({survey:{generationId:'retry',groups:[],questionCount:0}})});vi.stubGlobal('fetch',fetch);
 await expect(loadSurvey('u:retry')).rejects.toThrow('offline');expect((await loadSurvey('u:retry')).generationId).toBe('retry');
});
it('퀴즈 작업 완료 전에도 저장된 설문을 먼저 반환한다',async()=>{
 vi.useFakeTimers();
 try {
  const partial={generationId:'partial',groups:[],questionCount:10,answers:{},completed:false,quizStatus:'pending'};
  mocks.wait.mockReturnValue(new Promise(()=>{}));
  const fetch=vi.fn().mockResolvedValueOnce(Response.json({survey:null})).mockResolvedValueOnce(Response.json({jobId:'slow-quiz'},{status:202})).mockResolvedValue(Response.json({survey:partial}));
  vi.stubGlobal('fetch',fetch);
  const work=loadSurvey('partial-owner');
  await vi.advanceTimersByTimeAsync(810);
  await expect(work).resolves.toEqual(partial);
 }finally{vi.useRealTimers();}
});

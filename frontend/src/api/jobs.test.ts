import {afterEach,expect,it,vi} from 'vitest';
const mocks=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('./client',async()=>{const original=await vi.importActual<typeof import('./client')>('./client');return {...original,http:{get:mocks.get,post:mocks.post}};});
import {waitJob} from './jobs';
afterEach(()=>vi.clearAllMocks());
it('서버 중단 작업은 복구 ID로 이어서 기다린다',async()=>{
 mocks.get.mockResolvedValueOnce({status:'failed',progress:{_resume:{}},error:{code:'JOB_INTERRUPTED'}}).mockResolvedValueOnce({status:'done',progress:{},result:{ok:true}});
 mocks.post.mockResolvedValue({jobId:'new'});
 await expect(waitJob('old')).resolves.toEqual({ok:true});
 expect(mocks.post).toHaveBeenCalledWith('/jobs/old/resume',{}, {signal:undefined});
 expect(mocks.get.mock.calls[1][0]).toContain('/jobs/new');
});
it('이미 복구된 작업은 중복 재등록 없이 연결한다',async()=>{
 mocks.get.mockResolvedValueOnce({status:'failed',progress:{redirectJobId:'replacement'},error:{code:'JOB_INTERRUPTED'}}).mockResolvedValueOnce({status:'done',progress:{},result:{cached:true}});
 await expect(waitJob('old')).resolves.toEqual({cached:true});expect(mocks.post).not.toHaveBeenCalled();
});
it('사용자 취소와 실제 모델 실패는 자동 재시도하지 않는다',async()=>{
 mocks.get.mockResolvedValueOnce({status:'cancelled',progress:{}});
 await expect(waitJob('cancelled')).rejects.toMatchObject({name:'AbortError'});
 mocks.get.mockResolvedValueOnce({status:'failed',progress:{_resume:{}},error:{code:'MODEL_ERROR'}});
 await expect(waitJob('failed')).rejects.toMatchObject({code:'MODEL_ERROR'});expect(mocks.post).not.toHaveBeenCalled();
});

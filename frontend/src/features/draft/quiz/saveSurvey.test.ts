import {beforeEach,expect,it,vi} from 'vitest';
const mock=vi.hoisted(()=>({state:{owner:'u' as string|null,draftId:'d',draft:{goal:'SQL 검증',project:null,prefs:{hours:4},v2Assessment:{generationId:'g',completed:false}}},flush:vi.fn(),take:vi.fn(),get:vi.fn(),request:vi.fn()}));
vi.mock('@/shared/state/workspace',()=>({ws:()=>mock.state}));
vi.mock('../draftSync',()=>({flush:mock.flush,takeDraft:mock.take}));
vi.mock('@/api/endpoints/drafts',()=>({draftsApi:{get:mock.get}}));
vi.mock('./surveyRequest',()=>({request:mock.request,SurveyRequestError:class extends Error{constructor(message:string,readonly code:string){super(message);}}}));
import {inputSignature} from '../invalidation';
import {saveSurvey} from './saveSurvey';
const scope=()=>({owner:'u',id:'d',generationId:'g',inputKey:inputSignature(mock.state.draft as never)});
const response=()=>({draftId:'d',draft:structuredClone({...mock.state.draft,v2Assessment:{generationId:'g',completed:true}})});
function deferred<T>(){let resolve!:(value:T)=>void;const work=new Promise<T>(done=>{resolve=done;});return{work,resolve};}
beforeEach(()=>{vi.resetAllMocks();mock.state.owner='u';mock.state.draftId='d';mock.state.draft.goal='SQL 검증';mock.state.draft.v2Assessment={generationId:'g',completed:false};mock.flush.mockResolvedValue(undefined);mock.request.mockResolvedValue({generationId:'g',completed:true,answers:{q:0}});mock.get.mockImplementation(async()=>response());});
it('현재 점검의 응답·완료 저장을 재조회로 확인한 뒤에만 초안에 적용한다',async()=>{
 const saved=await saveSurvey(scope(),{q:0},true);expect(saved.answers.q).toBe(0);expect(mock.take).toHaveBeenCalledOnce();
 expect(JSON.parse(mock.request.mock.calls[0][1].body)).toEqual({generationId:'g',answers:{q:0},complete:true});
});
it('자동 저장 대기 중 입력이 바뀌면 답안 저장을 시작하지 않는다',async()=>{
 const wait=deferred<void>();mock.flush.mockReturnValue(wait.work);const work=saveSurvey(scope(),{},true);
 mock.state.draft.goal='변경된 목표';wait.resolve();await expect(work).rejects.toThrow('입력이 변경');expect(mock.request).not.toHaveBeenCalled();
});
it('답안 응답 대기 중 직원이 바뀌면 이전 초안 조회·적용을 하지 않는다',async()=>{
 const wait=deferred<unknown>();mock.request.mockReturnValue(wait.work);const work=saveSurvey(scope(),{},true);
 await vi.waitFor(()=>expect(mock.request).toHaveBeenCalled());mock.state.owner='other';wait.resolve({generationId:'g',completed:true});
 await expect(work).rejects.toThrow('입력이 변경');expect(mock.get).not.toHaveBeenCalled();expect(mock.take).not.toHaveBeenCalled();
});
it('재조회 대기 중 문항이 바뀌면 과거 완료 응답을 적용하지 않는다',async()=>{
 const wait=deferred<unknown>();mock.get.mockReturnValue(wait.work);const old=response(),work=saveSurvey(scope(),{},true);
 await vi.waitFor(()=>expect(mock.get).toHaveBeenCalled());mock.state.draft.v2Assessment.generationId='new';wait.resolve(old);
 await expect(work).rejects.toThrow('입력이 변경');expect(mock.take).not.toHaveBeenCalled();
});
it('다른 입력의 서버 응답이나 미완료 상태를 완료로 적용하지 않는다',async()=>{
 mock.get.mockResolvedValue({...response(),draft:{...mock.state.draft,goal:'다른 목표'}});
 await expect(saveSurvey(scope(),{},true)).rejects.toThrow('저장 상태');expect(mock.take).not.toHaveBeenCalled();
 mock.request.mockResolvedValue({generationId:'g',completed:false});await expect(saveSurvey(scope(),{},true)).rejects.toThrow('응답 저장');
});
it('실패 후 사용자가 다시 저장하면 정상 완료할 수 있다',async()=>{
 mock.request.mockRejectedValueOnce(Error('offline'));await expect(saveSurvey(scope(),{},true)).rejects.toThrow('offline');
 await expect(saveSurvey(scope(),{},true)).resolves.toMatchObject({completed:true});expect(mock.take).toHaveBeenCalledOnce();
});

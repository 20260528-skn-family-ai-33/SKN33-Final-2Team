import {expect,it} from 'vitest';
import {initialMaterialPreparation,materialPreparation,canRevealMaterials,type MaterialPreparation,type MaterialStatus} from './materialPreparation';
const versions:Record<string,string>={A1:'free1',A2:'crash1',A3:'challenge1'};
function report(state:MaterialPreparation,course:string,status:MaterialStatus,changed=versions,version=changed[course],regenerating:string[]=[],scope='draft'){
 return materialPreparation(state,{type:'report',scope,course,status,version,versions:changed,regenerating});
}
function ready(){let state=initialMaterialPreparation;for(const course of Object.keys(versions))state=report(state,course,'ready');return state;}
it('initial proposals are shown together only after all finish',()=>{
 let state=report(initialMaterialPreparation,'A1','ready');expect(state.revealed).toBe(false);
 state=report(state,'A2','ready');expect(state.revealed).toBe(false);
 state=report(state,'A3','ready');expect(state.revealed).toBe(true);
});
it('regenerating one course leaves the comparison and other prepared courses available',()=>{
 const state=ready();const changed={...versions,A2:'crash2'};
 let next=report(state,'A2','pending',changed,'crash2',['A2']);
 expect(next.revealed).toBe(true);expect(next.courses.A1).toEqual(state.courses.A1);expect(next.courses.A3).toEqual(state.courses.A3);
 next=report(next,'A2','failed',changed);expect(next.revealed).toBe(true);
 next=report(next,'A2','ready',changed);expect(next.revealed).toBe(true);expect(next.courses.A2.version).toBe('crash2');
});
it('a late result from the replaced course cannot mark its new version ready',()=>{
 const changed={...versions,A2:'crash2'};const state=report(ready(),'A2','pending',changed);
 expect(report(state,'A2','ready',changed,'crash1')).toEqual(state);
});
it('a new draft does not inherit the revealed state',()=>{
 const next=report(ready(),'A1','ready',versions,'free1',[],'other-draft');expect(next.revealed).toBe(false);expect(next.courses.A2).toBeUndefined();
});

it('a missing failed roadmap does not hide the ready courses',()=>{
 const available={A1:'free1',A3:'challenge1'};
 let state=report(initialMaterialPreparation,'A1','ready',available);
 state=materialPreparation(state,{type:'report',scope:'draft',course:'A3',version:'challenge1',status:'ready',versions:available,unavailable:['A2'],regenerating:[]});
 expect(state.revealed).toBe(true);expect(canRevealMaterials(state.courses,available,['A2'],[])).toBe(true);
 expect(canRevealMaterials(state.courses,available,[],['A2'])).toBe(false);
});
it('a failed material recommendation allows the successful courses after all settle',()=>{
 let state=report(initialMaterialPreparation,'A1','ready');state=report(state,'A2','failed');state=report(state,'A3','ready');
 expect(state.revealed).toBe(true);expect(state.courses.A2.status).toBe('failed');
});
it('no successful materials must not be presented as ready',()=>{
 let state=initialMaterialPreparation;for(const course of Object.keys(versions))state=report(state,course,'failed');
 expect(state.revealed).toBe(false);
});
it('새로고침 후에도 한 코스 재생성이 나머지 두 코스 자료를 숨기지 않는다',()=>{
 const partial={A1:{version:'free1',status:'ready' as const},A3:{version:'challenge1',status:'ready' as const}};
 expect(canRevealMaterials(partial,versions,[],['A2'])).toBe(true);
 expect(canRevealMaterials(partial,{A1:'free1',A3:'challenge1'},[],['A2'])).toBe(false);
});

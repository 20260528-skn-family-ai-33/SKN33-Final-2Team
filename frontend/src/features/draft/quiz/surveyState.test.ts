import {expect,it} from 'vitest';
import {surveyState} from './surveyState';
import type {Stored} from './surveyRequest';
const survey:Stored={generationId:'g',groups:[],questionCount:0,answers:{},completed:true};
it('같은 완료 점검으로 돌아오면 자료 키와 산출물 완료 상태를 보존한다',()=>{
 const previous={generationId:'g',completed:true,materialsKey:'materials',materialsReady:true,activitiesReady:true};
 expect(surveyState(previous,survey,false)).toEqual(previous);
});
it('문항이 바뀌거나 응답을 수정하면 이전 자료·산출물 상태를 이어받지 않는다',()=>{
 const previous={generationId:'g',completed:true,materialsKey:'old',materialsReady:true,activitiesReady:true};
 expect(surveyState(previous,{...survey,generationId:'new'},false)).toEqual({generationId:'new',completed:true,materialsReady:false,activitiesReady:false});
 expect(surveyState(previous,survey,true)).toEqual({generationId:'g',completed:false,materialsReady:false,activitiesReady:false});
});

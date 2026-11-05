import {expect,it} from 'vitest';
import {quizSummary} from './quizSummary';
it('서로 다른 문항은 개념 단위 정답 수만 집계한다',()=>{
 expect(quizSummary([{skill:'SQL',concept:'조인',pre:'오답',post:'정답'},{skill:'SQL',concept:'조인',pre:'정답',post:'정답'},{skill:'SQL',concept:'집계',pre:'오답',post:'오답'}])).toEqual([{label:'SQL · 조인',pre:1,post:2,count:2},{label:'SQL · 집계',pre:0,post:0,count:1}]);
});
it('측정 개념이 없는 기존 보고서는 스킬 단위로 구분한다',()=>{
 expect(quizSummary([{skill:'S',pre:'정답',post:'오답'}])).toEqual([{label:'S · 스킬 단위',pre:1,post:0,count:1}]);
});

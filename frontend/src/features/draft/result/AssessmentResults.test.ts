import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect,it } from 'vitest';
import { CompletedAssessment } from './AssessmentResults';
const survey={generationId:'g',questionCount:2,completed:true,answers:{s:3,q:1},groups:[{skill:'SQL',title:'SQL',surveys:[{id:'s',text:'설문 문장'}],quizzes:[{id:'q',q:'퀴즈 문제',options:['A','B'],answer:0,explain:'정답의 근거'}]}]};
const html=()=>renderToStaticMarkup(createElement(CompletedAssessment,{survey}));

it('결과 단계에 들어오면 퀴즈 결과를 먼저 보여준다',()=>{
 const shown=html();
 expect(shown).toContain('퀴즈 문제');expect(shown).toContain('1 · 오답');expect(shown).toContain('정답의 근거');expect(shown).not.toContain('설문 문장');
});
it('첫 포커스만 퀴즈이고 상단 탭 순서는 설문 다음 퀴즈로 유지한다',()=>{
 const shown=html();
 expect(shown.indexOf('1. 설문')).toBeGreaterThan(-1);expect(shown.indexOf('1. 설문')).toBeLessThan(shown.indexOf('2. 퀴즈'));
 expect(shown).toMatch(/aria-current="step"[^>]*>2\. 퀴즈/);expect(shown).not.toMatch(/aria-current="step"[^>]*>1\. 설문/);
});

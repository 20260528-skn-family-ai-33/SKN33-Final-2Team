import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {createElement} from 'react';
import {QuizLearningCheck} from './QuizLearningCheck';
it('스킬별 카드와 개념별 사전·사후 정답 수를 출력한다',()=>{
 const html=renderToStaticMarkup(createElement(QuizLearningCheck,{evidence:[{skill:'SQL',concept:'조인',question:'Q1',pre:'오답',post:'정답'},{skill:'API',concept:'오류 응답',question:'Q2',pre:'정답',post:'정답'}]}));
 expect(html).toContain('학습 점검');expect(html).toContain('2개 스킬');expect(html).toContain('SQL');expect(html).toContain('오류 응답');expect(html).toContain('사후 1문항 중 1개 정답');expect(html).toContain('같은 개념의 다른 문제');
});
it('근거가 없는 기존 보고서에는 비어 있는 점검을 추가하지 않는다',()=>{
 expect(renderToStaticMarkup(createElement(QuizLearningCheck,{evidence:[]}))).toBe('');
});

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect,it,vi } from 'vitest';
import { SurveyFlow } from './SurveyFlow';
const survey={generationId:'g',questionCount:2,groups:[{skill:'SQL',title:'SQL',surveys:[{id:'s',text:'Survey'}],quizzes:[{id:'q',q:'Quiz',options:['A','B']}]}]};
it('completed assessments render a fixed completion screen without editable radios',()=>{
 const save=vi.fn();const html=renderToStaticMarkup(createElement(SurveyFlow,{survey,initialAnswers:{s:3,q:0},initialCompleted:true,onSave:save,onContinue:()=>{}}));
 expect(html).toContain('역량 테스트를 완료했어요');expect(html).not.toContain('type="radio"');expect(save).not.toHaveBeenCalled();
});
it('incomplete assessments retain editable survey questions',()=>{
 const html=renderToStaticMarkup(createElement(SurveyFlow,{survey,onSave:async()=>{}}));expect(html).toContain('type="radio"');expect(html).toContain('전체 0/2문항');
});

it('결과 설문은 같은 보기와 선택 표시를 보여주되 정오답 표시와 저장 버튼은 없다',()=>{
 const html=renderToStaticMarkup(createElement(SurveyFlow,{survey,initialAnswers:{s:3,q:1},initialCompleted:true,review:true,onSave:async()=>{}}));
 expect(html).toContain('fieldset disabled');expect(html).not.toContain('내 선택');expect(html).not.toContain('type="radio"');expect(html).toContain('보통이다');expect(html).not.toContain('answer-correct');expect(html).not.toContain('역량 테스트 완료</button>');
});
it('결과 퀴즈만 정답·선택 오답·해설을 구분한다',()=>{
 const graded={...survey,groups:[{...survey.groups[0],quizzes:[{...survey.groups[0].quizzes[0],answer:0,explain:'정답의 근거'}]}]};
 const wrong=renderToStaticMarkup(createElement(SurveyFlow,{survey:graded,initialAnswers:{s:3,q:1},initialCompleted:true,initialPhase:'quizzes',review:true,onSave:async()=>{}}));
 expect(wrong).toContain('quiz-result-number wrong');expect(wrong).toContain('1 · 오답');expect(wrong).toContain('answer-correct');expect(wrong).toContain('answer-wrong');expect(wrong).toContain('내 선택 · 오답');expect(wrong).toContain('정답의 근거');
 const correct=renderToStaticMarkup(createElement(SurveyFlow,{survey:graded,initialAnswers:{s:3,q:0},initialCompleted:true,initialPhase:'quizzes',review:true,onSave:async()=>{}}));
 expect(correct).toContain('quiz-result-number correct');expect(correct).toContain('1 · 정답');expect(correct).toContain('answer-chosen-correct');expect(correct).not.toContain('answer-wrong');
});
it('퀴즈 준비 중에는 빈 스킬 제목 카드를 노출하지 않고 로딩 상태만 보여준다',()=>{
 const pendingSurvey={generationId:'g',questionCount:2,quizStatus:'pending' as const,groups:[{skill:'RAG',title:'검색과 답변 품질을 함께 살펴볼까요',surveys:[{id:'s',text:'Survey'}],quizzes:[]}]};
 const html=renderToStaticMarkup(createElement(SurveyFlow,{survey:pendingSurvey,initialAnswers:{s:3},initialPhase:'quizzes',onSave:async()=>{}}));
 expect(html).toContain('class="loading"');expect(html).toContain('퀴즈를 준비하고 있어요.');expect(html).not.toContain('검색과 답변 품질을 함께 살펴볼까요');expect(html).not.toContain('확인할 역량:');
});

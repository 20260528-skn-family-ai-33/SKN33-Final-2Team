import { expect, it } from 'vitest';
import type { PlanRecord } from '@/api/types/plan';
import { fillRandomPost } from './postRandom';

const record = () => ({ plan:{ assess:{ questions:[{id:'survey'}] } }, post:{ answers:{}, goalSelf:'', file:{name:'보존.pdf'}, running:false } }) as unknown as PlanRecord;

it('fills surveys and goal response immediately while quiz is not prepared', () => {
  const value = record();
  fillRandomPost(value, () => 0);
  expect(value.post.answers).toEqual({survey:'1'});
  expect(value.post.goalSelf).toBe('1');
  expect(value.post.file?.name).toBe('보존.pdf');
  expect(value.post.quizSurvey).toBeUndefined();
  expect(value.post.running).toBe(false);
});

it('fills prepared quizzes including the zero index and stays inside option bounds', () => {
  const value = record();
  value.post.quizSurvey = {generationId:'fixture',questionCount:1,groups:[{skill:'SQL',title:'SQL',surveys:[],quizzes:[{id:'quiz',q:'질문',options:['a','b','c']}]}]};
  fillRandomPost(value, () => 0);
  expect(value.post.quizAnswers).toEqual({quiz:'0'});
  fillRandomPost(value, () => 0.9999);
  expect(value.post.answers.survey).toBe('1');
  expect(value.post.quizAnswers?.quiz).toBe('0');
  expect(value.post.goalSelf).toBe('1');
});

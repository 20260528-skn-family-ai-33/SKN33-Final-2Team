import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { QuizLearningCheck } from './QuizLearningCheck';

const quiz = (skill: string, concept: string, pre: string, post: string) => ({ skill, concept, question: '', pre, post });
const render = (props: Parameters<typeof QuizLearningCheck>[0]) => renderToStaticMarkup(createElement(QuizLearningCheck, props));

it('스킬별 카드와 개념별 사전·사후 정답 수를 출력한다', () => {
  const html = render({ evidence: [quiz('SQL', '조인', '오답', '정답'), quiz('API', '오류 응답', '정답', '정답')] });
  expect(html).toContain('학습 점검');
  expect(html).toContain('2개 스킬');
  expect(html).toContain('SQL');
  expect(html).toContain('오류 응답');
  expect(html).toContain('사후 1문항 중 1개 정답');
  expect(html).toContain('같은 개념의 다른 문제');
  expect(html).toContain('개념별 정답 수');
});

it('근거가 없는 기존 보고서에는 비어 있는 점검을 추가하지 않는다', () => {
  expect(render({ evidence: [] })).toBe('');
});

it('스킬마다 문항 수만큼 점을 찍고 정답 수를 분모와 함께 적는다', () => {
  const html = render({ evidence: [quiz('SQL', '조인', '오답', '정답'), quiz('SQL', '집계', '정답', '정답'), quiz('SQL', '인덱스', '오답', '오답')] });
  expect(html).toContain('사전 3문항 중 1개 정답');
  expect(html).toContain('사후 3문항 중 2개 정답');
  expect(html).toContain('1 / 3');
  expect(html).toContain('2 / 3');
  expect(html.split('cmp-dot pre wrong').length - 1).toBe(2);
  expect(html.split('cmp-dot post correct').length - 1).toBe(3);
  expect(html).toContain('조인: 사후 정답');
  expect(html).not.toContain('채점 근거 없음');
});

it('채점 근거가 없는 문항은 0점이 아니라 –로 보인다', () => {
  const html = render({ evidence: [quiz('SQL', '조인', '채점 근거 없음', '채점 근거 없음')] });
  expect(html).toContain('사전 채점 근거 없음');
  expect(html).toContain('사후 채점 근거 없음');
  expect(html).toContain('cmp-dot post none');
  expect(html).not.toContain('문항 중 0개 정답');
  expect(html).not.toContain('<b>0</b>');
});

it('사후 문항별 결과만 있는 보고서는 점 격자 없이 정오표만 보여 준다', () => {
  const html = render({ evidence: [], postDetails: [{ id: 'q1', skill: 'SQL', question: '질문', selected: '보기1', correct: '보기2', isCorrect: false, explanation: '근거' }] });
  expect(html).toContain('1개 스킬');
  expect(html).toContain('사후 퀴즈 문항별 결과');
  expect(html).toContain('해설 · 근거');
  expect(html).not.toContain('cmp-grid');
});

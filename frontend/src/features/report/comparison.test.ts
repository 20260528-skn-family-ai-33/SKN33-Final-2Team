import { describe, expect, it } from 'vitest';
import { quizComparison, surveyComparison } from './comparison';

const quiz = (skill: string, concept: string | undefined, pre: string, post: string) => ({ skill, concept, question: '', pre, post });
const survey = (id: string, pre: string | null, post: string, skill = 'SQL') => ({ id, area: '영역', skill, text: `문항 ${id}`, pre, post });

describe('quizComparison', () => {
  it('스킬·전체 정답 수와 문항별 채점 결과를 센다', () => {
    const result = quizComparison([
      quiz('SQL', '조인', '오답', '정답'),
      quiz('SQL', '집계', '정답', '정답'),
      quiz('SQL', '인덱스', '정답', '오답'),
      quiz('API', '오류 응답', '오답', '오답'),
    ]);
    expect(result.skills.map((skill) => [skill.skill, skill.pre, skill.post])).toEqual([
      ['SQL', { correct: 2, graded: 3 }, { correct: 2, graded: 3 }],
      ['API', { correct: 0, graded: 1 }, { correct: 0, graded: 1 }],
    ]);
    expect(result.pre).toEqual({ correct: 2, graded: 4 });
    expect(result.post).toEqual({ correct: 2, graded: 4 });
    expect(result.ungraded).toBe(0);
    expect(result.skills[0].items.map((item) => [item.pre, item.post])).toEqual([
      ['wrong', 'correct'],
      ['correct', 'correct'],
      ['correct', 'wrong'],
    ]);
  });

  it('같은 개념의 여러 문항은 개념 한 줄로 묶고, 개념이 없는 이전 보고서는 스킬 단위로 둔다', () => {
    const result = quizComparison([quiz('SQL', '조인', '오답', '정답'), quiz('SQL', '조인', '정답', '정답'), quiz('S', undefined, '정답', '오답')]);
    expect(result.skills[0].concepts).toEqual([{ concept: '조인', pre: { correct: 1, graded: 2 }, post: { correct: 2, graded: 2 } }]);
    expect(result.skills[1].concepts).toEqual([{ concept: '', pre: { correct: 1, graded: 1 }, post: { correct: 0, graded: 1 } }]);
  });

  it('채점 근거가 없는 문항은 0점으로 세지 않고 분모에서 뺀다', () => {
    const result = quizComparison([quiz('SQL', '조인', '채점 근거 없음', '채점 근거 없음'), quiz('SQL', '집계', '오답', '정답')]);
    expect(result.pre).toEqual({ correct: 0, graded: 1 });
    expect(result.post).toEqual({ correct: 1, graded: 1 });
    expect(result.ungraded).toBe(1);
    expect(result.skills[0].concepts[0]).toEqual({ concept: '조인', pre: { correct: 0, graded: 0 }, post: { correct: 0, graded: 0 } });
  });

  it('사전·사후 중 한쪽만 채점한 문항은 각자의 분모로 센다', () => {
    const result = quizComparison([quiz('SQL', '조인', '채점 근거 없음', '정답'), quiz('SQL', '집계', '정답', '정답')]);
    expect(result.pre).toEqual({ correct: 1, graded: 1 });
    expect(result.post).toEqual({ correct: 2, graded: 2 });
    expect(result.ungraded).toBe(1);
  });

  it('채점한 문항이 없으면 분모가 0으로 남는다', () => {
    const result = quizComparison([quiz('SQL', '조인', '채점 근거 없음', '채점 근거 없음')]);
    expect(result.pre).toEqual({ correct: 0, graded: 0 });
    expect(result.post).toEqual({ correct: 0, graded: 0 });
    expect(quizComparison([])).toEqual({ skills: [], pre: { correct: 0, graded: 0 }, post: { correct: 0, graded: 0 }, ungraded: 0 });
  });
});

describe('surveyComparison', () => {
  it('같은 문항의 높아짐·같음·낮아짐을 센다', () => {
    const result = surveyComparison([survey('q1', '2', '4'), survey('q2', '3', '3'), survey('q3', '4', '3')]);
    expect(result.counts).toEqual({ up: 1, same: 1, down: 1, unknown: 0 });
    expect(result.compared).toBe(3);
    expect(result.items.map((item) => [item.pre, item.post, item.change])).toEqual([
      [2, 4, 'up'],
      [3, 3, 'same'],
      [4, 3, 'down'],
    ]);
  });

  it('사전 응답이 없거나 1~5를 벗어난 값은 변화에서 빼고 0으로 바꾸지 않는다', () => {
    const result = surveyComparison([survey('q1', null, '4'), survey('q2', '0', '3'), survey('q3', '2', '6'), survey('q4', '1', '5')]);
    expect(result.counts).toEqual({ up: 1, same: 0, down: 0, unknown: 3 });
    expect(result.compared).toBe(1);
    expect(result.items[0]).toMatchObject({ pre: null, post: 4, change: 'unknown' });
    expect(result.items[1]).toMatchObject({ pre: null, post: 3 });
    expect(result.items[2]).toMatchObject({ pre: 2, post: null });
  });

  it('스킬 이름이 없으면 영역 이름을 쓴다', () => {
    expect(surveyComparison([survey('q1', '1', '2', '')]).items[0].skill).toBe('영역');
  });
});

import { describe, expect, it } from 'vitest';
import { assessmentSummary } from './assessmentSummary';

const survey = { groups: [
  { skill: 'SQL', title: 'SQL 살펴보기',
    surveys: [{ id: 's1', text: '가' }, { id: 's2', text: '나' }, { id: 's3', text: '다' }],
    quizzes: [{ id: 'q1', q: '1', options: ['a', 'b'], answer: 1 }, { id: 'q2', q: '2', options: ['a', 'b'], answer: 0 }] },
  { skill: 'Bash', title: 'Bash 살펴보기',
    surveys: [{ id: 's4', text: '라' }],
    quizzes: [{ id: 'q3', q: '3', options: ['a', 'b'], answer: 0 }, { id: 'q4', q: '4', options: ['a', 'b'] }] },
] };

describe('5단계 결과 요약', () => {
  it('스킬별 퀴즈 정답 수와 설문 평균을 낸다', () => {
    const result = assessmentSummary(survey, { s1: 3, s2: 4, s3: 3, s4: 5, q1: 1, q2: 1, q3: 0, q4: 1 });
    expect(result.skills).toEqual([
      { skill: 'SQL', quizCorrect: 1, quizTotal: 2, selfAverage: 3.3 },
      { skill: 'Bash', quizCorrect: 1, quizTotal: 1, selfAverage: 5 },
    ]);
    expect([result.quizCorrect, result.quizTotal]).toEqual([2, 3]);
  });

  it('정답이 공개되지 않은 문항은 세지 않고, 0번 보기가 정답인 경우도 맞게 센다', () => {
    const result = assessmentSummary(survey, { q3: 0, q4: 0 });
    expect(result.skills[1]).toMatchObject({ quizCorrect: 1, quizTotal: 1 });
  });

  it('답하지 않은 설문은 평균에서 빼고, 하나도 없으면 평균이 없다', () => {
    const result = assessmentSummary(survey, { s1: 2 });
    expect(result.skills[0].selfAverage).toBe(2);
    expect(result.skills[1].selfAverage).toBeNull();
  });
});

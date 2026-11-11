/* 보고서 개요의 스킬별 값과 일정 줄 계산 */
import { describe, expect, it } from 'vitest';
import { quizComparison, surveyComparison } from './comparison';
import { buildSchedule, quizBySkill, quizRingCount, surveyBySkill } from './overview';

const quiz = (skill: string, concept: string, pre: string, post: string) => ({ skill, concept, question: '', pre, post });
const survey = (id: string, skill: string, pre: string | null, post: string) => ({ id, area: skill, skill, text: `문항 ${id}`, pre, post });
const act = (id: string, wFrom: number, wTo: number, res: string | null = null) => ({ id, res, wFrom, wTo });
const recorded = (id: string, status: string, task = false) => ({ id, title: `활동 ${id}`, status, task });
const snapshot = (activities: ReturnType<typeof recorded>[]) => ({ asOf: '2026-11-11T01:00:00+00:00', early: false, version: 1, activities });

describe('surveyBySkill', () => {
  it('스킬마다 응답한 문항의 평균을 내고 5점 만점 비율로 바꾼다', () => {
    const axes = surveyBySkill(surveyComparison([survey('q1', 'SQL', '2', '4'), survey('q2', 'SQL', '3', '4'), survey('q3', 'API', '1', '5')]));
    expect(axes).toEqual([
      { skill: 'SQL', pre: 0.5, post: 0.8, preText: '2.5', postText: '4' },
      { skill: 'API', pre: 0.2, post: 1, preText: '1', postText: '5' },
    ]);
  });

  it('사전 응답이 없는 스킬은 0점이 아니라 값 없음으로 둔다', () => {
    const [axis] = surveyBySkill(surveyComparison([survey('q1', 'SQL', null, '4'), survey('q2', 'SQL', '9', '3')]));
    expect(axis).toEqual({ skill: 'SQL', pre: null, post: 0.7, preText: '–', postText: '3.5' });
  });
});

describe('quizBySkill', () => {
  it('스킬마다 채점한 문항 중 맞힌 비율과 분모를 함께 돌려준다', () => {
    const comparison = quizComparison([quiz('SQL', '조인', '오답', '정답'), quiz('SQL', '집계', '정답', '정답'), quiz('SQL', '인덱스', '오답', '오답'), quiz('API', '인증', '채점 근거 없음', '정답')]);
    expect(quizBySkill(comparison)).toEqual([
      { skill: 'SQL', pre: 1 / 3, post: 2 / 3, preText: '1/3', postText: '2/3' },
      { skill: 'API', pre: null, post: 1, preText: '–', postText: '1/1' },
    ]);
  });

  it('채점 문항 수가 모두 같을 때만 눈금 한 칸을 1문항으로 쓴다', () => {
    const same = quizComparison([quiz('SQL', '조인', '오답', '정답'), quiz('SQL', '집계', '정답', '정답'), quiz('API', '인증', '오답', '정답'), quiz('API', '오류', '오답', '오답')]);
    expect(quizRingCount(same)).toBe(2);
    const mixed = quizComparison([quiz('SQL', '조인', '오답', '정답'), quiz('SQL', '집계', '정답', '정답'), quiz('API', '인증', '오답', '정답')]);
    expect(quizRingCount(mixed)).toBeNull();
    expect(quizRingCount(quizComparison([quiz('SQL', '조인', '채점 근거 없음', '채점 근거 없음')]))).toBeNull();
  });
});

describe('buildSchedule', () => {
  it('보고서 시점의 완료 여부에 계획 주차를 붙인다', () => {
    const schedule = buildSchedule([act('a1', 1, 2, 'c1'), act('a2', 2, 2), act('a3', 3, 4)], snapshot([recorded('a1', 'done'), recorded('a2', 'doing', true), recorded('a3', 'done', true)]), 5);
    expect(schedule).toEqual({
      weeks: 5,
      rows: [
        { key: 'a1', res: 'c1', task: false, title: '활동 a1', from: 1, to: 2, done: true },
        { key: 'a2', res: null, task: true, title: '활동 a2', from: 2, to: 2, done: false },
        { key: 'a3', res: null, task: true, title: '활동 a3', from: 3, to: 4, done: true },
      ],
    });
  });

  it('같은 강좌가 여러 활동으로 나뉘어 있으면 한 줄로 합치고 모두 끝나야 완료로 본다', () => {
    const schedule = buildSchedule([act('a1', 1, 1, 'c1'), act('a2', 2, 3, 'c1')], snapshot([recorded('a1', 'done'), recorded('a2', 'doing')]));
    expect(schedule?.rows).toEqual([{ key: 'a1', res: 'c1', task: false, title: '활동 a1', from: 1, to: 3, done: false }]);
    expect(schedule?.weeks).toBe(3);
  });

  it('주차를 알 수 없는 활동이 있으면 일부만 그리지 않는다', () => {
    expect(buildSchedule([act('a1', 1, 1)], snapshot([recorded('a1', 'done'), recorded('gone', 'done')]))).toBeNull();
    expect(buildSchedule([act('a1', 0, 0)], snapshot([recorded('a1', 'done')]))).toBeNull();
    expect(buildSchedule([act('a1', 1, 1)], snapshot([]))).toBeNull();
  });
});

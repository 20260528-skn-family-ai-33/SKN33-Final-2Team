/* 내 스킬 지도(누적) 뱃지 계산: 학습 중·브론즈·실버·골드, 학습한 횟수 */
import { describe, expect, it } from 'vitest';
import type { ResourceMap, SkillMapData } from '@/api/types/catalog';
import type { PlanRecord, Report } from '@/api/types/plan';
import { earnedSkills } from './earned';

const data: SkillMapData = {
  skills: [
    { id: 1, name: 'SQL', category: '데이터', resources: 1 },
    { id: 2, name: 'SQL 튜닝', category: '데이터', resources: 1 },
    { id: 3, name: 'Python', category: '개발', resources: 1 },
  ],
  prerequisites: [[1, 2]],
  unmatched: [],
  prerequisiteSource: 'draft',
};
const resources = { course: { id: 'course', kind: '강좌' }, book: { id: 'book', kind: '도서' } } as unknown as ResourceMap;

type Act = { id: string; skill: string; res?: string };
const rec = (id: string, status: string, acts: Act[], done: string[]): PlanRecord =>
  ({ id, status, plan: { goal: `${id} 목표`, def: {}, acts }, progress: Object.fromEntries(done.map((act) => [act, { status: 'done' }])) }) as unknown as PlanRecord;
/** 스킬마다 사후 퀴즈 3문항 가운데 맞힌 개수 */
const report = (planId: string, correct: Record<string, number>): Report =>
  ({
    planId,
    quizEvidence: Object.entries(correct).flatMap(([skill, n]) => [0, 1, 2].map((i) => ({ skill, question: '', pre: '오답', post: i < n ? '정답' : '오답' }))),
  }) as unknown as Report;
const levels = (records: PlanRecord[], reports: Report[] = []) =>
  Object.fromEntries([...earnedSkills(data, records, reports, resources).marks].map(([id, mark]) => [id, mark.level]));

describe('earnedSkills', () => {
  it('스킬의 활동을 모두 완료하면 브론즈, 진행 중인 로드맵에서 남아 있으면 학습 중', () => {
    const active = rec('p1', 'active', [{ id: 'a', skill: 'SQL' }, { id: 'b', skill: 'SQL' }, { id: 'c', skill: 'Python' }], ['a', 'b']);
    expect(levels([active])).toEqual({ 1: 'bronze', 3: 'learning' });
  });
  it('보관했거나 조기 종료한 로드맵의 못 마친 스킬은 표시하지 않는다', () => {
    const archived = rec('p1', 'archived', [{ id: 'a', skill: 'SQL' }], []);
    const early = rec('p2', 'done', [{ id: 'b', skill: 'Python' }], []);
    expect(levels([archived, early])).toEqual({});
  });
  it('도서는 완료 기록이 없어도 브론즈 판정에서 뺀다', () => {
    const plan = rec('p1', 'active', [{ id: 'a', skill: 'SQL', res: 'course' }, { id: 'b', skill: 'SQL', res: 'book' }], ['a']);
    expect(levels([plan])).toEqual({ 1: 'bronze' });
  });
  it('도서만 있는 스킬은 로드맵을 마쳤을 때 브론즈로 본다', () => {
    const acts = [{ id: 'b', skill: 'SQL', res: 'book' }];
    expect(levels([rec('p1', 'active', acts, [])])).toEqual({ 1: 'learning' });
    expect(levels([rec('p1', 'done', acts, [])])).toEqual({ 1: 'bronze' });
  });
  it('사후 퀴즈 3문항 중 2개면 실버, 3개면 골드, 1개 이하면 브론즈에 머문다', () => {
    const plan = rec('p1', 'done', [{ id: 'a', skill: 'SQL' }, { id: 'b', skill: 'Python' }, { id: 'c', skill: 'SQL 튜닝' }], ['a', 'b', 'c']);
    expect(levels([plan], [report('p1', { SQL: 3, Python: 2, 'SQL 튜닝': 1 })])).toEqual({ 1: 'gold', 2: 'bronze', 3: 'silver' });
  });
  it('활동을 다 마치지 않았어도 사후 퀴즈 기록이 있으면 실버·골드를 준다', () => {
    const early = rec('p1', 'done', [{ id: 'a', skill: 'SQL' }, { id: 'b', skill: 'Python' }], []);
    expect(levels([early], [report('p1', { SQL: 3, Python: 1 })])).toEqual({ 1: 'gold' });
  });
  it('다른 로드맵의 보고서는 쓰지 않는다', () => {
    const plan = rec('p1', 'active', [{ id: 'a', skill: 'SQL' }], ['a']);
    expect(levels([plan], [report('p2', { SQL: 3 })])).toEqual({ 1: 'bronze' });
  });
  it('여러 로드맵에서 배우면 가장 높은 뱃지를 쓰고, 배운 로드맵을 뱃지순으로 모두 적는다', () => {
    const first = rec('p1', 'done', [{ id: 'a', skill: 'SQL' }], ['a']);
    const second = rec('p2', 'done', [{ id: 'b', skill: 'SQL' }], ['b']);
    const third = rec('p3', 'active', [{ id: 'c', skill: 'SQL' }, { id: 'd', skill: 'SQL' }], ['c']);
    const mark = earnedSkills(data, [first, second, third], [report('p2', { SQL: 2 })], resources).marks.get(1);
    expect(mark?.level).toBe('silver');
    expect(mark?.plans.map((plan) => [plan.id, plan.level])).toEqual([['p2', 'silver'], ['p1', 'bronze'], ['p3', 'learning']]);
    expect(mark?.plans[0].quiz).toEqual({ post: 2, count: 3 });
  });
  it('팀 DB 스킬 이름과 맞지 않는 스킬은 지도에 올리지 않고 따로 알린다', () => {
    const plan = rec('p1', 'active', [{ id: 'a', skill: '없는 스킬' }, { id: 'b', skill: '' }], ['a']);
    const result = earnedSkills(data, [plan], [], resources);
    expect(result.marks.size).toBe(0);
    expect(result.unmatched).toEqual(['없는 스킬']);
  });
});

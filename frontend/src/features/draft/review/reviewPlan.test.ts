import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { reviewPlan, type ReviewProposal } from './reviewPlan';
import { ReviewSkillBlocks, type ReviewMaterials } from './ReviewSkillBlocks';
import { Stats } from '@/shared/ui/parts';

function fixture() {
  const materials: ReviewMaterials = { recommendations: { skills: [{ name: 'SQL',
    courses: [{ id: 'course', title: 'SQL course', hours: 13.5, timeStatus: 'confirmed', cost: 1000 }],
    books: [{ id: 'book', title: 'SQL book', hours: 10, cost: null }] }] },
    choices: {SQL: {course: 'course', books: ['book']}}, skillOrder: ['SQL'] };
  const proposal: ReviewProposal = {id: 'base', key: 'current', option: {id: 'A2', name: 'Crash', short: '', tagline: '', pros: [], cons: [], acts: [
    {id: 'c', res: 'course', skill: 'SQL', stage: 2, title: 'Course', hours: 13.5, how: ''},
    {id: 'b', res: 'book', skill: 'SQL', stage: 2, title: 'Book', hours: 10, how: ''},
    {id: 't', res: null, skill: 'SQL', stage: 3, title: 'Task', hours: 8, how: 'Verify'},
  ]}, selectedIds: ['c', 'b', 't']};
  const handoff = {startStage: 1, prefs: {weeklyHours: 5, formatKey: 'mixed'}};
  return {materials, proposal, handoff};
}

describe('검토 선택과 확정 계획의 시간 기준', () => {
  it('카탈로그 전역 캐시 없이 현재 자료로 상단·카드를 함께 계산하고 원본을 보존한다', () => {
    const {materials, proposal, handoff} = fixture(), original = structuredClone(proposal);
    const result = reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL');
    expect(result.plan).toMatchObject({weeks: 4, materialHours: 18.5, taskHours: 8, totalH: 26.5, cost: 1000, costUnknown: true});
    expect(result.acts.find(act => act.res === 'book')).toMatchObject({hours: 5, catalogHours: 10, hoursAllocation: 'book-week'});
    const card = renderToStaticMarkup(createElement(ReviewSkillBlocks, {materials, acts: result.acts, selectedIds: proposal.selectedIds, busy: false}));
    const stats = renderToStaticMarkup(createElement(Stats, {pl: result.plan}));
    expect(card).toContain('도서 1주 배정 · 5시간'); expect(card).not.toContain('계획 10시간');
    expect(stats).toContain('과제 별도 8시간'); expect(proposal).toEqual(original);
  });
  it('과제를 해제하면 합계에서만 제외하고 카드에는 재선택할 활동을 남긴다', () => {
    const {materials, proposal, handoff} = fixture(); proposal.selectedIds = ['c', 'b'];
    const result = reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL');
    expect(result.plan).toMatchObject({weeks: 4, taskHours: 0, totalH: 18.5});
    expect(result.plan.acts.map(act => act.id)).toEqual(['c', 'b']);
    expect(result.acts.map(act => act.id)).toContain('t');
  });
  it('다른 버전의 선택 과제로 교체해 서버 저장과 같은 합계를 계산한다', () => {
    const {materials, proposal, handoff} = fixture();
    const alternative = structuredClone(proposal); alternative.id = 'new';
    alternative.option.acts[2] = {...alternative.option.acts[2], id: 'new-task', hours: 3};
    proposal.selectedIds = ['c', 'b', 'new-task'];
    const result = reviewPlan(proposal, [proposal, alternative], {SQL: 'new'}, materials, handoff, 'SQL');
    expect(result.plan).toMatchObject({taskHours: 3, totalH: 21.5, weeks: 4});
    expect(result.acts.some(act => act.id === 't')).toBe(false);
    expect(result.acts.find(act => act.id === 'new-task')?.hours).toBe(3);
  });
  it('선택 상태를 다시 읽거나 주당 시간을 바꿔도 같은 자료·과제를 기준으로 계산한다', () => {
    const {materials, proposal, handoff} = fixture();
    const first = reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL');
    expect(reviewPlan(JSON.parse(JSON.stringify(proposal)), [proposal], {}, materials, handoff, 'SQL')).toEqual(first);
    handoff.prefs.weeklyHours = 10;
    const next = reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL');
    expect(next.plan).toMatchObject({weeks: 3, materialHours: 23.5, taskHours: 8});
    expect(next.acts.find(act => act.res === 'book')).toMatchObject({hours: 10, catalogHours: 10});
  });
  it('단계 이전 과제는 표시·합계에서 제외하고 현재 선택 자료의 기간은 유지한다', () => {
    const {materials, proposal, handoff} = fixture();
    proposal.option.acts[2].stage = 1; handoff.startStage = 2;
    const result = reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL');
    expect(result.plan.taskHours).toBe(0); expect(result.acts.some(act => act.id === 't')).toBe(false);
  });
  it('다른 입력의 과제나 존재하지 않는 선택은 오류로 알리고 오래된 합계를 만들지 않는다', () => {
    const {materials, proposal, handoff} = fixture();
    const old = {...proposal, id: 'old', key: 'different'};
    expect(() => reviewPlan(proposal, [proposal, old], {SQL: 'old'}, materials, handoff, 'SQL')).toThrow('선택한 과제');
    proposal.selectedIds.push('missing');
    expect(() => reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL')).toThrow('현재 제안');
  });
  it('자료가 변경되거나 아직 없으면 이전 도서 시간으로 대체하지 않는다', () => {
    const {materials, proposal, handoff} = fixture();
    expect(() => reviewPlan(proposal, [proposal], {}, {...materials, recommendations: null}, handoff, 'SQL')).toThrow('불러오는 중');
    materials.choices.SQL.books = [];
    expect(() => reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL')).toThrow('자료가 현재 선택과 달라');
  });
});

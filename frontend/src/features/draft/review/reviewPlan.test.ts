import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { reviewPlan, reviewTaskDisplay, type ReviewProposal } from './reviewPlan';
import type { ReviewMaterials } from './ReviewSkillBlocks';
import { ReviewTaskBlocks } from './ReviewTaskBlocks';

// 작성 7단계의 스킬 블록(ReviewTaskBlocks)으로 그린다. 확정 뒤 화면용 ReviewSkillBlocks 는 선택·제안 기능이 없다
const noop = () => {};
const blocks = { options: {}, onToggle: noop, onPick: noop, onPropose: noop, onChangeMaterials: noop };
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
    expect(result.plan).toMatchObject({weeks: 3, materialHours: 13.5, taskHours: 8, totalH: 21.5, cost: 1000, costUnknown: true});
    expect(result.acts.find(act => act.res === 'book')).toMatchObject({hours: 10, catalogHours: 10});
    const card = renderToStaticMarkup(createElement(ReviewTaskBlocks, {...blocks, materials, acts: result.acts, selectedIds: proposal.selectedIds, busy: false}));
    const stats = renderToStaticMarkup(createElement(Stats, {pl: result.plan}));
    expect(card).toContain('일정에 넣지 않아요'); expect(card).not.toContain('계획 10시간');
    expect(stats).toContain('강좌 시간 기준 · 13시간 30분'); expect(stats).not.toContain('과제 별도'); expect(proposal).toEqual(original);
  });
  it('과제를 해제하면 합계에서만 제외하고 카드에는 재선택할 활동을 남긴다', () => {
    const {materials, proposal, handoff} = fixture(); proposal.selectedIds = ['c', 'b'];
    const result = reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL');
    expect(result.plan).toMatchObject({weeks: 3, taskHours: 0, totalH: 13.5});
    expect(result.plan.acts.map(act => act.id)).toEqual(['c', 'b']);
    expect(result.acts.map(act => act.id)).toContain('t');
  });
  it('다른 버전의 선택 과제로 교체해 서버 저장과 같은 합계를 계산한다', () => {
    const {materials, proposal, handoff} = fixture();
    const alternative = structuredClone(proposal); alternative.id = 'new';
    alternative.option.acts[2] = {...alternative.option.acts[2], id: 'new-task', hours: 3};
    proposal.selectedIds = ['c', 'b', 'new-task'];
    const result = reviewPlan(proposal, [proposal, alternative], {SQL: 'new'}, materials, handoff, 'SQL');
    expect(result.plan).toMatchObject({taskHours: 3, totalH: 16.5, weeks: 3});
    expect(result.acts.some(act => act.id === 't')).toBe(false);
    expect(result.acts.find(act => act.id === 'new-task')?.hours).toBe(3);
  });
  it('선택 상태를 다시 읽거나 주당 시간을 바꿔도 같은 자료·과제를 기준으로 계산한다', () => {
    const {materials, proposal, handoff} = fixture();
    const first = reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL');
    expect(reviewPlan(JSON.parse(JSON.stringify(proposal)), [proposal], {}, materials, handoff, 'SQL')).toEqual(first);
    handoff.prefs.weeklyHours = 10;
    const next = reviewPlan(proposal, [proposal], {}, materials, handoff, 'SQL');
    expect(next.plan).toMatchObject({weeks: 2, materialHours: 13.5, taskHours: 8});
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


describe('검토 계산 대기·오류 중 과제 표시', () => {
  it('자료 시간 대신 기존 과제와 선택 여부를 보존하고 재제안만 막는다', () => {
    const {materials, proposal} = fixture();
    const acts = reviewTaskDisplay(proposal, [proposal], {});
    expect(acts.map(act => act.id)).toEqual(['t']);
    for (const busy of [false, true]) {
      const html = renderToStaticMarkup(createElement(ReviewTaskBlocks, {...blocks, materials, acts, selectedIds: proposal.selectedIds, busy, proposeDisabled: true}));
      expect(html).toContain('Task'); expect(html).toContain('checked');
      expect(html).not.toContain('산출물을 제안받으면'); expect(html).not.toContain('계획 10시간');
      expect(html).toMatch(/<button[^>]*disabled[^>]*>(?:(?!<\/button>).)*다른 과제 제안받기/);
      if (!busy) expect(html).not.toMatch(/<input[^>]*disabled/);
    }
  });
  it('기본 제안 대신 실제 선택한 다른 버전의 과제를 표시한다', () => {
    const {proposal} = fixture(); const alternative = structuredClone(proposal); alternative.id = 'new';
    alternative.option.acts[2] = {...alternative.option.acts[2], id: 'new-task', hours: 3};
    expect(reviewTaskDisplay(proposal, [proposal, alternative], {SQL: 'new'})).toEqual([alternative.option.acts[2]]);
    expect(proposal.option.acts[2].id).toBe('t');
  });
  it('다른 입력의 제안·없는 버전·시작 단계 이전 과제를 끌어오지 않는다', () => {
    const {proposal} = fixture();
    expect(reviewTaskDisplay(proposal, [{...proposal, key: 'old'}], {SQL: 'base'})).toEqual([]);
    expect(reviewTaskDisplay(proposal, [], {SQL: 'missing'})).toEqual([]);
    expect(reviewTaskDisplay(proposal, [proposal], {}, 4)).toEqual([]);
    expect(reviewTaskDisplay(null, [], {})).toEqual([]);
  });
});

import { describe, it, expect } from 'vitest';
import { displayOrder, moveSkill, totalWeeks, currentWeeks, currentEstimates, durationLabel, DURATION_METHOD, type DurationEstimate } from './skillOrder';
const choices = { A: { course: null, books: [] }, B: { course: null, books: [], enabled: false }, C: { course: null, books: [] } };
describe('스킬 순서와 제외', () => {
 it('제외한 스킬은 삭제하지 않고 아래로 표시한다', () => expect(displayOrder(['A','B','C'], choices)).toEqual(['A','C','B']));
 it('선택 스킬의 순서만 바꾸고 자료 선택은 유지한다', () => {
   expect(moveSkill(['A','B','C'], 'C', 'A', choices)).toEqual(['C','A','B']);
   expect(choices.B.enabled).toBe(false);
 });
 it('자료 ID나 제외 스킬을 드래그해 순서를 바꿀 수 없다', () => {
   expect(moveSkill(['A','B','C'], 'B', 'A', choices)).toEqual(['A','B','C']);
   expect(moveSkill(['A','B','C'], 'resource', 'A', choices)).toEqual(['A','B','C']);
 });
});

describe('공유 자료 전체 기간과 스킬 표시 구간', () => {
 const order = ['RAG', 'ETL', 'Web'];
 const choices = { RAG: {course: 'shared', books: []}, ETL: {course: 'etl', books: []}, Web: {course: 'shared', books: []} };
 const selection = Object.fromEntries(order.map(name => [name, {enabled: true, courses: [choices[name as keyof typeof choices].course], books: []}]));
 const estimates: Record<string, DurationEstimate> = Object.fromEntries(order.map((name, i) => [name, {
   method: DURATION_METHOD, weeks: 2, startWeek: i === 1 ? 2 : 1, endWeek: i === 1 ? 3 : 2,
   addedWeeks: i === 0 ? 2 : i === 1 ? 1 : 0, totalWeeks: 3, weeklyHours: 6, scheduleKey: 'whole-selection',
   skillOrder: order, selection, course: choices[name as keyof typeof choices].course, books: [],
 }]));
 it('겹치는 표시 구간 6주를 더하지 않고 실제 전체 3주를 사용한다', () => {
   expect(totalWeeks(order, choices, estimates, 6)).toBe(3);
   expect(durationLabel(estimates.Web)).toBe('1–2주차 · 추가 0주');
 });
 it('공유 강좌 첫 참조를 바꾸는 순서·제외·선택 변경은 전체 캐시를 무효화한다', () => {
   expect(currentEstimates(['Web', 'ETL', 'RAG'], choices, estimates, 6)).toEqual({});
   expect(currentEstimates(order, {...choices, RAG: {...choices.RAG, enabled: false}}, estimates, 6)).toEqual({});
   expect(currentEstimates(order, {...choices, RAG: {...choices.RAG, course: 'changed'}}, estimates, 6)).toEqual({});
   expect(totalWeeks(order, {...choices, RAG: {...choices.RAG, course: 'changed'}}, estimates, 6)).toBeNull();
 });
 it('주당시간·일부 캐시 버전이 달라도 이전 기간을 표시하지 않는다', () => {
   expect(currentEstimates(order, choices, estimates, 12)).toEqual({});
   expect(totalWeeks(order, choices, {...estimates, ETL: {...estimates.ETL, scheduleKey: 'stale'}}, 6)).toBeNull();
   expect(currentEstimates(order, choices, {...estimates, ETL: {...estimates.ETL, method: 'course-hours-books/v1'}}, 6)).toEqual({});
 });
 it('확인되지 않은 시간을 확정값처럼 표시하지 않는다', () => {
   expect(durationLabel({...estimates.Web, unknownCourses: ['shared']})).toContain('시간 미확인');
   expect(durationLabel({...estimates.Web, estimatedCourses: ['shared']})).toContain('추정 시간 포함');
 });
});

describe('스킬 주차 합산', () => {
 const selected={A:{course:'a',books:[]},B:{course:'b',books:[]},C:{course:'c',books:[]}};
 const estimates={A:{weeks:2,basis:'AI',course:'a',books:[]},B:{weeks:3,basis:'AI',course:'b',books:[]},C:{weeks:4,basis:'AI',course:'c',books:[]}};
 it('순서를 바꿔도 합은 9주로 유지한다',()=>expect(totalWeeks(['C','A','B'],selected,estimates)).toBe(9));
 it('3주 스킬을 제외하면 6주, 복원하면 9주다',()=>{
  expect(totalWeeks(['A','B','C'],{...selected,B:{...selected.B,enabled:false}},estimates)).toBe(6);
  expect(totalWeeks(['A','B','C'],selected,estimates)).toBe(9);
 });
 it('선택 자료를 바꾸면 예전 주차를 사용하지 않는다',()=>{
  expect(currentWeeks({...selected.A,course:'other'},estimates.A)).toBeNull();
  expect(totalWeeks(['A','B','C'],{...selected,A:{...selected.A,course:'other'}},estimates)).toBeNull();
 });
 it('모두 제외하면 0주, 미정 기간은 임의로 더하지 않는다',()=>{
  expect(totalWeeks(['A'],{A:{...selected.A,enabled:false}},estimates)).toBe(0);
  expect(totalWeeks(['A'],selected,{A:{...estimates.A,weeks:null}})).toBeNull();
 });
});

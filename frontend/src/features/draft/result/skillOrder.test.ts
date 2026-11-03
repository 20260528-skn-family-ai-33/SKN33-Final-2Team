import { describe, it, expect } from 'vitest';
import { displayOrder, moveSkill, totalWeeks, currentWeeks } from './skillOrder';
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

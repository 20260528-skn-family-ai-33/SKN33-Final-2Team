import { expect, it } from 'vitest';
import { currentMaterialTotals } from './materialTotals';

it('재생성·주당 시간 변경·자료 재준비 중에는 이전 기간과 비용을 표시하지 않는다', () => {
  const old = {version:'v1',weeklyHours:5,weeks:4,amount:66000,unknown:false};
  expect(currentMaterialTotals(old,'v1',5,true)).toBe(old);
  expect(currentMaterialTotals(old,'v2',5,true)).toBeUndefined();
  expect(currentMaterialTotals(old,'v1',10,true)).toBeUndefined();
  expect(currentMaterialTotals(old,'v1',5,false)).toBeUndefined();
  expect(currentMaterialTotals(undefined,'v1',5,true)).toBeUndefined();
});

it('현재 선택의 기간 미확인은 이전 기간 대신 미확인으로 유지한다', () => {
  const current = {version:'v2',weeklyHours:5,weeks:null,amount:0,unknown:true};
  expect(currentMaterialTotals(current,'v2',5,true)).toBe(current);
});

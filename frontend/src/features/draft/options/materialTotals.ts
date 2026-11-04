import type { MaterialTotals } from '../result/ResultStep';

/** 새 안·주당 시간에 이전 선택 자료 합계가 잠깐 다시 표시되지 않게 한다. */
export function currentMaterialTotals(value: MaterialTotals | undefined, version: string, weeklyHours: number, ready: boolean): MaterialTotals | undefined {
  return ready && value?.version === version && value.weeklyHours === weeklyHours ? value : undefined;
}

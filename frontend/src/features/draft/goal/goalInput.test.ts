import { describe, expect, it } from 'vitest';
import { resolveGoalInput } from './goalInput';
describe('키우고 싶은 역량 기본 후보', () => {
  it.each([
    ['', '첫 후보', '첫 후보'],
    ['   ', '첫 후보', '첫 후보'],
    ['직접 작성한 역량', '첫 후보', '직접 작성한 역량'],
    [' 짧은 입력 ', '첫 후보', ' 짧은 입력 '],
    ['', undefined, ''],
    ['직접 작성한 역량', undefined, '직접 작성한 역량'],
  ])('입력 우선 및 빈 값 기본 처리: %s', (input, candidate, expected) => {
    expect(resolveGoalInput(input, candidate)).toBe(expected);
  });
});

import { expect, it } from 'vitest';
import { hrs } from './format';
import { roundedDuration } from './resourceTime';

it('uses the same ten-minute labels across activity and resource screens', () => {
  for (const [hours, label] of [[35/6,'5시간 50분'],[65/60,'1시간 10분'],[25/60,'30분'],[5/60,'10분'],[1/60,'10분 미만']] as const) {
    expect(hrs(hours)).toBe(label);
    expect(roundedDuration(hours)).toBe(label);
  }
  expect(hrs('5.833333333333333')).toBe('5시간 50분');
  expect(hrs(0)).toBe('0시간');
  expect(roundedDuration(0)).toBe('시간 미확인');
  for (const value of [null, undefined, '', 'bad', NaN, Infinity, -1]) expect(hrs(value)).toBe('시간 미확인');
});

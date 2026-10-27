/* 스킬 지도 주차 꼬리표: 같은 스킬을 다루는 활동들의 주차를 이어 붙인다 */
import { describe, expect, it } from 'vitest';
import type { Activity } from '@/api/types/plan';
import { actWeek, weeksOf } from './layout';

const a = (wFrom: number, wTo: number, stage = 1): { a: Activity } => ({ a: { id: `${wFrom}-${wTo}`, stage, title: '', hours: 1, wFrom, wTo } });

describe('weeksOf', () => {
  it('이어진 주는 묶고 떨어진 주는 가운뎃점으로 잇는다', () => {
    expect(weeksOf([a(1, 3), a(5, 6)])).toBe('1~3·5~6주차');
  });
  it('겹치는 활동의 주는 한 번만 센다', () => {
    expect(weeksOf([a(1, 2), a(2, 3)])).toBe('1~3주차');
  });
  it('세 덩어리 이상이면 처음~끝으로 줄인다', () => {
    expect(weeksOf([a(1, 1), a(3, 3), a(5, 5)])).toBe('1~5주차');
  });
  it('주차가 없는 옛 기록은 단계로 대신한다', () => {
    const old = { a: { id: 'x', stage: 2, title: '', hours: 1 } as unknown as Activity };
    expect(weeksOf([old])).toBe('2단계');
  });
});

describe('actWeek', () => {
  it('한 주짜리와 여러 주짜리를 구분해 쓴다', () => {
    expect(actWeek(a(4, 4).a)).toBe('4주차');
    expect(actWeek(a(2, 5).a)).toBe('2~5주차');
  });
});

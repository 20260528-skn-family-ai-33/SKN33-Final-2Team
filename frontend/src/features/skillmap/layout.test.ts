/* 스킬 지도 주차 꼬리표: 같은 스킬을 다루는 활동들의 주차를 이어 붙인다 */
import { describe, expect, it } from 'vitest';
import type { Activity } from '@/api/types/plan';
import { actWeek, edgeEnds, labelSpan, weeksOf } from './layout';

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

// 점 반지름 10 · 이름 한 줄(bh = 2r + 6 + 15 + 13) → 점 가운데 기준 이름 칸은 위 13 ~ 아래 44, 좌우 ±40
const node = (x: number, y: number, bw = 80) => ({ x, y, r: 10, bw, bh: 54 });

describe('labelSpan', () => {
  it('아래로 내려가는 선은 이름 칸 위에서 들어가 아래로 나온다', () => {
    expect(labelSpan(node(0, 0), 0, 1)).toEqual({ tin: 13, tout: 44 });
  });
  it('위나 옆으로 가는 선은 이름 칸을 지나지 않는다', () => {
    expect(labelSpan(node(0, 0), 0, -1)).toBeNull();
    expect(labelSpan(node(0, 0), 1, 0)).toBeNull();
  });
});

describe('edgeEnds', () => {
  it('이름 칸을 지나지 않으면 두 점 둘레에서 시작하고 끝난다', () => {
    expect(edgeEnds(node(0, 0), node(200, 0))).toEqual({ x1: 12, y1: 0, x2: 185, y2: 0 });
  });
  it('아래에서 들어오는 화살표는 끝 점의 이름 칸 아래에서 멈춘다(화살촉이 이름 뒤에 숨지 않게)', () => {
    const p = edgeEnds(node(0, 200), node(0, 0));
    expect(p.y1).toBe(188);
    expect(p.y2).toBe(49);
  });
  it('아래로 나가는 선은 시작 점의 이름 칸 아래에서 시작한다', () => {
    const p = edgeEnds(node(0, 0), node(0, 200));
    expect(p.y1).toBe(46);
    expect(p.y2).toBe(185);
  });
  it('점에서 멀리 떨어진 곳에서 이름 칸에 걸치는 선은 그대로 둔다', () => {
    const A = node(0, 0, 400);
    const B = node(400, 60);
    const p = edgeEnds(A, B);
    const d = Math.hypot(400, 60);
    expect(p.x1).toBeCloseTo((400 / d) * 12);
    expect(p.y1).toBeCloseTo((60 / d) * 12);
  });
  it('이름 칸을 피할 자리가 없으면 원래대로 점 둘레에서 끝난다', () => {
    // 시작 점의 위쪽 끝(y 50)이 끝 점의 이름 칸 아래(y 44) 바로 밑이라 피하면 선 길이가 남지 않는다
    const p = edgeEnds(node(0, 60), node(0, 0));
    expect(p.y2).toBe(15);
    expect(p.y1).toBe(48);
  });
});

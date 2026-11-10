/* 시연 도구 기준 날짜: 주차 계산의 오늘만 앞으로 옮기고, 시연이 꺼지면 적용하지 않는다 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanContent, PlanRecord } from '@/api/types/plan';
import { colsOne, weekNow } from '@/features/home/ganttCalc';
import { useAi } from './ai';
import { clockNow, isoDay, setDemoDay, useDemoClock } from './demoClock';

const rec = (createdAt: string, weeks: number): PlanRecord => ({ createdAt, plan: { weeks, acts: [] } as unknown as PlanContent }) as PlanRecord;
const serverDemo = (on: boolean) => useAi.setState((s) => ({ status: { ...s.status, demoMode: on } }));
const started = rec('2026-11-09', 4);

beforeEach(() => {
  vi.useFakeTimers({ now: new Date(2026, 10, 9, 15, 0), toFake: ['Date'] });
  vi.stubEnv('VITE_DEMO_TOOLS', 'on');
  serverDemo(true);
  setDemoDay(null);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('시연 기준 날짜', () => {
  it('정하지 않으면 실제 오늘로 계산한다', () => {
    expect(isoDay(clockNow())).toBe('2026-11-09');
    expect(weekNow(started)).toBe(1);
  });

  it('7일째까지 같은 주차이고 8일째에 다음 주차로 넘어간다', () => {
    setDemoDay('2026-11-15');
    expect(weekNow(started)).toBe(1);
    setDemoDay('2026-11-16');
    expect(weekNow(started)).toBe(2);
  });

  it('마지막 주가 지나면 일정표에 이번 주 칸이 없다', () => {
    setDemoDay('2026-12-06');
    expect(colsOne(started).map((c) => c.on)).toEqual([false, false, false, true]);
    setDemoDay('2026-12-07');
    expect(weekNow(started)).toBe(5);
    expect(colsOne(started).some((c) => c.on)).toBe(false);
  });

  it('호출하는 쪽이 넘긴 시각은 기준 날짜보다 우선한다', () => {
    setDemoDay('2026-12-07');
    expect(weekNow(started, new Date(2026, 10, 16))).toBe(2);
  });

  it.each([
    ['서버 시연 꺼짐', () => serverDemo(false)],
    ['화면 빌드 시연 꺼짐', () => vi.stubEnv('VITE_DEMO_TOOLS', 'off')],
  ])('%s이면 저장된 기준 날짜를 쓰지 않는다', (_name, turnOff) => {
    setDemoDay('2026-11-30');
    expect(weekNow(started)).toBe(4);
    turnOff();
    expect(weekNow(started)).toBe(1);
  });

  it.each(['2026-11-09', '2026-11-08', '', '20261-11-20', '내일', null])('%s은(는) 기준 날짜로 두지 않는다', (value) => {
    setDemoDay('2026-11-20');
    setDemoDay(value);
    expect(useDemoClock.getState().day).toBeNull();
    expect(isoDay(clockNow())).toBe('2026-11-09');
  });

  it('실제 날짜가 기준 날짜를 따라잡으면 실제 날짜로 돌아간다', () => {
    setDemoDay('2026-11-10');
    expect(isoDay(clockNow())).toBe('2026-11-10');
    vi.setSystemTime(new Date(2026, 10, 12, 9, 0));
    expect(isoDay(clockNow())).toBe('2026-11-12');
  });

  it('새로 고쳐도 탭 안에서는 유지하고 되돌리면 지운다', async () => {
    const box = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => box.get(k) ?? null,
      setItem: (k: string, v: string) => void box.set(k, v),
      removeItem: (k: string) => void box.delete(k),
    });
    setDemoDay('2026-11-20');
    vi.resetModules();
    const reloaded = await import('./demoClock');
    expect(reloaded.useDemoClock.getState().day).toBe('2026-11-20');
    reloaded.setDemoDay(null);
    expect(box.size).toBe(0);
  });
});

/* 새 로드맵 확정 때 진행 중인 로드맵이 있으면 시작 방식을 묻고, 고른 방식만 넘긴다 */
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanRecord } from '@/api/types/plan';
import { closeSheet, useUi } from '@/shared/state/ui';
import { useWs } from '@/shared/state/workspace';
import { chooseStartMode, startOptions } from './startModeSheet';

const plan = (id: string, createdAt: string, weeks: number, status: PlanRecord['status'] = 'active', extra: Partial<PlanRecord> = {}) =>
  ({ id, status, createdAt, plan: { goal: `${id} 목표`, weeks, acts: [] }, ...extra }) as unknown as PlanRecord;
const setPlans = (...list: PlanRecord[]) => useWs.setState({ plans: Object.fromEntries(list.map((R) => [R.id, R])) });
const sheet = () => useUi.getState().sheet;
const choices = () => (sheet()!.body() as ReactElement<{ children: ReactElement<{ children: ReactElement<{ onClick: () => void }>[] }>[] }>).props.children[0].props.children;
// 2026-10-26 은 월요일
const NOW = new Date(2026, 9, 26, 15, 0);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});
afterEach(() => {
  closeSheet();
  setPlans();
  vi.useRealTimers();
});

describe('startOptions', () => {
  it('끝나고 시작은 진행 중인 로드맵이 끝난 다음 주의 날짜를 보여 준다', () => {
    const options = startOptions([plan('a', '2026-10-21', 4)], NOW);
    expect(options.map((option) => option.label)).toEqual(['동시 진행', '끝나고 시작', '보관하고 시작']);
    expect(options[1].desc).toContain('11월 18일부터');
    expect(options[2].desc).toContain('이번 주부터');
  });
  it('여럿이면 모두 끝난 다음 주로 안내하고 모두 보관한다고 밝힌다', () => {
    const options = startOptions([plan('a', '2026-10-21', 4), plan('b', '2026-10-26', 5)], NOW);
    expect(options[1].desc).toContain('모두 끝난 다음 주, 11월 30일부터');
    expect(options[2].desc).toContain('모두 보관하고');
  });
  it('기간이 이미 지난 로드맵뿐이면 이번 주부터라고 안내한다', () => {
    expect(startOptions([plan('a', '2026-09-01', 2)], NOW)[1].desc).toContain('이번 주부터');
  });
});

describe('chooseStartMode', () => {
  it('진행 중인 로드맵이 없으면 묻지 않고 바로 진행한다', () => {
    setPlans(plan('old', '2026-09-01', 2, 'archived'), plan('fin', '2026-09-01', 2, 'done'));
    const proceed = vi.fn();
    chooseStartMode(proceed);
    expect(proceed).toHaveBeenCalledExactlyOnceWith();
    expect(sheet()).toBeNull();
  });
  it('진행 중이면 고르기 전에는 확정하지 않고, 고른 방식을 넘기며 창을 닫는다', () => {
    setPlans(plan('a', '2026-10-21', 4));
    const proceed = vi.fn();
    chooseStartMode(proceed);
    expect(proceed).not.toHaveBeenCalled();
    choices()[1].props.onClick();
    expect(proceed).toHaveBeenCalledExactlyOnceWith('after');
    expect(sheet()).toBeNull();
  });
  it('취소하면 아무것도 넘기지 않는다', () => {
    setPlans(plan('a', '2026-10-21', 4));
    const proceed = vi.fn();
    chooseStartMode(proceed);
    expect(renderToStaticMarkup(sheet()!.foot!() as ReactElement)).toContain('취소');
    closeSheet();
    expect(proceed).not.toHaveBeenCalled();
  });
  it('수정안이 있는 로드맵이 있으면 보관할 때 버린다고 알린다', () => {
    setPlans(plan('a', '2026-10-21', 4, 'active', { pending: {} as PlanRecord['pending'] }));
    chooseStartMode(vi.fn());
    expect(renderToStaticMarkup(sheet()!.body() as ReactElement)).toContain('수정안은 버려요');
  });
});

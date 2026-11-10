/* 새 로드맵 작성 탭에 들어가려 할 때 진행 중인 로드맵이 있으면 시작 방식을 묻고, 고른 방식을 작성 문서에 남긴다 */
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { closeSheet, useUi } from '@/shared/state/ui';
import { freshDraft, updateWs, useWs, ws } from '@/shared/state/workspace';
import { blocksEntry, enterNewRoadmap, needsStartMode, startOptions } from './startModeSheet';

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
  useWs.setState({ draft: freshDraft() });
  vi.useRealTimers();
});

describe('startOptions', () => {
  it('끝나고 시작은 진행 중인 로드맵이 끝난 다음 주의 날짜를 보여 준다', () => {
    const options = startOptions([plan('a', '2026-10-21', 4)], NOW);
    expect(options.map((option) => option.label)).toEqual(['동시 진행', '끝나고 시작', '보관하고 시작']);
    expect(options[1].desc).toContain('11월 18일부터');
  });
  it('보관은 작성을 시작할 때가 아니라 확정할 때 적용된다고 밝힌다', () => {
    expect(startOptions([plan('a', '2026-10-21', 4)], NOW)[2].desc).toContain('확정할 때');
  });
  it('여럿이면 모두 끝난 다음 주로 안내하고 모두 보관한다고 밝힌다', () => {
    const options = startOptions([plan('a', '2026-10-21', 4), plan('b', '2026-10-26', 5)], NOW);
    expect(options[1].desc).toContain('모두 끝난 다음 주, 11월 30일부터');
    expect(options[2].desc).toContain('모두 보관하고');
  });
  it('기간이 이미 지난 로드맵뿐이면 확정하면 바로 시작한다고 안내한다', () => {
    expect(startOptions([plan('a', '2026-09-01', 2)], NOW)[1].desc).toContain('바로 시작');
  });
});

describe('진입 판단', () => {
  const pickMode = () => updateWs((s) => void (s.draft.startMode = 'after'));

  it('진행 중인 로드맵이 있고 아직 고르지 않았을 때만 묻는다', () => {
    expect(needsStartMode(ws())).toBe(false);
    setPlans(plan('old', '2026-09-01', 2, 'archived'), plan('fin', '2026-09-01', 2, 'done'));
    expect(needsStartMode(ws())).toBe(false);
    setPlans(plan('a', '2026-10-21', 4));
    expect(needsStartMode(ws())).toBe(true);
    pickMode();
    expect(needsStartMode(ws())).toBe(false);
  });
  it('작성 탭 밖에서 안으로 들어갈 때만 막고, 작성 단계끼리의 이동은 막지 않는다', () => {
    setPlans(plan('a', '2026-10-21', 4));
    expect(blocksEntry(paths.newGoal, paths.home, ws())).toBe(true);
    expect(blocksEntry(paths.newReview, paths.roadmaps, ws())).toBe(true);
    expect(blocksEntry(paths.newMaterials, paths.home, ws())).toBe(true);
    expect(blocksEntry(paths.newDetails, paths.newGoal, ws())).toBe(false);
    expect(blocksEntry(paths.roadmaps, paths.home, ws())).toBe(false);
  });
});

describe('enterNewRoadmap', () => {
  it('진행 중인 로드맵이 없으면 묻지 않고 바로 들어간다', () => {
    setPlans(plan('old', '2026-09-01', 2, 'archived'));
    const go = vi.fn();
    enterNewRoadmap(go, paths.newGoal);
    expect(go).toHaveBeenCalledExactlyOnceWith(paths.newGoal, { force: true });
    expect(sheet()).toBeNull();
    expect(ws().draft.startMode).toBeNull();
  });
  it('이미 고른 작성 문서는 다시 묻지 않는다', () => {
    setPlans(plan('a', '2026-10-21', 4));
    updateWs((s) => void (s.draft.startMode = 'together'));
    const go = vi.fn();
    enterNewRoadmap(go, paths.newQuiz);
    expect(go).toHaveBeenCalledOnce();
    expect(sheet()).toBeNull();
  });
  it('진행 중이면 고르기 전에는 들어가지 않고, 고르면 저장한 뒤 원래 가려던 단계로 간다', () => {
    setPlans(plan('a', '2026-10-21', 4));
    const go = vi.fn();
    enterNewRoadmap(go, paths.newOptions);
    expect(go).not.toHaveBeenCalled();
    expect(sheet()).not.toBeNull();
    choices()[1].props.onClick();
    expect(ws().draft.startMode).toBe('after');
    expect(go).toHaveBeenCalledExactlyOnceWith(paths.newOptions, { force: true });
    expect(sheet()).toBeNull();
  });
  it('취소하면 들어가지 않고 준비 작업도 하지 않으며 고른 값도 남지 않는다', () => {
    setPlans(plan('a', '2026-10-21', 4));
    const go = vi.fn();
    const before = vi.fn();
    enterNewRoadmap(go, paths.newGoal, before);
    expect(renderToStaticMarkup(sheet()!.foot!() as ReactElement)).toContain('취소');
    closeSheet();
    expect(go).not.toHaveBeenCalled();
    expect(before).not.toHaveBeenCalled();
    expect(ws().draft.startMode).toBeNull();
  });
  it('준비 작업이 작성 문서를 새로 만들어도 고른 방식은 남는다', () => {
    setPlans(plan('a', '2026-10-21', 4));
    const go = vi.fn();
    enterNewRoadmap(go, paths.newGoal, () => updateWs((s) => void (s.draft = freshDraft())));
    choices()[2].props.onClick();
    expect(ws().draft.startMode).toBe('archive');
    expect(go).toHaveBeenCalledOnce();
  });
  it('단계 이동 초안은 기존 로드맵과 수정안의 보관을 제안하지 않는다', () => {
    setPlans(plan('a', '2026-10-21', 4, 'active', { pending: {} as PlanRecord['pending'] }));
    useWs.setState({ draft: { ...freshDraft(), demoSeeded: true } });
    enterNewRoadmap(vi.fn(), paths.newReview);
    const html = renderToStaticMarkup(sheet()!.body() as ReactElement);
    expect(html).toContain('동시 진행');
    expect(html).toContain('끝나고 시작');
    expect(html).not.toContain('보관');
  });
  it('수정안이 있는 로드맵이 있으면 보관할 때 버린다고 알린다', () => {
    setPlans(plan('a', '2026-10-21', 4, 'active', { pending: {} as PlanRecord['pending'] }));
    enterNewRoadmap(vi.fn(), paths.newGoal);
    expect(renderToStaticMarkup(sheet()!.body() as ReactElement)).toContain('수정안은 버려요');
  });
});

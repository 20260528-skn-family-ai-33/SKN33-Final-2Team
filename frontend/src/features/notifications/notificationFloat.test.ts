/* 새 알림 하단 플로팅(#96): 새로 온 알림 고르기 · 쌓는 순서 · 시간 지나면 내림 · 마우스를 올린 동안 멈춤 · 읽음이 되면 내림 · 로그인 바뀜 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppNotification } from '@/api/types/notification';
import { dismissFloat, FLOAT_MS, holdFloats, noteInbox, resetFloats, takeArrivals, useFloats } from './notificationFloat';

const note = (id: string, createdAt: string, o: Partial<AppNotification> = {}): AppNotification =>
  ({ id, kind: 'roadmap', audience: 'self', employee: { id: '7', name: '나' }, planId: 'p1', planTitle: '', track: '', reportId: null, createdAt, read: false, ...o }) as AppNotification;
const T1 = '2026-11-06T09:00:00+00:00';
const T2 = '2026-11-06T09:05:00+00:00';
const T3 = '2026-11-06T09:10:00+00:00';
const ids = () => useFloats.getState().items.map((n) => n.id);
const never = () => false;

describe('takeArrivals', () => {
  it('첫 목록은 기준으로만 삼고 고르지 않는다', () => {
    const { next, fresh } = takeArrivals(null, [note('a', T2), note('b', T1)]);
    expect(fresh).toEqual([]);
    expect([...next.known].sort()).toEqual(['a', 'b']);
    expect(next.latest).toBe(Date.parse(T2));
  });

  it('처음 보는 읽지 않은 알림만 서버 순서(최근 것 먼저)로 고른다', () => {
    const { next: base } = takeArrivals(null, [note('a', T1)]);
    const { fresh } = takeArrivals(base, [note('c', T3), note('b', T2), note('r', T3, { read: true }), note('a', T1)]);
    expect(fresh.map((n) => n.id)).toEqual(['c', 'b']);
  });

  it('처음 보는 id 라도 이미 본 가장 최근 알림보다 오래된 것은 고르지 않는다(50건 밖에 밀려 있던 옛 알림)', () => {
    const { next: base } = takeArrivals(null, [note('a', T2)]);
    expect(takeArrivals(base, [note('a', T2), note('old', T1)]).fresh).toEqual([]);
  });

  it('첫 목록이 비어 있었으면 다음에 온 알림은 모두 새 알림이다', () => {
    const { next: base } = takeArrivals(null, []);
    expect(base.latest).toBeNull();
    expect(takeArrivals(base, [note('a', T1)]).fresh.map((n) => n.id)).toEqual(['a']);
  });
});

describe('noteInbox', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetFloats();
  });
  afterEach(() => {
    resetFloats();
    vi.useRealTimers();
  });

  it('새 알림을 오래된 것부터 쌓고(가장 최근이 맨 아래), 같은 목록을 다시 받아도 다시 띄우지 않는다', () => {
    noteInbox('7:1', [note('a', T1)], never);
    expect(ids()).toEqual([]);
    const items = [note('c', T3), note('b', T2), note('a', T1)];
    noteInbox('7:1', items, never);
    expect(ids()).toEqual(['b', 'c']);
    noteInbox('7:1', items, never);
    expect(ids()).toEqual(['b', 'c']);
  });

  it('skip 에 걸린 알림(창이 열림·이미 그 화면)은 띄우지 않고, 본 것으로 남아 나중에도 뜨지 않는다', () => {
    noteInbox('7:1', [], never);
    noteInbox('7:1', [note('a', T1)], () => true);
    expect(ids()).toEqual([]);
    noteInbox('7:1', [note('a', T1)], never);
    expect(ids()).toEqual([]);
  });

  it('목록에서 빠진(읽음이 된) 알림은 바로 내린다', () => {
    noteInbox('7:1', [], never);
    noteInbox('7:1', [note('b', T2), note('a', T1)], never);
    noteInbox('7:1', [note('b', T2)], never);
    expect(ids()).toEqual(['b']);
  });

  it(`${FLOAT_MS}ms 뒤 내린다. 마우스를 올린 동안은 남고, 나가면 처음부터 다시 잰다`, () => {
    noteInbox('7:1', [], never);
    noteInbox('7:1', [note('a', T1)], never);
    vi.advanceTimersByTime(FLOAT_MS - 1);
    expect(ids()).toEqual(['a']);
    holdFloats('hover', true);
    vi.advanceTimersByTime(FLOAT_MS * 2);
    expect(ids()).toEqual(['a']);
    // 멈춘 동안 온 알림도 시간을 재지 않는다
    noteInbox('7:1', [note('b', T2), note('a', T1)], never);
    vi.advanceTimersByTime(FLOAT_MS * 2);
    expect(ids()).toEqual(['a', 'b']);
    holdFloats('hover', false);
    vi.advanceTimersByTime(FLOAT_MS - 1);
    expect(ids()).toEqual(['a', 'b']);
    vi.advanceTimersByTime(1);
    expect(ids()).toEqual([]);
  });

  it('닫으면 그 알림만 내리고, 다 내리면 멈춤도 풀린다', () => {
    noteInbox('7:1', [], never);
    noteInbox('7:1', [note('b', T2), note('a', T1)], never);
    holdFloats('hover', true);
    dismissFloat('a');
    expect(ids()).toEqual(['b']);
    dismissFloat('b');
    noteInbox('7:1', [note('c', T3)], never);
    vi.advanceTimersByTime(FLOAT_MS);
    expect(ids()).toEqual([]);
  });

  it('마우스와 초점은 따로 센다: 하나가 나가도 다른 하나가 남아 있으면 계속 멈춘다 (PR #134 리뷰)', () => {
    noteInbox('7:1', [], never);
    noteInbox('7:1', [note('a', T1)], never);
    holdFloats('hover', true);
    holdFloats('focus', true);
    holdFloats('hover', false); // 마우스만 나감 → 초점이 안에 있으니 그대로
    vi.advanceTimersByTime(FLOAT_MS * 2);
    expect(ids()).toEqual(['a']);
    holdFloats('hover', true);
    holdFloats('focus', false); // 초점만 나감 → 마우스가 안에 있으니 그대로
    vi.advanceTimersByTime(FLOAT_MS * 2);
    expect(ids()).toEqual(['a']);
    holdFloats('hover', false); // 둘 다 나감 → 처음부터 다시 잰다
    vi.advanceTimersByTime(FLOAT_MS - 1);
    expect(ids()).toEqual(['a']);
    vi.advanceTimersByTime(1);
    expect(ids()).toEqual([]);
  });

  it('초점이 있던 카드를 닫은 뒤 실제 상태로 맞추면(blur 없음) 남은 카드의 시간을 다시 잰다 (PR #134 리뷰)', () => {
    noteInbox('7:1', [], never);
    noteInbox('7:1', [note('b', T2), note('a', T1)], never);
    holdFloats('focus', true);
    dismissFloat('b'); // 키보드로 닫음. 카드가 남아 있어 멈춤은 그대로이고, DOM 에서 빠진 버튼의 blur 는 오지 않는다
    vi.advanceTimersByTime(FLOAT_MS * 2);
    expect(ids()).toEqual(['a']);
    holdFloats('focus', false); // NotificationBell 이 카드가 바뀐 뒤 document.activeElement 를 보고 부른다
    vi.advanceTimersByTime(FLOAT_MS);
    expect(ids()).toEqual([]);
  });

  it('이미 같은 상태면 시간을 다시 재지 않는다(카드가 바뀔 때마다 실제 상태로 맞춰도 시간이 늘어나지 않게)', () => {
    noteInbox('7:1', [], never);
    noteInbox('7:1', [note('a', T1)], never);
    vi.advanceTimersByTime(FLOAT_MS - 1);
    holdFloats('focus', false);
    holdFloats('hover', false);
    vi.advanceTimersByTime(1);
    expect(ids()).toEqual([]);
  });

  it('로그인이 바뀌면(같은 직원의 재로그인 포함) 띄운 알림을 버리고 그 목록을 새 기준으로 삼는다', () => {
    noteInbox('7:1', [], never);
    noteInbox('7:1', [note('a', T1)], never);
    expect(ids()).toEqual(['a']);
    noteInbox('7:2', [note('b', T2), note('a', T1)], never);
    expect(ids()).toEqual([]);
    noteInbox('7:2', [note('c', T3), note('b', T2), note('a', T1)], never);
    expect(ids()).toEqual(['c']);
  });
});

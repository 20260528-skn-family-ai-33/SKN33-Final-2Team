/* 완료 알림(#82): 받는 쪽(본인·부서장)과 종류(로드맵·보고서)에 따라 문구와 이동할 주소가 맞는지 */
import { describe, expect, it } from 'vitest';
import type { AppNotification } from '@/api/types/notification';
import { needsWorkspace, notificationSub, notificationTarget, notificationTime, notificationTitle } from './notificationView';

const base: AppNotification = {
  id: 'n1',
  kind: 'roadmap',
  audience: 'self',
  employee: { id: '8', name: '김직원' },
  planId: 'p1',
  planTitle: 'SQL 분석 역량',
  track: 'A2',
  reportId: null,
  createdAt: '2026-11-04T09:00:00+09:00',
  read: false,
};
const n = (o: Partial<AppNotification>): AppNotification => ({ ...base, ...o });

describe('notificationTarget', () => {
  it('본인 알림은 내 로드맵·결과 보고서로', () => {
    expect(notificationTarget(base)).toBe('/roadmaps/p1');
    expect(notificationTarget(n({ kind: 'report', reportId: 'r1' }))).toBe('/reports/r1');
  });
  it('부서장 알림은 그 직원의 로드맵·결과 보고서로', () => {
    expect(notificationTarget(n({ audience: 'head' }))).toBe('/team/8/plans/p1');
    expect(notificationTarget(n({ audience: 'head', kind: 'report', reportId: 'r1' }))).toBe('/team/8/reports/r1');
  });
  it('보고서 id 가 빠진 보고서 알림은 로드맵으로(빈 주소로 가지 않음)', () => {
    expect(notificationTarget(n({ kind: 'report', reportId: null }))).toBe('/roadmaps/p1');
  });
});

describe('문구', () => {
  it('부서장에게는 직원 이름을, 본인에게는 이름 없이', () => {
    expect(notificationTitle(n({ audience: 'head' }))).toBe('김직원 님이 새 로드맵 작성을 마쳤어요');
    expect(notificationTitle(n({ audience: 'head', kind: 'report', reportId: 'r1' }))).toBe('김직원 님의 결과 보고서 작성이 끝났어요');
    expect(notificationTitle(base)).toBe('새 로드맵 작성을 마쳤어요');
    expect(notificationTitle(n({ kind: 'report', reportId: 'r1' }))).toBe('결과 보고서 작성이 끝났어요');
  });
  it('부제는 로드맵 제목 · 트랙 이름, 없는 값은 뺀다', () => {
    expect(notificationSub(base)).toBe('SQL 분석 역량 · Crash Course');
    expect(notificationSub(n({ track: '' }))).toBe('SQL 분석 역량');
    expect(notificationSub(n({ planTitle: '', track: 'zz' }))).toBe('');
  });
});

describe('notificationTime', () => {
  const now = new Date('2026-11-04T12:00:00+09:00');
  it('가까운 시각은 상대 시간, 하루가 지나면 날짜', () => {
    expect(notificationTime('2026-11-04T11:59:30+09:00', now)).toBe('방금');
    expect(notificationTime('2026-11-04T11:45:00+09:00', now)).toBe('15분 전');
    expect(notificationTime('2026-11-04T09:00:00+09:00', now)).toBe('3시간 전');
    expect(notificationTime('2026-11-02T12:00:00+09:00', now)).toMatch(/^2026-11-0[12]$/);
  });
  it('읽을 수 없는 값은 빈칸', () => {
    expect(notificationTime('nope', now)).toBe('');
  });
});

describe('needsWorkspace', () => {
  const ws = { plans: { p1: {} }, reports: [{ id: 'r1' }] };
  it('본인 알림인데 화면에 아직 없는 로드맵·보고서면 다시 받는다', () => {
    expect(needsWorkspace(base, ws)).toBe(false);
    expect(needsWorkspace(n({ planId: 'p2' }), ws)).toBe(true);
    expect(needsWorkspace(n({ kind: 'report', reportId: 'r1' }), ws)).toBe(false);
    expect(needsWorkspace(n({ kind: 'report', reportId: 'r2' }), ws)).toBe(true);
  });
  it('부서장 알림은 부서장 화면이 직접 받으므로 다시 받지 않는다', () => {
    expect(needsWorkspace(n({ audience: 'head', planId: 'p2' }), ws)).toBe(false);
  });
});

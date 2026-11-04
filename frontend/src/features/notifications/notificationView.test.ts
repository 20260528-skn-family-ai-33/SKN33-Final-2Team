/* 완료 알림(#82): 받는 쪽(본인·부서장)과 종류(로드맵·보고서)에 따라 문구와 이동할 주소가 맞는지 */
import { describe, expect, it } from 'vitest';
import type { AppNotification } from '@/api/types/notification';
import { mergeReports, notificationSub, notificationTarget, notificationTime, notificationTitle } from './notificationView';

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

describe('mergeReports', () => {
  const cur = [
    { id: 'old', planId: 'p1' },
    { id: 'other', planId: 'p2' },
  ];
  it('그 로드맵의 옛 보고서(다시 만들어 서버에서 지워진 것)는 빼고 새 보고서를 앞에 둔다', () => {
    expect(mergeReports(cur, 'p1', [{ id: 'new', planId: 'p1' }])).toEqual([
      { id: 'new', planId: 'p1' },
      { id: 'other', planId: 'p2' },
    ]);
  });
  it('다른 로드맵 보고서는 서버 응답에 섞여 와도 건드리지 않는다', () => {
    expect(mergeReports(cur, 'p1', [{ id: 'x', planId: 'p2' }])).toEqual([{ id: 'other', planId: 'p2' }]);
  });
});

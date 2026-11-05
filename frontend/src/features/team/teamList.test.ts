/* 소속 직원 목록 정렬(#96): 확인 전 기록 있는 직원 → 기록 있는 직원 → 기록 없는 직원(접어 둠) */
import { describe, expect, it } from 'vitest';
import type { TeamMember } from '@/api/types/team';
import { arrangeMembers, hasRecords, unseenOf } from './teamList';

const mem = (id: string, o: Partial<TeamMember> = {}): TeamMember =>
  ({ user: { id }, activePlans: 0, pastPlans: 0, reports: 0, unreadComments: 0, unseenPlans: 0, unseenReports: 0, ...o }) as TeamMember;
const ids = (list: TeamMember[]) => list.map((m) => m.user.id);

describe('arrangeMembers', () => {
  it('확인 전 기록이 있는 직원을 맨 앞, 기록만 있는 직원을 다음, 기록 없는 직원은 따로 둔다', () => {
    const list = [
      mem('none1'),
      mem('has1', { activePlans: 1 }),
      mem('new1', { pastPlans: 1, unseenReports: 1 }),
      mem('none2'),
      mem('has2', { pastPlans: 2 }),
      mem('new2', { activePlans: 1, unseenPlans: 1 }),
    ];
    const { shown, empty } = arrangeMembers(list);
    expect(ids(shown)).toEqual(['new1', 'new2', 'has1', 'has2']); // 같은 묶음 안은 서버 순서 그대로
    expect(ids(empty)).toEqual(['none1', 'none2']);
  });
  it('원래 배열은 바꾸지 않는다', () => {
    const list = [mem('a'), mem('b', { activePlans: 1 })];
    arrangeMembers(list);
    expect(ids(list)).toEqual(['a', 'b']);
  });
  it('기록이 없는데 확인 전 수만 남은 직원은 들어갈 화면이 없어 접힌 쪽에 둔다', () => {
    expect(ids(arrangeMembers([mem('x', { unseenPlans: 1 })]).empty)).toEqual(['x']);
  });
  it('빈 목록', () => {
    expect(arrangeMembers([])).toEqual({ shown: [], empty: [] });
  });
});

describe('hasRecords · unseenOf', () => {
  it('지난 로드맵만 있어도 기록이 있다', () => {
    expect(hasRecords(mem('a', { pastPlans: 1 }))).toBe(true);
    expect(hasRecords(mem('a', { reports: 1 }))).toBe(false);
  });
  it('확인 전 수는 로드맵과 보고서를 더하고, 서버가 값을 빠뜨려도 0으로 본다', () => {
    expect(unseenOf(mem('a', { unseenPlans: 2, unseenReports: 1 }))).toBe(3);
    expect(unseenOf({ ...mem('a'), unseenPlans: undefined } as unknown as TeamMember)).toBe(0);
  });
});

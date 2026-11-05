/* 소속 직원 목록 정렬(#96): 확인 전 로드맵·보고서가 있는 직원 → 로드맵이 있는 직원 → 없는 직원 순.
   로드맵·보고서가 없는 직원은 화면에서 접어 둔다. 같은 묶음 안은 서버 순서 그대로 둔다 */
import type { TeamMember } from '@/api/types/team';

/** 볼 수 있는 기록이 있는지(보고서는 로드맵에 딸려 있어 로드맵 수로 본다) */
export const hasRecords = (m: TeamMember): boolean => m.activePlans + m.pastPlans > 0;

/** 부서장이 아직 확인하지 않은 로드맵·보고서 수 */
export const unseenOf = (m: TeamMember): number => (m.unseenPlans || 0) + (m.unseenReports || 0);

/** 직원 로드맵·보고서 상세가 실제로 화면에 보이는지(PR #107 리뷰) — 이때만 그 대상 알림을 읽음으로 바꾼다.
 *  직원 기록이 먼저 도착해도 소속 직원 목록을 기다리는 동안(로딩 화면)은 아직 본 것이 아니다 */
export function detailShown(gate: { gone: boolean; teamLoading: boolean; member: unknown }, found: boolean): boolean {
  return !gate.gone && !gate.teamLoading && !!gate.member && found;
}

const tier = (m: TeamMember): number => (!hasRecords(m) ? 2 : unseenOf(m) ? 0 : 1);

export function arrangeMembers(members: TeamMember[]): { shown: TeamMember[]; empty: TeamMember[] } {
  const sorted = [...members].sort((a, b) => tier(a) - tier(b));
  return { shown: sorted.filter((m) => tier(m) < 2), empty: sorted.filter((m) => tier(m) === 2) };
}

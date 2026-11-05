/* 완료 알림(#82)을 눌렀을 때·읽음 처리할 때의 서버 동기화 — PR #84 리뷰 반영
   1) 알림 캐시는 직원별 키에 두고, 응답이 늦게 와도 그사이 로그인이 바뀌었으면(같은 직원의 재로그인 포함) 넣지도 이동하지도 않는다
   2) 부서장 알림은 그 직원 기록 캐시를 새로 받기 시작한 뒤 이동한다(같은 화면에서 보고서 id 만 바뀌어도 새 보고서가 보이게)
   3) 본인 알림은 작업 공간 전체를 다시 받지 않는다. 화면에 이미 있는 로드맵은 덮지 않고(저장 전 사후 점검 입력 등 보존),
      없을 때만 받는다. 보고서 알림은 그 로드맵의 보고서 목록만 받아 바꾼다 */
import type { QueryClient } from '@tanstack/react-query';
import { notificationsApi } from '@/api/endpoints/notifications';
import type { AppNotification, NotificationInbox, NotificationKind } from '@/api/types/notification';
import { plansApi } from '@/api/endpoints/plans';
import { memberKey, memberKeyAll, teamKey } from '@/features/team/teamData';
import { mergeReg, mergeRes } from '@/shared/state/catalog';
import { me, signInSeq } from '@/shared/state/session';
import { putRec, updateWs, ws } from '@/shared/state/workspace';
import { mergeReports } from './notificationView';

/** 알림 캐시 키: 로그인한 직원마다 따로(로그아웃 뒤 다른 직원이 이전 직원 알림을 보지 않게) */
export const notificationKey = (owner: string) => ['notifications', owner] as const;

/** 요청을 시작한 로그인: 직원 id 와 로그인 회차. 같은 직원이 다시 로그인해도 회차가 달라 구분된다 */
export interface SignIn {
  id: string;
  seq: number;
}

export const currentSignIn = (): SignIn | null => {
  const u = me();
  return u ? { id: u.id, seq: signInSeq() } : null;
};

/** 요청을 시작한 그 로그인이 아직 이어지고 있는지 */
export const stillSignedIn = (t: SignIn): boolean => signInSeq() === t.seq && me()?.id === t.id;

/** 소속 직원 목록·직원 기록의 '새 로드맵·보고서' 표시와 정렬은 부서장 알림의 읽음 여부로 정해진다(#96).
 *  어느 경로로든 알림이 읽음이 되면 두 캐시를 무효화한다: 보고 있는 화면은 바로, 나머지는 다음에 들어갈 때 다시 받는다.
 *  부서장이 아니면 목록 조회가 꺼져 있어(useTeam enabled) 아무것도 받지 않는다 (PR #107 리뷰) */
function refreshTeamMarks(qc: QueryClient): Promise<unknown> {
  return Promise.all([qc.invalidateQueries({ queryKey: teamKey }), qc.invalidateQueries({ queryKey: memberKeyAll })]);
}

/** 한 건(id) 또는 모두(id 없음) 읽음. 응답이 왔을 때 같은 로그인이면 그 직원 캐시에 넣고 true, 로그인이 바뀌었으면 버리고 false.
 *  소속 직원 목록·기록 캐시도 무효화하되 다시 받기를 기다리지 않는다(알림을 누른 뒤 이동이 목록 다시 받기에 막히지 않게) */
export async function markRead(qc: QueryClient, t: SignIn, id?: string): Promise<boolean> {
  const box: NotificationInbox = id ? await notificationsApi.read(id) : await notificationsApi.readAll();
  if (!stillSignedIn(t)) return false;
  qc.setQueryData(notificationKey(t.id), box);
  void refreshTeamMarks(qc);
  return true;
}

/** 그 로드맵·보고서의 내 알림을 모두 읽음으로(#96). 같은 로그인이면 바뀐 목록을 그 직원 캐시에 넣고 true.
 *  실제로 읽음이 된 알림이 있으면 소속 직원 목록·직원 기록 캐시도 무효화한다. 읽음 응답보다 먼저 끝난 목록 조회가
 *  '새 로드맵·보고서' 표시와 우선 정렬을 옛 값으로 남기지 않게(PR #107 리뷰). 보고 있는 화면의 캐시는 바로 다시 받는다 */
export async function markTargetRead(qc: QueryClient, t: SignIn, kind: NotificationKind, id: string): Promise<boolean> {
  const res = await notificationsApi.readTarget(kind, id);
  if (!stillSignedIn(t)) return false;
  qc.setQueryData<NotificationInbox>(notificationKey(t.id), { items: res.items, unread: res.unread });
  if (res.changed > 0) await refreshTeamMarks(qc);
  return true;
}

/** 알림 대상의 최신 기록을 받는다.
 *  부서장: 그 직원 기록 캐시를 화면에 쓰지 않는 중이어도 새로 받는다(캐시에 남은 옛 기록으로 '보고서 없음 → 목록으로' 되지 않게).
 *    부르는 쪽은 기다리지 않고 바로 이동한다. 이동한 화면은 받는 동안 '불러오는 중'을 보여 준다(TeamPages).
 *  본인: 작업 공간에 없는 로드맵만 받아 넣는다(있는 로드맵을 서버 값으로 덮으면 저장 전 입력이 사라진다).
 *    보고서 알림이면 그 로드맵의 보고서 목록만 바꾼다. 로그인이 바뀌었으면 넣지 않는다. 부르는 쪽은 기다린 뒤 이동한다 */
export async function refreshTarget(qc: QueryClient, t: SignIn, n: AppNotification): Promise<void> {
  if (n.audience === 'head') {
    await qc.invalidateQueries({ queryKey: memberKey(n.employee.id), refetchType: 'all' });
    return;
  }
  const loaded = !!ws().plans[n.planId];
  const [plan, reports] = await Promise.all([
    loaded ? Promise.resolve(null) : plansApi.get(n.planId),
    n.kind === 'report' ? plansApi.reports(n.planId) : Promise.resolve(null),
  ]);
  if (!stillSignedIn(t) || ws().owner !== t.id) return;
  if (plan) {
    mergeRes(plan.res);
    mergeReg(plan.reg);
  }
  updateWs((s) => {
    // 받는 사이 다른 곳에서 그 로드맵을 넣었으면 그것을 둔다
    if (plan && !s.plans[n.planId]) putRec(s, plan.plan);
    if (reports) s.reports = mergeReports(s.reports, n.planId, reports);
  });
}

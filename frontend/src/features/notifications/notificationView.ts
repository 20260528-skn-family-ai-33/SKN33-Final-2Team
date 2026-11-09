/* 완료 알림(#82)의 문구·이동할 주소 — 서버는 종류·받는 쪽·대상 id 만 보내고 화면이 정한다 */
import type { AppNotification, NotificationJobKind } from '@/api/types/notification';
import { paths } from '@/app/paths';
import { trackName } from '@/shared/constants/data';

/** 작업 알림을 누르면 갈 곳(결과를 보거나 다시 시도하는 화면) */
function jobTarget(kind: NotificationJobKind | null, planId: string): string {
  if (kind === 'materials') return paths.newMaterials;
  if (kind === 'revision') return paths.revise(planId);
  if (kind === 'report') return paths.post(planId);
  return paths.newOptions;
}

/** 누르면 갈 곳: 본인은 내 로드맵·결과 보고서, 부서장은 그 직원의 로드맵·결과 보고서, 코멘트는 받은 코멘트, 작업은 그 작업의 화면 */
export function notificationTarget(n: AppNotification): string {
  const planId = n.planId ?? '';
  if (n.kind === 'job') return jobTarget(n.jobKind, planId);
  if (n.kind === 'comment') return paths.comments(planId);
  const head = n.audience === 'head';
  if ((n.kind === 'report' || n.kind === 'task' || n.kind === 'task_result') && n.reportId) return head ? paths.memberReport(n.employee.id, n.reportId) : paths.report(n.reportId);
  return head ? paths.memberPlan(n.employee.id, planId) : paths.roadmap(planId);
}

/** 로드맵 확정 전 작업의 알림이 지금 작성 중인 문서가 아닌 다른 문서의 것인지. 작성 화면 주소는 문서마다 같아 주소만으로는 구분되지 않는다(PR #139 리뷰) */
export function isOtherDraft(n: AppNotification, currentDraftId: string | null): boolean {
  return n.kind === 'job' && !n.planId && n.draftId !== currentDraftId;
}

/** 지금 보고 있는 화면을 가리키는 읽지 않은 알림(#96). 이미 본 일이 알림 창에 쌓이지 않게 읽음으로 바꾼다.
 *  부서장의 로드맵·보고서 알림은 기록이 실제로 화면에 보일 때 useMarkSeen 이 처리하므로 뺀다 */
export function viewedNow(items: AppNotification[], pathname: string, currentDraftId: string | null): AppNotification[] {
  return items.filter((n) => !n.read && (n.audience !== 'head' || n.kind === 'task_result') && notificationTarget(n) === pathname && !isOtherDraft(n, currentDraftId));
}

const JOB_TITLE: Record<NotificationJobKind, { done: string; failed: string }> = {
  options: { done: '로드맵 3안 작성이 끝났어요', failed: '로드맵 3안 중 만들지 못한 안이 있어요' },
  regenerate: { done: '다시 만든 안이 준비됐어요', failed: '안을 다시 만들지 못했어요' },
  materials: { done: '학습 자료 추천이 끝났어요', failed: '학습 자료를 추천하지 못했어요' },
  revision: { done: '수정안 작성이 끝났어요', failed: '수정안을 만들지 못했어요' },
  report: { done: '결과 보고서 작성이 끝났어요', failed: '결과 보고서를 작성하지 못했어요' },
};

/** bare: 직원별 묶음 안처럼 직원 이름이 위에 이미 보이면 이름을 뺀다(#96) */
export function notificationTitle(n: AppNotification, bare = false): string {
  if (n.kind === 'job') return n.jobKind ? JOB_TITLE[n.jobKind][n.jobStatus === 'failed' ? 'failed' : 'done'] : '작업이 끝났어요';
  if (n.kind === 'comment') return `${n.employee.name} 님이 로드맵에 코멘트를 보냈어요`;
  if (n.kind === 'task') return `${n.employee.name} 님이 과제를 보냈어요`;
  if (n.kind === 'task_result') return bare ? '과제 결과를 제출했어요' : `${n.employee.name} 님이 과제 결과를 제출했어요`;
  if (n.audience === 'head' && !bare)
    return n.kind === 'report' ? `${n.employee.name} 님의 결과 보고서 작성이 끝났어요` : `${n.employee.name} 님이 새 로드맵 작성을 마쳤어요`;
  return n.kind === 'report' ? '결과 보고서 작성이 끝났어요' : '새 로드맵 작성을 마쳤어요';
}

/** 한 소속 직원에게서 생긴 알림 묶음(#96) */
export interface StaffGroup {
  employee: AppNotification['employee'];
  /** 서버 순서 그대로(최근 것 먼저) */
  items: AppNotification[];
  unread: number;
  latestAt: string;
}

/** 본인 알림(위)과 소속 직원 알림(아래)을 나누고, 소속 직원 알림은 직원별로 묶는다(#96).
 *  서버가 최근 순으로 보내므로 따로 정렬하지 않는다. 묶음도 가장 최근 알림이 앞선 직원부터 */
export function splitNotifications(items: AppNotification[]): { mine: AppNotification[]; staff: StaffGroup[] } {
  const mine: AppNotification[] = [];
  const staff = new Map<string, StaffGroup>();
  for (const n of items) {
    if (n.audience !== 'head') {
      mine.push(n);
      continue;
    }
    const g = staff.get(n.employee.id);
    if (g) {
      g.items.push(n);
      if (!n.read) g.unread += 1;
    } else {
      staff.set(n.employee.id, { employee: n.employee, items: [n], unread: n.read ? 0 : 1, latestAt: n.createdAt });
    }
  }
  return { mine, staff: [...staff.values()] };
}

/** 묶음 줄의 부제: 종류별 건수(없는 종류는 뺀다) */
export function staffGroupSub(g: StaffGroup): string {
  const count = (kind: AppNotification['kind']) => g.items.filter((n) => n.kind === kind).length;
  const parts: [string, number][] = [['로드맵', count('roadmap')], ['결과 보고서', count('report')], ['과제 결과', count('task_result')]];
  return parts.filter(([, n]) => n).map(([label, n]) => `${label} ${n}건`).join(' · ');
}

export function notificationSub(n: AppNotification): string {
  return [n.planTitle, trackName(n.track)].filter(Boolean).join(' · ');
}

const pad = (v: number) => String(v).padStart(2, '0');

/** 1분 안 '방금', 1시간 안 'N분 전', 하루 안 'N시간 전', 그 뒤는 날짜(이 기기의 시간대) */
export function notificationTime(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '';
  const min = Math.floor((now.getTime() - at.getTime()) / 60000);
  if (min < 1) return '방금';
  if (min < 60) return `${min}분 전`;
  if (min < 60 * 24) return `${Math.floor(min / 60)}시간 전`;
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
}

/** 한 로드맵의 보고서만 서버에서 새로 받은 것으로 바꾼다. 확인 전 보고서를 다시 만들면 서버는 이전 보고서를 지우므로
 *  그 로드맵의 옛 보고서는 남기지 않고, 다른 로드맵의 보고서는 그대로 둔다. 새 보고서를 앞에(서버 목록처럼 최근 것 먼저) */
export function mergeReports<T extends { planId: string }>(current: T[], planId: string, fresh: T[]): T[] {
  return [...fresh.filter((r) => r.planId === planId), ...current.filter((r) => r.planId !== planId)];
}

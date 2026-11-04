/* 완료 알림(#82)의 문구·이동할 주소 — 서버는 종류·받는 쪽·대상 id 만 보내고 화면이 정한다 */
import type { AppNotification } from '@/api/types/notification';
import { paths } from '@/app/paths';
import { trackName } from '@/shared/constants/data';

/** 누르면 갈 곳: 본인은 내 로드맵·결과 보고서, 부서장은 그 직원의 로드맵·결과 보고서 */
export function notificationTarget(n: AppNotification): string {
  const head = n.audience === 'head';
  if (n.kind === 'report' && n.reportId) return head ? paths.memberReport(n.employee.id, n.reportId) : paths.report(n.reportId);
  return head ? paths.memberPlan(n.employee.id, n.planId) : paths.roadmap(n.planId);
}

export function notificationTitle(n: AppNotification): string {
  if (n.audience === 'head')
    return n.kind === 'report' ? `${n.employee.name} 님의 결과 보고서 작성이 끝났어요` : `${n.employee.name} 님이 새 로드맵 작성을 마쳤어요`;
  return n.kind === 'report' ? '결과 보고서 작성이 끝났어요' : '새 로드맵 작성을 마쳤어요';
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

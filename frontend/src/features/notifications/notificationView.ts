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

/** 본인 알림인데 화면이 들고 있는 작업 공간에 그 로드맵·보고서가 아직 없으면(백그라운드로 끝난 보고서 등) 이동 전에 다시 받는다.
 *  부서장 화면은 들어갈 때마다 서버에서 새로 받으므로 필요 없다 */
export function needsWorkspace(n: AppNotification, ws: { plans: Record<string, unknown>; reports: { id: string }[] }): boolean {
  if (n.audience !== 'self') return false;
  return n.kind === 'report' ? !ws.reports.some((r) => r.id === n.reportId) : !ws.plans[n.planId];
}

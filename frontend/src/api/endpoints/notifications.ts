/* 완료 알림 (#82) — 직원 계정만. 읽음 처리는 바뀐 목록을 그대로 돌려준다 */
import { enc, http } from '../client';
import type { NotificationInbox, NotificationKind, NotificationTargetRead } from '../types/notification';

export const notificationsApi = {
  inbox: () => http.get<NotificationInbox>('/notifications'),
  read: (id: string) => http.post<NotificationInbox>(`/notifications/${enc(id)}/read`),
  readAll: () => http.post<NotificationInbox>('/notifications/read-all'),
  /** 그 로드맵·보고서의 내 알림을 모두 읽음으로(#96 · 부서장이 직원 기록 화면을 열 때) */
  readTarget: (kind: NotificationKind, id: string) => http.post<NotificationTargetRead>('/notifications/read-target', { kind, id }),
};

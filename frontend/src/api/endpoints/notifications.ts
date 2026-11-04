/* 완료 알림 (#82) — 직원 계정만. 읽음 처리는 바뀐 목록을 그대로 돌려준다 */
import { enc, http } from '../client';
import type { NotificationInbox } from '../types/notification';

export const notificationsApi = {
  inbox: () => http.get<NotificationInbox>('/notifications'),
  read: (id: string) => http.post<NotificationInbox>(`/notifications/${enc(id)}/read`),
  readAll: () => http.post<NotificationInbox>('/notifications/read-all'),
};

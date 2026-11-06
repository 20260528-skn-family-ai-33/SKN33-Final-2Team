/* 완료 알림 (#82 · 설계서 밖 추가) — 로드맵 확정·결과 보고서 작성이 끝나면 작성한 직원 본인(self)과 그 직원 부서의 부서장(head)에게 남는다 */

export type NotificationKind = 'roadmap' | 'report';
export type NotificationAudience = 'self' | 'head';

export interface AppNotification {
  id: string;
  kind: NotificationKind;
  audience: NotificationAudience;
  /** 로드맵·보고서를 작성한 직원(본인 알림이면 나) */
  employee: { id: string; name: string };
  planId: string;
  /** 로드맵 제목(displayTitle, 없으면 목표) */
  planTitle: string;
  /** 코스 id(A1~A3) */
  track: string;
  /** kind 가 report 일 때만 */
  reportId: string | null;
  /** ISO 시각 */
  createdAt: string;
  read: boolean;
}

/** 대상 읽음(#96)의 응답: 바뀐 목록과 이번에 읽음으로 바뀐 알림 수 */
export interface NotificationTargetRead extends NotificationInbox {
  changed: number;
}

export interface NotificationInbox {
  /** 최근 50건 */
  items: AppNotification[];
  /** 목록 길이와 관계없이 읽지 않은 전체 수 */
  unread: number;
}

/* 완료 알림 (#82 · 설계서 밖 추가) — 로드맵 확정·결과 보고서 작성이 끝나면 작성한 직원 본인(self)과 그 직원 부서의 부서장(head)에게 남는다 */

export type NotificationKind = 'roadmap' | 'report' | 'job' | 'comment';
/** 대상 읽음(POST /notifications/read-target)에 쓰는 종류 */
export type NotificationTargetKind = 'roadmap' | 'report';
/** self: 본인 일 · head: 소속 직원 일을 받는 부서장 · member: 부서장이 한 일을 받는 직원(#96) */
export type NotificationAudience = 'self' | 'head' | 'member';
/** 끝나면 본인에게 알리는 작업(#96). report 는 실패만(성공은 kind 'report' 알림) */
export type NotificationJobKind = 'options' | 'regenerate' | 'materials' | 'revision' | 'report';

export interface AppNotification {
  id: string;
  kind: NotificationKind;
  audience: NotificationAudience;
  /** 알림을 일으킨 사람: 로드맵·보고서를 작성한 직원(본인 알림이면 나), 코멘트 알림이면 보낸 부서장 */
  employee: { id: string; name: string };
  /** 로드맵 확정 전 작업(kind 'job' 의 options·regenerate·materials)만 null */
  planId: string | null;
  /** 로드맵 제목(displayTitle, 없으면 목표). 로드맵 확정 전 작업은 작성 중인 목표 */
  planTitle: string;
  /** 코스 id(A1~A3) */
  track: string;
  /** kind 가 report 일 때만 */
  reportId: string | null;
  /** 로드맵 확정 전 작업의 작성 문서 */
  draftId: string | null;
  /** kind 가 comment 일 때만 */
  commentId: string | null;
  /** kind 가 job 일 때만 */
  jobKind: NotificationJobKind | null;
  jobStatus: 'done' | 'failed' | null;
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

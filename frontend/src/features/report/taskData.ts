/* 결과 보고서 과제(#96)의 캐시 키와 제한. 화면(ReportTasks)과 알림(notificationActions)이 함께 쓴다 */
export const taskKey = (planId: string) => ['report-tasks', planId] as const;

/** 서버 제한과 같은 값(services/report_tasks.py) */
export const TASK_BODY_MAX = 2000;
export const TASK_ANSWER_MAX = 4000;
export const TASK_FILE_MAX = 15_000_000;

/* 결과 보고서 과제 (#96) — 부서장이 결과 보고서를 보고 내는 과제와 직원의 제출 결과 */

export interface ReportTask {
  id: string;
  planId: string;
  body: string;
  /** YYYY-MM-DD */
  createdAt: string;
  /** 과제를 낸 부서장 */
  head: { id: string; name: string };
  /** 제출 전이면 null */
  submittedAt: string | null;
  answer: string;
  file: { name: string; size: number } | null;
}

export interface ReportTaskList {
  tasks: ReportTask[];
}

/* 결과 보고서 과제(#96)의 캐시 키와 제한. 화면(ReportTasks)과 알림(notificationActions)이 함께 쓴다 */
import type { QueryClient } from '@tanstack/react-query';
import type { ReportTask } from '@/api/types/task';

export const taskKey = (planId: string) => ['report-tasks', planId] as const;

/** 제출은 한 번뿐이고 고칠 수 없어서, 제출한 과제가 제출 전으로 돌아갈 일은 없다.
 *  같은 보고서의 과제를 동시에 내면 응답 순서가 바뀌어 더 오래된 목록이 나중에 올 수 있으므로 이미 받은 제출 내용을 유지한다(PR #140 리뷰) */
function keepSubmitted(tasks: ReportTask[], current: ReportTask[] | undefined): ReportTask[] {
  const submitted = new Map((current ?? []).filter((t) => t.submittedAt).map((t) => [t.id, t]));
  return tasks.map((t) => (t.submittedAt ? t : (submitted.get(t.id) ?? t)));
}

/** 서버가 돌려준 과제 목록을 캐시에 넣는다. 먼저 시작한 조회의 응답이 늦게 오면 제출·전송 전 목록으로 덮으므로 진행 중인 조회를 취소한다.
 *  요청 전이 아니라 응답을 받은 뒤에 취소해야 요청하는 동안 새로 시작한 조회까지 막는다(PR #140 리뷰) */
export async function putTasks(qc: QueryClient, planId: string, tasks: ReportTask[]): Promise<void> {
  await qc.cancelQueries({ queryKey: taskKey(planId) });
  qc.setQueryData<ReportTask[]>(taskKey(planId), (current) => keepSubmitted(tasks, current));
}

/** 서버 제한과 같은 값(services/report_tasks.py) */
export const TASK_BODY_MAX = 2000;
export const TASK_ANSWER_MAX = 4000;
export const TASK_FILE_MAX = 15_000_000;

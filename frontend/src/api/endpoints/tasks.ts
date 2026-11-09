/* 결과 보고서 과제 (#96) */
import { API_BASE, enc, http } from '../client';
import type { ReportTaskList } from '../types/task';

export const tasksApi = {
  // 직원
  mine: (planId: string) => http.get<ReportTaskList>(`/plans/${enc(planId)}/tasks`),
  submit: (planId: string, taskId: string, answer: string, file: File | null) => {
    const form = new FormData();
    form.append('answer', answer);
    if (file) form.append('file', file, file.name);
    return http.post<ReportTaskList>(`/plans/${enc(planId)}/tasks/${enc(taskId)}/submit`, form);
  },
  // 부서장
  ofMember: (planId: string) => http.get<ReportTaskList>(`/team/plans/${enc(planId)}/tasks`),
  send: (planId: string, body: string) => http.post<ReportTaskList>(`/team/plans/${enc(planId)}/tasks`, { body }),
};

/** 제출 파일 내려받기 주소. 부서장은 소속 직원 것만 받을 수 있다(서버가 확인) */
export const taskFileUrl = (planId: string, taskId: string, asHead: boolean): string =>
  `${API_BASE}${asHead ? '/team' : ''}/plans/${enc(planId)}/tasks/${enc(taskId)}/file`;

/* 관리자 화면 서버 데이터 (TanStack Query) — 개요·시트 행·변경 이력·미리보기.
   저장·반영하면 바뀐 데이터의 행과 개요·이력을 다시 받는다(5차 st.cache·st.overview·st.history 를 비우던 것과 같음) */
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '@/api/endpoints/admin';
import { queryClient } from '@/app/queryClient';
import { PAGE } from './datasets';

export const adminKeys = {
  overview: ['admin', 'overview'] as const,
  rowsOf: (ds: string) => ['admin', 'rows', ds] as const,
  rows: (ds: string, sheet: string, q: string, page: number) => ['admin', 'rows', ds, sheet, q, page] as const,
  uploads: ['admin', 'uploads'] as const,
  upload: (id: string) => ['admin', 'upload', id] as const,
  goalEmployees: ['admin', 'goal-employees'] as const,
  regulations: ['admin', 'regulations'] as const,
  regulationUploads: ['admin', 'regulation-uploads'] as const,
};

export const useOverview = () => useQuery({ queryKey: adminKeys.overview, queryFn: adminApi.overview });

export const useRows = (ds: string, sheet: string, q: string, page: number) =>
  useQuery({ queryKey: adminKeys.rows(ds, sheet, q, page), queryFn: () => adminApi.rows(ds, sheet, { q, limit: PAGE, offset: page * PAGE }) });

export const useUploads = () => useQuery({ queryKey: adminKeys.uploads, queryFn: () => adminApi.uploads('') });

export const useUpload = (id: string) => useQuery({ queryKey: adminKeys.upload(id), queryFn: () => adminApi.upload(id), enabled: !!id });

/** 데이터가 바뀐 뒤: 그 데이터(없으면 전부)의 행과 개요·이력을 다시 받는다 */
export function refreshAdmin(ds?: string): void {
  void queryClient.invalidateQueries({ queryKey: ds ? adminKeys.rowsOf(ds) : ['admin', 'rows'] });
  void queryClient.invalidateQueries({ queryKey: adminKeys.overview });
  void queryClient.invalidateQueries({ queryKey: adminKeys.uploads });
}

/** 목표 후보 다시 만들기 창의 직원 고르기 목록(창을 열 때마다 새로 받는다) */
export const useGoalEmployees = () => useQuery({ queryKey: adminKeys.goalEmployees, queryFn: adminApi.goalEmployees, staleTime: 0 });

/** 규정 데이터: 지금 규정(원문 PDF) · 관리자가 올린 PDF */
export const useRegulations = () => useQuery({ queryKey: adminKeys.regulations, queryFn: adminApi.regulations });
export const useRegulationUploads = () => useQuery({ queryKey: adminKeys.regulationUploads, queryFn: adminApi.regulationUploads });

/** 규정 PDF 를 올린 뒤: 올린 목록과 개요 개수 */
export function refreshRegulationUploads(): void {
  void queryClient.invalidateQueries({ queryKey: adminKeys.regulationUploads });
  void queryClient.invalidateQueries({ queryKey: adminKeys.overview });
}

/** 개요만 다시 받는다(목표 후보 작업 뒤) */
export const refreshOverview = (): void => void queryClient.invalidateQueries({ queryKey: adminKeys.overview });

/** 목표 후보 작업 뒤: 개요 개수와 직원 목록의 후보 상태 */
export function refreshGoals(): void {
  refreshOverview();
  void queryClient.invalidateQueries({ queryKey: adminKeys.goalEmployees });
}

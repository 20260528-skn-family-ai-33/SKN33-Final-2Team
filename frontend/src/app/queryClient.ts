/* 서버 데이터 캐시 (TanStack Query) — 화면에 들어올 때 새로 받고(staleTime 0), 창을 다시 볼 때 몰래 다시 받지는 않는다(5차와 같은 동작).
   로그아웃·시연 초기화 뒤에는 비운다(다른 계정의 부서원 목록·관리자 데이터가 잠깐이라도 보이지 않게) */
import { QueryClient } from '@tanstack/react-query';
import { onDataReset } from '@/shared/state/events';

export const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });

onDataReset(() => queryClient.clear());

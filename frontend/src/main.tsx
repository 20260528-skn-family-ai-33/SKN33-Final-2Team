/* 시작점: CSS(5차와 같은 순서) → 서버 데이터 캐시 → 라우터. 로그인 상태를 서버에서 읽은 뒤(boot) 화면을 그린다 */
import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';
import '@/styles/gp.css';
import '@/styles/gp-v2.css';
import '@/styles/gp-admin.css';
// 화면 테마 비교(비교 브랜치 전용 · skins/index.ts 설명): 테마 CSS 를 기본 CSS 뒤에 불러오고, 고른 테마를 바로 적용한다
import { SkinPicker } from '@/skins/SkinPicker';
import '@/features/draft/draftSync';
import { queryClient } from '@/app/queryClient';
import { router } from '@/app/routes';
import { boot } from '@/shared/state/session';

void boot();

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <SkinPicker />
    </QueryClientProvider>
  </StrictMode>,
);

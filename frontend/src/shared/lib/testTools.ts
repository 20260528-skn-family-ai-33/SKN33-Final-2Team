/* 시험용 조작(역량 테스트·사후 점검의 무작위 선택)을 보여 줄지.
   일반 사용 화면에는 숨기고, 개발 서버와 시연 도구를 켠 빌드(VITE_DEMO_TOOLS=on + 서버 demoMode)에서만 보인다(#74 · #224) */
import { useAi } from '@/shared/state/ai';
import { canUseDemo } from './demoAccess';

export const useTestTools = (): boolean => {
  const demoMode = useAi((s) => s.status.demoMode);
  return import.meta.env.DEV || canUseDemo(demoMode);
};

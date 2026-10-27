/* 화면 이동: 열린 가운데 창을 닫고, 등록된 이동 확인(작성 흐름의 '앞 단계를 바꿨어요')을 거친 뒤 옮긴다 (5차 GP.go · data-go) */
import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { closeSheet } from '@/shared/state/ui';

type Guard = (to: string, from: string) => boolean;
const guards = new Set<Guard>();

/** 이동 전에 물어볼 것을 등록한다. false 를 돌려주면 이동을 멈춘다(그 가드가 직접 확인 창을 띄움) */
export function addNavGuard(g: Guard): () => void {
  guards.add(g);
  return () => guards.delete(g);
}

export function useGo() {
  const navigate = useNavigate();
  return useCallback(
    (to: string, opts?: { force?: boolean; replace?: boolean }) => {
      closeSheet();
      const from = window.location.pathname;
      if (!opts?.force) for (const g of guards) if (g(to, from) === false) return;
      navigate(to, { replace: opts?.replace });
      window.scrollTo(0, 0);
    },
    [navigate],
  );
}

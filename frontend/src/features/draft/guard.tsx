/* 작성 단계 진입 조건 (5차 화면 guard) — 앞 단계를 마치지 않았으면 그 단계로 돌려보낸다 */
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import { pathToNewId } from '@/app/paths';
import { onBound } from '@/shared/state/bind';
import { updateWs, useWs, type WsState } from '@/shared/state/workspace';
import { useEffect } from 'react';
import { quizKey, type StepKey, blockedTo } from './model';

/** 새 로드맵 단계 화면: 마지막으로 연 단계를 기억한다(5차 newStep → lastNew, 서버 작성 문서에도 저장) */
export function useRememberStep(): void {
  const loc = useLocation();
  useEffect(() => {
    const id = pathToNewId(loc.pathname);
    if (id) updateWs((s) => void (s.lastNew = id));
  }, [loc.pathname]);
}

export function StepGate({ step, extra, children }: { step: StepKey; extra?: (s: WsState) => string | null; children: ReactNode }) {
  const to = useWs((s) => blockedTo(s, step) || (extra ? extra(s) : null));
  if (to) return <Navigate to={to} replace />;
  return <>{children}</>;
}

/* 입력 연결 뒤처리: 세부 사항을 바꾸면 확인 화면을 다시 거치게 하고, 문항 실패 표시는 열쇠가 바뀌면 지운다 */
onBound((s, path) => {
  if (!path.startsWith('draft.')) return;
  const d = s.draft;
  if (path.startsWith('draft.prefs.')) d.detailsOk = false;
  if (d.quizFail && d.quizFail.key !== quizKey(d)) d.quizFail = null;
});

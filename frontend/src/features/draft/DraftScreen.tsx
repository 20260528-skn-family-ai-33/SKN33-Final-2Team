/* 작성 단계 화면 감싸기: 진입 조건(앞 단계를 마치지 않았으면 돌려보냄) · 마지막 단계 기억 · 앞 단계 변경 확인 카드 */
import { useState, type ReactNode } from 'react';
import { paths } from '@/app/paths';
import { ws, type WsState } from '@/shared/state/workspace';
import { StepGate, useRememberStep } from './guard';
import { blockedTo, diagKey, docBusy, type StepKey } from './model';
import { confirmInFlight } from './review/confirmReview';
import { StaleStepGuard } from './stale';
import { needsStartMode, StartModeRedirect } from './startModeSheet';

function Remember() {
  useRememberStep();
  return null;
}

export function DraftScreen({ step, extra, remember = true, children }: { step?: StepKey; extra?: (s: WsState) => string | null; remember?: boolean; children: ReactNode }) {
  // 화면에 들어올 때 한 번만 본다. 주소 직접 입력·뒤로 가기처럼 useGo 를 거치지 않는 진입을 막는 곳이다
  const [mustAsk] = useState(() => needsStartMode(ws()) && !confirmInFlight());
  if (mustAsk) return <StartModeRedirect />;
  const body = <StaleStepGuard>{children}</StaleStepGuard>;
  return (
    <>
      {remember ? <Remember /> : null}
      {step ? (
        <StepGate step={step} extra={extra}>
          {body}
        </StepGate>
      ) : (
        body
      )}
    </>
  );
}

/* 하위 화면의 진입 조건 (5차 guard 그대로) */
export const editGate = (s: WsState) => (s.draft.diag && s.draft.diag.key === diagKey(s.draft) ? null : paths.newResult);
/* 3안 작성·선택 화면은 앞 단계 결과(handoff·gen)만 보고 들어오므로, 기획서를 다시 읽는 중이면 따로 1단계로 돌려보낸다(#81 리뷰) */
export const genGate = (s: WsState) => (docBusy(s) ? paths.newGoal : s.draft.handoff || s.draft.v2Assessment?.completed ? null : blockedTo(s, 'options') || paths.newResult);
export const optionsGate = (s: WsState) => (docBusy(s) ? paths.newGoal : s.draft.gen ? null : s.draft.handoff || s.draft.v2Assessment?.completed ? paths.newGen : blockedTo(s, 'options') || paths.newResult);

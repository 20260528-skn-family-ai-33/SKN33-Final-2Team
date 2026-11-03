/* 작성 단계 화면 감싸기: 진입 조건(앞 단계를 마치지 않았으면 돌려보냄) · 마지막 단계 기억 · 앞 단계 변경 확인 카드 */
import type { ReactNode } from 'react';
import { paths } from '@/app/paths';
import type { WsState } from '@/shared/state/workspace';
import { StepGate, useRememberStep } from './guard';
import { blockedTo, diagKey, type StepKey } from './model';
import { StaleStepGuard } from './stale';

function Remember() {
  useRememberStep();
  return null;
}

export function DraftScreen({ step, extra, remember = true, children }: { step?: StepKey; extra?: (s: WsState) => string | null; remember?: boolean; children: ReactNode }) {
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
export const genGate = (s: WsState) => (s.draft.handoff || s.draft.v2Assessment?.completed ? null : blockedTo(s, 'options') || paths.newResult);
export const optionsGate = (s: WsState) => (s.draft.gen ? null : s.draft.handoff ? paths.newGen : blockedTo(s, 'options') || paths.newResult);

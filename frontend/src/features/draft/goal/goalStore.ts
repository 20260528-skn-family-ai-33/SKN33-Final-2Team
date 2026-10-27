/* 목표 후보 (FR-05 · 2026-10-21 사용자 요구 1): 서버가 직원 데이터가 바뀔 때 미리 만들어 팀 DB 에 둔다.
   이 화면은 저장된 후보 3개를 보여 주기만 하고, '목표 후보 다시 만들기'를 누를 때만 다시 만든다.
   실패하면 이전 후보를 그대로 두고 안내한다(자동 재시도 없음). 30초 안에 다시 들어오면 읽은 것을 쓴다 (5차 gs·loadGoals) */
import { create } from 'zustand';
import { accountApi } from '@/api/endpoints/account';
import type { GoalSuggestions } from '@/api/types/account';
import { waitJob } from '@/api/jobs';
import { cause, type Cause } from '@/shared/state/ai';
import { onDataReset } from '@/shared/state/events';
import { me } from '@/shared/state/session';

export type GoalState = Partial<GoalSuggestions> & { status: string; loadError?: Cause; owner?: string; at?: number; candidates: GoalSuggestions['candidates'] };

interface S {
  gs: GoalState | null;
  /** 기획서 글자 꺼내기 실패: 서버에 기획서가 저장되지 않아 화면에만 안내를 둔다 */
  docErr: { name: string; cause: Cause } | null;
}

export const useGoalStore = create<S>(() => ({ gs: null, docErr: null }));
let tok = 0;

export async function loadGoals(): Promise<void> {
  const t = ++tok;
  const owner = me()?.id;
  let v: GoalState;
  try {
    v = { ...(await accountApi.goals()) };
  } catch (err) {
    v = { status: 'loadfail', loadError: cause(err), candidates: [] };
  }
  if (t !== tok) return;
  useGoalStore.setState({ gs: { ...v, owner, at: Date.now() } });
  if (v.status === 'running' && v.jobId) void waitGoals(v.jobId);
}

async function waitGoals(jobId: string): Promise<void> {
  const t = tok;
  try {
    await waitJob(jobId);
  } catch {
    /* 실패 상태는 다시 읽어서 보여 준다 */
  }
  if (t === tok) void loadGoals();
}

export function loadGoalsIfOld(): void {
  const gs = useGoalStore.getState().gs;
  if (!gs || gs.owner !== me()?.id || Date.now() - (gs.at || 0) > 30000) void loadGoals();
}

export async function regenGoals(): Promise<void> {
  const gs = useGoalStore.getState().gs;
  if (gs && gs.status === 'running') return;
  useGoalStore.setState({ gs: { candidates: [], ...gs, status: 'running', error: null } });
  try {
    const r = await accountApi.goalsRegenerate();
    if (r && r.jobId) {
      ++tok;
      void waitGoals(r.jobId);
    } else void loadGoals();
  } catch (err) {
    const cur = useGoalStore.getState().gs;
    useGoalStore.setState({ gs: { candidates: [], ...cur, status: 'failed', error: cause(err) } });
  }
}

onDataReset(() => {
  ++tok;
  useGoalStore.setState({ gs: null, docErr: null });
});

/** 내 정보가 바뀌면 화면에 둔 후보를 비운다(서버가 새로 만들므로 다음 방문 때 다시 읽음) */
export function dropGoals(): void {
  ++tok;
  useGoalStore.setState({ gs: null });
}

/* 정보 저장 뒤 준비한 후보를 읽는다. 진입 때 후보가 없는 신규 계정만 처음 준비한다.
   서버는 같은 입력의 캐시·진행 작업을 재사용하며 실패 후 자동 재시도하지 않는다. */
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

export async function loadGoals(ensure = true): Promise<void> {
  const t = ++tok;
  const owner = me()?.id;
  let v: GoalState;
  try {
    v = { ...(await (ensure ? accountApi.goalsEnsure() : accountApi.goals())) };
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
  if (t === tok) void loadGoals(false);
}

export function loadGoalsIfOld(): void {
  // 저장된 후보를 읽고 신규 계정의 누락만 보완한다. 기존 후보를 자동으로 다시 만들지 않는다.
  void loadGoals();
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

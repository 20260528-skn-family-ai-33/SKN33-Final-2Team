import { beforeEach, expect, it, vi } from 'vitest';
import { accountApi } from '@/api/endpoints/account';
import { waitJob } from '@/api/jobs';
import type { GoalSuggestions } from '@/api/types/account';
import { loadGoals, loadGoalsIfOld, useGoalStore } from './goalStore';

vi.mock('@/shared/state/session', () => ({ me: () => ({ id:'fixture' }) }));
vi.mock('@/api/jobs', () => ({ waitJob:vi.fn() }));

const stored: GoalSuggestions = { status:'ready', source:'ollama', note:'', used:[], trigger:'login',
  jobId:null, error:null, stale:false, updatedAt:'', candidates:[], who:'' };

beforeEach(() => {
  vi.restoreAllMocks();
  useGoalStore.setState({ gs:null });
});

it('checks each entry so a direct database update is detected even inside the old thirty-second cache', async () => {
  const ensure = vi.spyOn(accountApi, 'goalsEnsure').mockResolvedValue(stored);
  await loadGoals();
  loadGoalsIfOld();
  await vi.waitFor(() => expect(ensure).toHaveBeenCalledTimes(2));
  expect(useGoalStore.getState().gs?.owner).toBe('fixture');
});

it('reads the result after a failed job without automatically starting another generation', async () => {
  const ensure = vi.spyOn(accountApi, 'goalsEnsure').mockResolvedValue({ ...stored, status:'running', jobId:'job' });
  vi.mocked(waitJob).mockRejectedValue(new Error('expected test failure'));
  const get = vi.spyOn(accountApi, 'goals').mockResolvedValue({ ...stored, status:'failed' });
  await loadGoals();
  await vi.waitFor(() => expect(useGoalStore.getState().gs?.status).toBe('failed'));
  expect(ensure).toHaveBeenCalledTimes(1);
  expect(get).toHaveBeenCalledTimes(1);
});

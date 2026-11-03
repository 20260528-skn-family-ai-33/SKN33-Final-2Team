import { beforeEach, expect, it, vi } from 'vitest';
import { accountApi } from '@/api/endpoints/account';
import { waitJob } from '@/api/jobs';
import type { GoalSuggestions } from '@/api/types/account';
import { loadGoals, loadGoalsIfOld, regenGoals, useGoalStore } from './goalStore';

vi.mock('@/shared/state/session', () => ({ me: () => ({ id:'fixture' }) }));
vi.mock('@/api/jobs', () => ({ waitJob:vi.fn() }));

const stored: GoalSuggestions = { status:'ready', source:'ollama', note:'', used:[], trigger:'login',
  jobId:null, error:null, stale:false, updatedAt:'', candidates:[], who:'' };

beforeEach(() => {
  vi.restoreAllMocks();
  useGoalStore.setState({ gs:null });
});

it('reads stored candidates on each entry through the endpoint that only prepares missing accounts', async () => {
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

it('keeps existing candidates while generating and replaces them only after success', async () => {
  const previous = [{ goal:'기존 목표', why:'기존 근거', basis:[] }];
  const next = ['새 목표 1', '새 목표 2', '새 목표 3'].map(goal => ({ goal, why:'새 근거', basis:[] }));
  useGoalStore.setState({ gs:{ ...stored, candidates:previous } });
  vi.spyOn(accountApi, 'goalsRegenerate').mockResolvedValue({ ...stored, status:'running', jobId:'replacement' });
  let complete!: () => void;
  vi.mocked(waitJob).mockImplementation(() => new Promise(resolve => { complete = () => resolve({} as Awaited<ReturnType<typeof waitJob>>); }));
  vi.spyOn(accountApi, 'goals').mockResolvedValue({ ...stored, candidates:next });
  await regenGoals();
  expect(useGoalStore.getState().gs?.status).toBe('running');
  expect(useGoalStore.getState().gs?.candidates).toEqual(previous);
  complete();
  await vi.waitFor(() => expect(useGoalStore.getState().gs?.candidates).toEqual(next));
});

it('keeps existing candidates when regeneration request fails', async () => {
  const previous = [{ goal:'기존 목표', why:'기존 근거', basis:[] }];
  useGoalStore.setState({ gs:{ ...stored, candidates:previous } });
  vi.spyOn(accountApi, 'goalsRegenerate').mockRejectedValue(new Error('expected failure'));
  await regenGoals();
  expect(useGoalStore.getState().gs?.status).toBe('failed');
  expect(useGoalStore.getState().gs?.candidates).toEqual(previous);
});

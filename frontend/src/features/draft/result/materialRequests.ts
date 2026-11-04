import { waitJob } from '@/api/jobs';
import { flush } from '../draftSync';
import type { Choices, DurationEstimate } from './skillOrder';

export type Resource = { id: string; title: string; provider?: string; image?: string; url?: string; cost: number | null; why: string; knowledge: string; aiRecommended: boolean };
type Skill = { name: string; courses: Resource[]; books: Resource[]; selectedCourse: string | null; selectedBooks: string[] };
export type Result = { courseId?: string | null; skillDetails?: { name: string; application: string }[]; generationId: string; recommendations: { id: string; skills: Skill[]; retrieval?: { matches?: { skill: string; resourceId: string }[] } } | null; choices: Choices; skillOrder?: string[]; durationEstimates?: Record<string, DurationEstimate> };

export function recommendationUrl(id: string, course?: string | null, suffix = '') {
  return `/api/v2/drafts/${id}/recommendations${suffix}${course ? `?course=${encodeURIComponent(course)}` : ''}`;
}

export async function requestMaterials(path: string, init?: RequestInit): Promise<Result> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...init?.headers } });
  let body = await response.json().catch(() => null);
  if (response.status === 202 && body?.jobId) body = await waitJob<Result>(body.jobId);
  if (!response.ok) throw new Error(body?.error?.message ?? '추천 자료를 읽지 못했어요.');
  return body;
}

const recommendationFlights = new Map<string, Promise<Result>>();

export function loadRecommendations(id: string, generation: string | undefined, course: string | null | undefined, version: string): Promise<Result> {
  // Prefetch and screen entry share a recommendation even when the displayed weekly hours change.
  const key = JSON.stringify([id, generation, course || null, version]);
  const pending = recommendationFlights.get(key);
  if (pending) return pending;
  const path = recommendationUrl(id, course);
  // Persist genCur before reading the materials of a newly selected proposal version.
  const work = flush().then(() => requestMaterials(path)).then(body =>
    body.recommendations ? body : requestMaterials(path, { method: 'POST', headers: { Prefer: 'respond-async' } }));
  recommendationFlights.set(key, work);
  void work.finally(() => { if (recommendationFlights.get(key) === work) recommendationFlights.delete(key); }).catch(() => {});
  return work;
}

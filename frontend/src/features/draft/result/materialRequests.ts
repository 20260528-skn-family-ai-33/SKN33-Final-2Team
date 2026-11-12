import { browserHeaders } from '@/shared/lib/browserOptions';
import { waitJob } from '@/api/jobs';
import type { BookDiagnostic, CourseDiagnostic, MaterialResource } from '@/api/types/draft';
import { flush } from '../draftSync';
import type { Choices, DurationEstimate } from './skillOrder';

export type Resource = Pick<MaterialResource, 'id' | 'title' | 'unverifiedTargetTopics' | 'difficulty' | 'difficultyEstimated' | 'difficultyBasis' | 'difficultySource'> & { provider?: string; image?: string; url?: string; cost: number | null; hours?: number | null; timeStatus?: string; estimated?: string[]; why: string; knowledge: string; aiRecommended: boolean };
export type ModelCandidateCounts = { candidates: number; recommended: number };
type Skill = {
  modelBookCounts?: ModelCandidateCounts;
  modelCourseCandidates?: { id: string; title: string; provider?: string | null; recommended: boolean }[];
  name: string; courses: Resource[]; books: Resource[]; selectedCourse: string | null; selectedBooks: string[];
  courseDiagnostic?: CourseDiagnostic;
  bookDiagnostic?: BookDiagnostic;
};
export type Result = { preparingJobId?: string | null; courseId?: string | null; skillDetails?: { name: string; application: string }[]; generationId: string; recommendations: { id: string; skills: Skill[]; outdated?: boolean; retrieval?: { matches?: { skill: string; resourceId: string }[] } } | null; choices: Choices; skillOrder?: string[]; durationEstimates?: Record<string, DurationEstimate> };

export function recommendationUrl(id: string, course?: string | null, suffix = '') {
  return `/api/v2/drafts/${id}/recommendations${suffix}${course ? `?course=${encodeURIComponent(course)}` : ''}`;
}

export async function requestMaterials(path: string, init?: RequestInit): Promise<Result> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', mode: 'same-origin', headers: { ...browserHeaders(), 'Content-Type': 'application/json', ...init?.headers } });
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
  const work = flush().then(async () => {
    const deadline = Date.now() + 10000;
    let body = await requestMaterials(path);
    while (!body?.recommendations && body?.preparingJobId === '') {
      if (Date.now() >= deadline) throw new Error('자료 준비가 지연되고 있어요. 잠시 뒤 다시 시도해 주세요.');
      await new Promise(resolve => setTimeout(resolve, 150));
      body = await requestMaterials(path);
    }
    if (body?.recommendations) return body;
    const completed = body?.preparingJobId
      ? await waitJob<Result>(body.preparingJobId)
      : await requestMaterials(path, { method: 'POST', headers: { Prefer: 'respond-async' } });
    if (completed?.recommendations) return completed;

    const saved = await requestMaterials(path);
    if (saved?.recommendations) return saved;
    throw new Error('현재 제안의 자료를 준비하지 못했어요. 다시 시도해 주세요.');
  });
  recommendationFlights.set(key, work);
  void work.finally(() => { if (recommendationFlights.get(key) === work) recommendationFlights.delete(key); }).catch(() => {});
  return work;
}

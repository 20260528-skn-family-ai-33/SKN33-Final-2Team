/* 산출물 과제 고르기 화면의 처음 준비(#288): 저장된 제안·자료 읽기 → 없으면 제안·역량 요약 만들기.
   화면이 기존 내용을 먼저 보여 주는 읽기와 준비 흐름이 같은 GET 요청을 함께 쓴다(진입마다 각 1회) */
import { reviewRequest as request } from './reviewRequest';
import type { ReviewMaterials } from './ReviewSkillBlocks';
import type { ReviewProposal } from './reviewPlan';
import { reviewScope } from './reviewScope';
import { reviewTasks } from './reviewTasks';
import { ws } from '@/shared/state/workspace';
import { flush } from '../draftSync';

export type ProposalResponse = { proposal: ReviewProposal | null; versions: ReviewProposal[] };
export type ExistingReview = { body: ProposalResponse; resources: ReviewMaterials };
export type ReviewBundle = ExistingReview & { summaries?: Record<string, string[]> };

export function reviewPath(id: string, route: string, course: string, extra = '') {
  return `/api/v2/drafts/${id}/${route}?course=${encodeURIComponent(course)}${extra}`;
}

/** 저장된 제안·자료를 읽는다. fresh 는 진행 중인 읽기에는 합류하되 남겨 둔 결과는 쓰지 않는다(준비 흐름은 최신 저장 상태로 판단) */
export function readExisting(id: string, course: string, scope: string, fresh = false): Promise<ExistingReview> {
  return reviewTasks.run(scope, 'existing', async () => {
    await flush();
    if (reviewScope(ws()) !== scope) throw new Error('검토 입력이 변경됐어요.');
    const [body, resources] = await Promise.all([
      request<ProposalResponse>(reviewPath(id, 'activities', course)),
      request<ReviewMaterials>(reviewPath(id, 'recommendations', course)),
    ]);
    return { body, resources };
  }, fresh);
}

export async function initializeReview(id: string, course: string, scope: string): Promise<ReviewBundle> {
  // Rejoining a scope while its explicit regeneration runs must await that version.
  await reviewTasks.waitForChanges(scope);
  return reviewTasks.run(scope, 'initial', async () => {
    const { body: existing, resources } = await readExisting(id, course, scope, true);
    let body = existing;
    if (!body.proposal) {
      if (reviewScope(ws()) !== scope) throw new Error('검토 입력이 변경됐어요.');
      body = await request<ProposalResponse>(reviewPath(id, 'activities', course), {method: 'POST'});
    }
    if (!body.proposal) throw new Error('산출물 제안을 확인하지 못했어요. 다시 시도해 주세요.');
    let summaries: Record<string, string[]> | undefined;
    if (!body.proposal.skillSummaries) {
      // Do not start additional model work for a scope the user has left.
      if (reviewScope(ws()) !== scope) throw new Error('검토 입력이 변경됐어요.');
      summaries = (await request<{summaries: Record<string, string[]>}>(reviewPath(id, 'learning-outcomes', course), {method: 'POST'})).summaries;
    }
    return {body, resources, summaries};
  });
}

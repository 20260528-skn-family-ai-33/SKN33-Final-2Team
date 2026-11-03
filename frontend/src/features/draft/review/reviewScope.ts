import type { WsState } from '@/shared/state/workspace';
import { inputSignature } from '../invalidation';

/** A review result belongs to one owner, draft, input, course and material selection. */
export function reviewScope(s: Pick<WsState, 'owner' | 'draftId' | 'draft'>): string {
  const a = s.draft.v2Assessment;
  return JSON.stringify([s.owner, s.draftId, inputSignature(s.draft), s.draft.chosen, a?.generationId, a?.materialsKey]);
}

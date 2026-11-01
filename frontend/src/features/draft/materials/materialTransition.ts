import { draftsApi } from '@/api/endpoints/drafts';
import { paths } from '@/app/paths';
import { ws } from '@/shared/state/workspace';
import { flush, takeDraft } from '../draftSync';
import { inputSignature } from '../invalidation';

/** 이전 자동 저장이 끝난 뒤 자료를 저장하고, 같은 초안의 자료 저장만 확인한 뒤 검토 화면으로 이동한다. 검토 결과 생성은 7단계에서 진행한다. */
export async function completeMaterialSelection(save: () => Promise<boolean>, go: (path: string) => void) {
  await flush();
  const before=ws(); const id=before.draftId; const chosen=before.draft.chosen; const signature=inputSignature(before.draft);
  if (!id || !chosen) throw new Error('선택한 계획을 확인해 주세요.');
  if (!await save()) return false;
  const result=await draftsApi.get(id);
  if (ws().draftId!==id || ws().draft.chosen!==chosen || inputSignature(ws().draft)!==signature ||
      result.draft?.chosen!==chosen || !result.draft.v2Assessment?.materialsReady) {
    throw new Error('저장한 자료와 검토 계획을 확인하지 못했어요. 다시 시도해 주세요.');
  }
  takeDraft(result);
  go(paths.newReview);
  return true;
}

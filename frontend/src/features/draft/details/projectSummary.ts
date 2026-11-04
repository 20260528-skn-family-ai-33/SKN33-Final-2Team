import { draftsApi } from '@/api/endpoints/drafts';
import { ws } from '@/shared/state/workspace';
import { flush, takeDraft } from '../draftSync';
import { inputSignature } from '../invalidation';

/** 편집 중에는 원본을 유지하고 저장 성공 시에만 서버의 무효화 결과를 적용한다. */
export async function saveProjectSummary(value: string): Promise<boolean> {
  const before = ws();
  if (!before.draftId || before.draft.doc?.status !== 'ok') throw new Error('요약 준비가 끝난 뒤 수정해 주세요.');
  if (value.length > 1500) throw new Error('요약은 1,500자 이내로 입력해 주세요.');
  if (!value.trim()) throw new Error('프로젝트 요약을 입력해 주세요.');
  if (value === before.draft.doc.summary) return false;
  const owner = before.owner, id = before.draftId, signature = inputSignature(before.draft);
  const current = () => ws().owner === owner && ws().draftId === id && inputSignature(ws().draft) === signature;
  await flush();
  if (!current()) throw new Error('입력 내용이 바뀌었어요. 현재 요약을 다시 확인해 주세요.');
  const result = await draftsApi.patch(id, { docSummary: value });
  if (!current()) throw new Error('입력 내용이 바뀌어 이전 저장 응답을 적용하지 않았어요. 현재 초안을 다시 확인해 주세요.');
  takeDraft(result);
  return true;
}

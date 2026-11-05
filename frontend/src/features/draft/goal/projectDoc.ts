/* 1단계 기획서 올리기·빼기와 완료 안내 문구 (GoalStep 에서 분리 · #81 리뷰)
   파일을 올리는 동안에는 서버가 아직 기획서를 몰라 저장·다시 읽기 응답이 화면의 '읽는 중'을 지울 수 있다.
   그래서 올리는 중인 요청 번호를 작업 상태(docUpload)에 두고, 그동안은 다음 단계 진입·빼기·다른 파일 올리기를 막는다.
   응답은 지금 올리는 요청(같은 계정·같은 번호)일 때만 반영한다 */
import { draftsApi } from '@/api/endpoints/drafts';
import type { DocState } from '@/api/types/draft';
import { cause } from '@/shared/state/ai';
import { setAt } from '@/shared/state/bind';
import { updateWs, ws } from '@/shared/state/workspace';
import { DraftSaveError, draftCall, ensureDraft, takeDraft } from '../draftSync';
import { useGoalStore } from './goalStore';

let seq = 0;

/** 기획서 파일을 올린다. 이미 올리는 중이면 시작하지 않고 false(끝난 뒤에 바꿀 수 있음) */
export async function uploadProject(file: File): Promise<boolean> {
  if (ws().docUpload) return false;
  const owner = ws().owner;
  const mine = ++seq;
  setAt('draft.project', { name: file.name, size: file.size });
  updateWs((s) => {
    s.draft.doc = { name: file.name, status: 'reading', step: 'extract' };
    s.docUpload = mine;
  });
  useGoalStore.setState({ docErr: null });
  const current = () => ws().owner === owner && ws().docUpload === mine;
  try {
    const id = await ensureDraft();
    const r = await draftsApi.projectFile(id, file);
    if (current()) takeDraft(r, true);
  } catch (err) {
    if (current()) {
      updateWs((s) => {
        s.draft.project = null;
        s.draft.doc = null;
      });
      useGoalStore.setState({ docErr: { name: file.name, cause: cause(err instanceof DraftSaveError ? err.original : err) } });
    }
  } finally {
    if (current()) updateWs((s) => void (s.docUpload = null));
  }
  return true;
}

/** 기획서를 뺀다. 올리는 중이면 하지 않는다(늦게 끝난 업로드가 뺀 뒤의 상태를 덮지 않게) */
export async function clearProject(): Promise<void> {
  if (ws().docUpload) return;
  useGoalStore.setState({ docErr: null });
  updateWs((s) => {
    s.draft.project = null;
    s.draft.doc = null;
  });
  if (ws().draftId) await draftCall('기획서를 빼지 못했어요', (id) => draftsApi.projectClear(id), { soft: true });
  setAt('draft.project', null);
}

/** 요약이 끝났을 때 상자와 알림 문구. 둘 다 같은 조건(요약 글이 있는지)으로 고른다 */
export function docDoneText(doc: Pick<DocState, 'summary'> | null | undefined): { title: string; body: string; toast: string } {
  return doc?.summary?.trim()
    ? { title: '기획서 요약 완료', body: '요약은 다음 단계(세부 사항)에서 확인하고 고칠 수 있어요.', toast: '기획서 요약을 마쳤어요. 다음 단계로 넘어갈 수 있어요' }
    : { title: '기획서 읽기 완료', body: '요약할 내용을 찾지 못했어요. 목표만으로 진행해요.', toast: '기획서에서 요약할 내용을 찾지 못했어요. 목표만으로 진행해요' };
}

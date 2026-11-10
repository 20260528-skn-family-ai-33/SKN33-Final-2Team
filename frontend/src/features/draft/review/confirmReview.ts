import { draftsApi } from '@/api/endpoints/drafts';
import { ensurePostQuiz } from '@/features/assessment/postActions';
import { paths } from '@/app/paths';
import { failToast } from '@/shared/lib/fail';
import { toast } from '@/shared/state/ui';
import { recs, updateWs, ws } from '@/shared/state/workspace';
import { DraftSaveError, flush, reloadWorkspace } from '../draftSync';
import { reviewScope } from './reviewScope';

type Go = (path: string, options?: {force?: boolean}) => void;
const flights = new Map<string, Promise<boolean>>();
/** 확정 도중에는 작업 공간을 다시 읽어 작성 문서가 잠깐 비므로, 작성 탭 진입 확인을 띄우지 않게 알려 준다 */
export const confirmInFlight = (): boolean => flights.size > 0;
/** Share a complete submit sequence, not only its final HTTP request. */
export function confirmReview(go: Go, save?: () => Promise<boolean>): Promise<boolean> {
  const initial = ws(), scope = reviewScope(initial), id = initial.draftId, owner = initial.owner;
  const pending = flights.get(scope);
  if (pending) return pending;
  const current = () => ws().owner === owner && reviewScope(ws()) === scope && ws().pendingFlow !== 'materials';
  const work = Promise.resolve().then(async () => {
    try {
      if (!id || !owner) return false;
      if(ws().pendingFlow==='materials'){failToast(new Error('자료 선택을 먼저 저장해 주세요.'),'확정할 수 없어요');return false;}
      await flush();
      if (!current()) return false;
      if (save && !await save()) return false;
      if (!current()) return false;
      await flush();
      if (!current()) return false;
      // 작성 탭에 들어올 때 고른 방식을 쓴다. 고른 뒤 기존 로드맵이 끝났을 수 있어 실제로 보관할 때만 알린다
      const startMode = ws().draft.startMode || undefined;
      const archiving = startMode === 'archive' && recs(ws(), 'active').length > 0;
      const result = await draftsApi.confirm(id, startMode);
      // The server may already have confirmed the old draft. Never apply its
      // late response to a different input or account, or retry automatically.
      if (!current()) return false;
      if (!await reloadWorkspace(current)) return false;
      if (ws().owner !== owner) return false;
      updateWs(state => { state.lastNew = null; });
      if (!ws().plans?.[result.planId]?.post?.quizSurvey) void ensurePostQuiz(result.planId).catch(() => {});
      go(paths.confirmed(result.planId), {force:true});
      if (archiving) toast('진행 중이던 로드맵을 보관했어요 · 내 로드맵에서 다시 진행할 수 있어요');
      return true;
    } catch (error) {
      if (current() && !(error instanceof DraftSaveError)) failToast(error, '로드맵을 확정하지 못했어요');
      return false;
    }
  }).finally(() => { if (flights.get(scope) === work) flights.delete(scope); });
  flights.set(scope, work);
  return work;
}

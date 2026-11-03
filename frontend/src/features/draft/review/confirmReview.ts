import { draftsApi } from '@/api/endpoints/drafts';
import { paths } from '@/app/paths';
import { failToast } from '@/shared/lib/fail';
import { updateWs, ws } from '@/shared/state/workspace';
import { DraftSaveError, flush, reloadWorkspace } from '../draftSync';
import { reviewScope } from './reviewScope';

type Go = (path: string, options?: {force?: boolean}) => void;
const flights = new Map<string, Promise<boolean>>();
/** Share a complete submit sequence, not only its final HTTP request. */
export function confirmReview(go: Go, save?: () => Promise<boolean>): Promise<boolean> {
  const initial = ws(), scope = reviewScope(initial), id = initial.draftId, owner = initial.owner;
  const pending = flights.get(scope);
  if (pending) return pending;
  const current = () => ws().owner === owner && reviewScope(ws()) === scope;
  const work = Promise.resolve().then(async () => {
    try {
      if (!id || !owner) return false;
      await flush();
      if (!current()) return false;
      if (save && !await save()) return false;
      if (!current()) return false;
      await flush();
      if (!current()) return false;
      const result = await draftsApi.confirm(id);
      // The server may already have confirmed the old draft. Never apply its
      // late response to a different input or account, or retry automatically.
      if (!current()) return false;
      if (!await reloadWorkspace(current)) return false;
      if (ws().owner !== owner) return false;
      updateWs(state => { state.lastNew = null; });
      go(paths.confirmed(result.planId), {force:true});
      return true;
    } catch (error) {
      if (current() && !(error instanceof DraftSaveError)) failToast(error, '로드맵을 확정하지 못했어요');
      return false;
    }
  }).finally(() => { if (flights.get(scope) === work) flights.delete(scope); });
  flights.set(scope, work);
  return work;
}

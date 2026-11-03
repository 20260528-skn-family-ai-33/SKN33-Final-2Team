import { draftsApi } from '@/api/endpoints/drafts';
import { ws } from '@/shared/state/workspace';
import { flush, takeDraft } from '../draftSync';
import { inputSignature } from '../invalidation';
import type { Answers } from './assessment/flow';
import { request, SurveyRequestError } from './surveyRequest';
export type SurveyScope = { owner: string | null; id: string; inputKey: string; generationId: string };
export function surveyScopeCurrent(scope: SurveyScope): boolean {
  const state=ws();
  return state.owner===scope.owner && state.draftId===scope.id && inputSignature(state.draft)===scope.inputKey && state.draft.v2Assessment?.generationId===scope.generationId;
}
export async function saveSurvey(scope: SurveyScope, answers: Answers, complete: boolean) {
  const check=()=>{if(!surveyScopeCurrent(scope))throw new SurveyRequestError('점검 입력이 변경됐어요. 현재 입력을 확인해 주세요.','SURVEY_INPUT_CHANGED');};
  check(); await flush(); check();
  const saved=await request(`/api/v2/drafts/${scope.id}/survey/answers`,{method:'PUT',body:JSON.stringify({generationId:scope.generationId,answers,complete})});
  check();
  if(!saved || saved.generationId!==scope.generationId || (complete && !saved.completed))throw new Error('응답 저장을 확인하지 못했어요.');
  const refreshed=await draftsApi.get(scope.id); check();
  if(refreshed.draftId!==scope.id || !refreshed.draft || inputSignature(refreshed.draft)!==scope.inputKey || refreshed.draft.v2Assessment?.generationId!==scope.generationId || (complete && !refreshed.draft.v2Assessment.completed))throw new Error('현재 점검의 저장 상태를 확인하지 못했어요.');
  takeDraft(refreshed); return saved;
}

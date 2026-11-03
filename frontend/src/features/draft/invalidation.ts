import { sortKeys } from '@/shared/lib/format';
import type { WsState } from '@/shared/state/workspace';

/** 앞단계 입력이 바뀌면 작성 중인 하위 결과만 즉시 버린다. 확정 로드맵은 건드리지 않는다. */
export function invalidateDraft(s: WsState, from: 'inputs' | 'answers' | 'options' | 'materials' = 'inputs') {
  const d = s.draft;
  s.pendingFlow = from;
  if (from === 'options' || from === 'materials') {
    if (d.v2Assessment) d.v2Assessment = { ...d.v2Assessment, materialsReady: false, activitiesReady: false, materialsKey: undefined };
    s.draftPlan = null; s.regenReq = null; return;
  }
  if (from === 'inputs') {
    Object.assign(d, { detailsOk: false, quiz: null, answers: {}, deepMcq: {}, deepEssay: {}, quizFail: null, quizRun: null });
    delete d.v2Assessment;
  } else if (d.v2Assessment) d.v2Assessment = { generationId: d.v2Assessment.generationId, completed: false, materialsReady: false, activitiesReady: false };
  Object.assign(d, { diag: null, diagFail: null, diagRun: null, startStage: null, fix: null, edit: null, handoff: null, gen: null, chosen: null, genRun: null, genPrefs: null });
  s.draftPlan = null; s.regenReq = null;
}

export function inputSignature(d: WsState['draft']) {
  return JSON.stringify(sortKeys([d.goal, d.project, d.prefs, d.doc?.status === 'ok' ? d.doc.summary : null, d.selectedSkills || null]));
}

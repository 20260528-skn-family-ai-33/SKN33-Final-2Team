import { sameJ } from '@/shared/lib/format';
import { useEffect, useRef, useState } from 'react';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { updateWs, useWs } from '@/shared/state/workspace';
import { Page } from '@/shared/ui/parts';
import { draftsApi } from '@/api/endpoints/drafts';
import { inputSignature, invalidateDraft } from '../invalidation';
import { answerMemoryKey, pendingAnswers, rememberAnswers } from './assessment/answerMemory';
import { ensureDraft, flush, takeDraft } from '../draftSync';
import { Stepper } from '../Stepper';
import { SurveyFlow, type SurveyFlowHandle } from './assessment/SurveyFlow';
import type { Answers, Survey } from './assessment/flow';

type Stored = Survey & { answers: Answers; completed: boolean };
const flights = new Map<string, Promise<Stored>>();
class SurveyRequestError extends Error {
  constructor(message: string, readonly code: string) { super(message); }
}
async function request(path: string, init?: RequestInit): Promise<Stored | null> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...init?.headers } });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new SurveyRequestError(body?.error?.message ?? '문항 요청을 처리하지 못했어요.', body?.error?.code ?? 'REQUEST_FAILED');
  if (!body || typeof body !== 'object') throw new SurveyRequestError('서버 응답을 확인하지 못했어요. 다시 시도해 주세요.', 'EMPTY_RESPONSE');
  return body.survey ?? null;
}
function load(owner: string): Promise<Stored> {
  const pending = flights.get(owner);
  if (pending) return pending;
  const work = (async () => {
    const id = await ensureDraft();
    const path = `/api/v2/drafts/${id}/survey`;
    const existing = await request(path);
    const result = existing ?? await request(path, { method: 'POST' });
    if (!result) throw new Error('생성된 문항이 없어요.');
    return result;
  })();
  flights.set(owner, work);
  void work.finally(() => { if (flights.get(owner) === work) flights.delete(owner); }).catch(() => {});
  return work;
}
export function QuizStep() {
  const surveyRef = useRef<SurveyFlowHandle>(null);
  const owner = useWs(s => s.owner);
  const id = useWs(s => s.draftId);
  const inputKey = useWs(s => JSON.stringify([inputSignature(s.draft), s.draft.doc?.status]));
  const go = useGo();
  const [loaded, setLoaded] = useState<{ key: string; survey: Stored | null; error: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const requestKey = JSON.stringify([owner, id, inputKey, attempt]);
  const survey = loaded && loaded.key === requestKey ? loaded.survey : null;
  const error = loaded && loaded.key === requestKey ? loaded.error : '';
  const memoryKey = survey ? answerMemoryKey(owner, id, survey.generationId, inputKey) : '';
  const pending = pendingAnswers(memoryKey);
  useEffect(() => {
    let active = true;
    void load(`${owner}:${inputKey}`).then(result => { if (active) {
      setLoaded({ key: requestKey, survey: result, error: '' });
      const pending = pendingAnswers(answerMemoryKey(owner, id, result.generationId, inputKey));
      updateWs(s => {
        const dirty = pending && !sameJ(pending.answers, result.answers);
        const previous = s.draft.v2Assessment;
        s.draft.v2Assessment = { generationId: result.generationId, completed: result.completed && !dirty,
          materialsReady: previous?.generationId === result.generationId && !dirty ? previous.materialsReady : false,
          activitiesReady: previous?.generationId === result.generationId && !dirty ? previous.activitiesReady : false };
        if (dirty) invalidateDraft(s, 'answers');
      });
    } })
      .catch(e => { if (active) setLoaded({ key: requestKey, survey: null, error: e instanceof Error ? e.message : '문항을 불러오지 못했어요.' }); });
    return () => { active = false; };
  }, [owner, id, inputKey, requestKey]);
  return <><Stepper cur="quiz" busy={saving} /><Page title={<span style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>사전 점검
    <button type="button" className="btn line" style={{ fontSize: 12, padding: '5px 10px', minHeight: 0 }} disabled={!survey} onClick={() => surveyRef.current?.randomize()}>test용으로 삭제예정 · 무작위 선택</button>
  </span>}
    lead="프로젝트 요약과 키우고 싶은 역량, 개인 프로필을 참고해 선정 스킬의 역량을 확인해요. 설문을 모두 마치면 퀴즈로 이어집니다.">
    {error ? <div className="card"><p role="alert">{error}</p><div className="actions">
      <button className="btn line" onClick={() => go(paths.newDetailsCheck)}>입력 내용 확인</button>
      <button className="btn pri" onClick={() => setAttempt(n => n + 1)}>다시 시도하기</button></div></div>
      : survey ? <SurveyFlow ref={surveyRef} key={survey.generationId} survey={survey} initialAnswers={pending?.answers || survey.answers} initialPhase={pending?.phase} initialCompleted={survey.completed}
        onProgress={(answers, phase) => {
          rememberAnswers(memoryKey, answers, phase);
          if (!sameJ(answers, survey.answers)) updateWs(s => invalidateDraft(s, 'answers'));
        }} onContinue={() => go(paths.newResult)}
        onSave={async (answers, complete) => {
          if (!id) throw new Error('작성 중인 로드맵을 확인해 주세요.');
          setSaving(true);
          try {
            await flush();
            const saved = await request(`/api/v2/drafts/${id}/survey/answers`, { method: 'PUT', body: JSON.stringify({ generationId: survey.generationId, answers, complete }) });
            if (!saved || saved.generationId !== survey.generationId || (complete && !saved.completed)) throw new Error('응답 저장을 확인하지 못했어요.');
            setLoaded({ key: requestKey, survey: saved, error: '' });
            const refreshed = await draftsApi.get(id);
            if (complete && !refreshed.draft?.v2Assessment?.completed) throw new Error('점검 완료 상태를 확인하지 못했어요.');
            takeDraft(refreshed);
          } catch (e) {
            if (e instanceof SurveyRequestError && e.code === 'SURVEY_INPUT_CHANGED') {
              setAttempt(n => n + 1);
            }
            throw e;
          } finally { setSaving(false); }
        }} /> : <div className="loading" role="status" aria-live="polite"><span className="sp" aria-hidden="true" /><span>프로젝트와 희망 역량에 맞춰 스킬·문항을 준비하고 있어요.</span></div>}
  </Page></>;
}

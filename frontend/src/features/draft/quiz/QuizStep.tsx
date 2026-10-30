import { useEffect, useState } from 'react';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { useWs } from '@/shared/state/workspace';
import { Page } from '@/shared/ui/parts';
import { ensureDraft, pullDraft } from '../draftSync';
import { Stepper } from '../Stepper';
import { SurveyFlow } from './assessment/SurveyFlow';
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
  const owner = useWs(s => s.owner);
  const id = useWs(s => s.draftId);
  const inputKey = useWs(s => JSON.stringify([s.draft.goal, s.draft.prefs, s.draft.project, s.draft.doc?.summary, s.draft.doc?.status]));
  const go = useGo();
  const [loaded, setLoaded] = useState<{ key: string; survey: Stored | null; error: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const requestKey = JSON.stringify([owner, id, inputKey, attempt]);
  const survey = loaded && loaded.key === requestKey ? loaded.survey : null;
  const error = loaded && loaded.key === requestKey ? loaded.error : '';
  useEffect(() => {
    let active = true;
    void load(`${owner}:${inputKey}`).then(result => { if (active) setLoaded({ key: requestKey, survey: result, error: '' }); })
      .catch(e => { if (active) setLoaded({ key: requestKey, survey: null, error: e instanceof Error ? e.message : '문항을 불러오지 못했어요.' }); });
    return () => { active = false; };
  }, [owner, inputKey, requestKey]);
  return <><Stepper cur="quiz" /><Page title="사전 점검"
    lead="프로젝트 요약과 키우고 싶은 역량, 개인 프로필을 참고해 선정 스킬의 역량을 확인해요. 설문을 모두 마치면 퀴즈로 이어집니다.">
    {error ? <div className="card"><p role="alert">{error}</p><div className="actions">
      <button className="btn line" onClick={() => go(paths.newDetailsCheck)}>입력 내용 확인</button>
      <button className="btn pri" onClick={() => setAttempt(n => n + 1)}>다시 시도하기</button></div></div>
      : survey ? <SurveyFlow key={survey.generationId} survey={survey} initialAnswers={survey.answers} initialCompleted={survey.completed} onContinue={() => go(paths.newResult)}
        onSave={async (answers, complete) => {
          if (!id) throw new Error('작성 중인 로드맵을 확인해 주세요.');
          try {
            await request(`/api/v2/drafts/${id}/survey/answers`, { method: 'PUT', body: JSON.stringify({ generationId: survey.generationId, answers, complete }) });
            if (complete) await pullDraft();
          } catch (e) {
            if (e instanceof SurveyRequestError && e.code === 'SURVEY_INPUT_CHANGED') {
              setAttempt(n => n + 1);
            }
            throw e;
          }
        }} /> : <div className="loading" role="status" aria-live="polite"><span className="sp" aria-hidden="true" /><span>프로젝트와 희망 역량에 맞춰 스킬·문항을 준비하고 있어요.</span></div>}
  </Page></>;
}

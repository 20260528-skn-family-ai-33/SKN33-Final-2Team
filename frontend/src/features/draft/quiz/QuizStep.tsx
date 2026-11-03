import { loadSurvey, SurveyRequestError, type Stored } from './surveyRequest';
import { prepareRoadmaps } from '../prepareRoadmaps';
import { sameJ } from '@/shared/lib/format';
import { useEffect, useRef, useState } from 'react';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { Page } from '@/shared/ui/parts';
import { saveSurvey, surveyScopeCurrent } from './saveSurvey';
import { surveyState } from './surveyState';
import { inputSignature, invalidateDraft } from '../invalidation';
import { answerMemoryKey, pendingAnswers, rememberAnswers } from './assessment/answerMemory';
import { Stepper } from '../Stepper';
import { SurveyFlow, type SurveyFlowHandle } from './assessment/SurveyFlow';

export function QuizStep() {
  const surveyRef = useRef<SurveyFlowHandle>(null);
  const owner = useWs(s => s.owner);
  const id = useWs(s => s.draftId);
  const inputKey = useWs(s => inputSignature(s.draft));
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
    void loadSurvey(`${owner}:${inputKey}`).then(result => { if (active && ws().owner === owner && ws().draftId === id && inputSignature(ws().draft) === inputKey) {
      setLoaded({ key: requestKey, survey: result, error: '' });
      const pending = pendingAnswers(answerMemoryKey(owner, id, result.generationId, inputKey));
      updateWs(s => {
        const dirty = !result.completed && pending && !sameJ(pending.answers, result.answers);
        const previous = s.draft.v2Assessment;
        s.draft.v2Assessment = surveyState(previous, result, !!dirty);
        if (dirty) invalidateDraft(s, 'answers');
      });
    } })
      .catch(e => { if (active) setLoaded({ key: requestKey, survey: null, error: e instanceof Error ? e.message : '문항을 불러오지 못했어요.' }); });
    return () => { active = false; };
  }, [owner, id, inputKey, requestKey]);
  return <><Stepper cur="quiz" busy={saving} /><Page title={<span style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>역량 테스트
    <button type="button" className="btn line" style={{ fontSize: 12, padding: '5px 10px', minHeight: 0 }} disabled={!survey || survey.completed} onClick={() => surveyRef.current?.randomize()}>test용으로 삭제예정 · 무작위 선택</button>
  </span>}
    lead="프로젝트 요약과 키우고 싶은 역량, 개인 프로필을 참고해 선정 스킬의 역량을 확인해요. 설문을 모두 마치면 퀴즈로 이어집니다.">
    {error ? <div className="card"><p role="alert">{error}</p><div className="actions">
      <button className="btn line" onClick={() => go(paths.newDetailsCheck)}>입력 내용 확인</button>
      <button className="btn pri" onClick={() => setAttempt(n => n + 1)}>다시 시도하기</button></div></div>
      : survey ? <SurveyFlow ref={surveyRef} key={survey.generationId} survey={survey} initialAnswers={survey.completed ? survey.answers : pending?.answers || survey.answers} initialPhase={survey.completed ? undefined : pending?.phase} initialCompleted={survey.completed}
        onProgress={(answers, phase) => {
          if (!id || !surveyScopeCurrent({owner,id,inputKey,generationId:survey.generationId})) return;
          rememberAnswers(memoryKey, answers, phase);
          if (!sameJ(answers, survey.answers)) updateWs(s => invalidateDraft(s, 'answers'));
        }} onContinue={() => { if (id && surveyScopeCurrent({owner,id,inputKey,generationId:survey.generationId})) go(paths.newResult); }}
        onSave={async (answers, complete) => {
          if (!id) throw new Error('작성 중인 로드맵을 확인해 주세요.');
          setSaving(true);
          try {
            const scope = {owner,id,inputKey,generationId:survey.generationId};
            const saved = await saveSurvey(scope, answers, complete);
            if (!surveyScopeCurrent(scope)) return;
            setLoaded({ key: requestKey, survey: saved, error: '' });
            if (complete) void prepareRoadmaps().catch(() => {});
          } catch (e) {
            if (e instanceof SurveyRequestError && e.code === 'SURVEY_INPUT_CHANGED') {
              setAttempt(n => n + 1);
            }
            throw e;
          } finally { setSaving(false); }
        }} /> : <div className="loading" role="status" aria-live="polite"><span className="sp" aria-hidden="true" /><span>프로젝트와 희망 역량에 맞춰 스킬·문항을 준비하고 있어요.</span></div>}
  </Page></>;
}

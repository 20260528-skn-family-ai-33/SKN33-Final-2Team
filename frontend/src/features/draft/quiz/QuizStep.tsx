import { loadSurvey, request, SurveyRequestError, type Stored } from './surveyRequest';
import { prepareRoadmaps } from '../prepareRoadmaps';
import { sameJ } from '@/shared/lib/format';
import { useEffect, useRef, useState } from 'react';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { Page } from '@/shared/ui/parts';
import { Skeleton } from '@/shared/ui/Skeleton';
import { saveSurvey, surveyScopeCurrent } from './saveSurvey';
import { surveyState } from './surveyState';
import { inputSignature, invalidateDraft } from '../invalidation';
import { answerMemoryKey, pendingAnswers, rememberAnswers } from './assessment/answerMemory';
import { Stepper } from '../Stepper';
import { useTestTools } from '@/shared/lib/testTools';
import { SurveyFlow, type SurveyFlowHandle } from './assessment/SurveyFlow';

export function QuizStep() {
  const recoveries = useRef<Record<string,number>>({});
  const surveyRef = useRef<SurveyFlowHandle>(null);
  const owner = useWs(s => s.owner);
  const id = useWs(s => s.draftId);
  const inputKey = useWs(s => inputSignature(s.draft));
  const go = useGo();
  /* 무작위 선택은 시험용이라 개발 서버와 시연 도구를 켠 빌드에서만 보인다(#74 · #224) */
  const testTools = useTestTools();
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
      .catch(e => { if (active) setLoaded({ key: requestKey, survey: null, error: e instanceof Error ? e.message : '설문을 불러오지 못했어요.' }); });
    return () => { active = false; };
  }, [owner, id, inputKey, requestKey]);
  useEffect(() => {
    if (!id || !survey || (survey.quizStatus !== 'pending' && survey.quizStatus !== 'interrupted')) return;
    let active=true;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout>;
    const poll = () => {
      void request(`/api/v2/drafts/${id}/survey`, { signal: AbortSignal.timeout(10000) }).then(async result => {
        if (active && result && result.generationId===survey.generationId && ws().owner===owner && ws().draftId===id && inputSignature(ws().draft)===inputKey)
          {
            failures = 0;
            if(result.quizStatus==='pending')return;
            if(result.quizStatus==='interrupted' && (recoveries.current[result.generationId]||0)<2){
              recoveries.current[result.generationId]=(recoveries.current[result.generationId]||0)+1;
              await request(`/api/v2/drafts/${id}/survey`, { method: 'POST', signal: AbortSignal.timeout(10000) });
              return;
            }
            const settled = result.quizStatus === 'interrupted' ? { ...result, quizStatus: 'failed' as const } : result;
            active = false;
            setLoaded(old => old?.survey?.quizStatus==='ready' ? old : {key:requestKey,survey:settled,error:''});
            const currentPending = pendingAnswers(answerMemoryKey(owner, id, result.generationId, inputKey));
            updateWs(s => {
              const dirty = !result.completed && currentPending && !sameJ(currentPending.answers, result.answers);
              s.draft.v2Assessment = surveyState(s.draft.v2Assessment, settled, !!dirty);
            });
          }
      }).catch(() => {
        if (active && ++failures >= 5) {
          active = false;
          setLoaded(old => old?.key === requestKey && old.survey
            ? { ...old, survey: { ...old.survey, quizStatus: 'failed' } } : old);
        }
      }).finally(() => {
        if (active) timer = setTimeout(poll, 1000);
      });
    };
    timer = setTimeout(poll, 1000);
    return () => { active = false; clearTimeout(timer); };
  },[id,owner,inputKey,requestKey,survey]);
  return <><Stepper cur="quiz" busy={saving} /><Page title={<span style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>역량 테스트
    {testTools ? <button type="button" className="btn line" style={{ fontSize: 12.5, padding: '5px 10px', minHeight: 0 }} disabled={!survey || survey.completed} onClick={() => surveyRef.current?.randomize()}>시험용 · 무작위 선택</button> : null}
  </span>}
    lead="프로젝트와 키우고 싶은 역량, 지금 하는 업무에 맞춘 설문과 퀴즈예요. 결과는 로드맵 3안을 내 수준에 맞추는 데 써요.">
    {error ? <div className="card"><p role="alert">{error}</p><div className="actions">
      <button className="btn line" onClick={() => go(paths.newDetailsCheck)}>입력 내용 확인</button>
      <button className="btn pri" onClick={() => setAttempt(n => n + 1)}>다시 시도하기</button></div></div>
      : survey ? <SurveyFlow ref={surveyRef} key={survey.generationId} survey={survey} initialAnswers={survey.completed ? survey.answers : pending?.answers || survey.answers} initialPhase={survey.completed ? undefined : pending?.phase} initialCompleted={survey.completed}
        onRetry={() => setAttempt(n => n + 1)} onProgress={(answers, phase) => {
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
            setLoaded(old => old?.key === requestKey && old.survey?.generationId === saved.generationId && old.survey.quizStatus === 'ready' && saved.quizStatus !== 'ready'
              ? { key: requestKey, survey: { ...old.survey, answers: saved.answers, completed: saved.completed }, error: '' }
              : { key: requestKey, survey: saved, error: '' });
            if (complete) void prepareRoadmaps().catch(() => {});
          } catch (e) {
            if (e instanceof SurveyRequestError && e.code === 'SURVEY_INPUT_CHANGED') {
              setAttempt(n => n + 1);
            }
            throw e;
          } finally { setSaving(false); }
        }} /> : <><div className="loading" role="status" aria-live="polite"><span className="sp" aria-hidden="true" /><span>프로젝트와 희망 역량에 맞춰 스킬·문항을 준비하고 있어요.</span></div><Skeleton kind="quiz" /></>}
  </Page></>;
}
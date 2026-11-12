import { useEffect, useState } from 'react';
import { useWs } from '@/shared/state/workspace';
import { SurveyFlow } from '../quiz/assessment/SurveyFlow';
import { request, type Stored } from '../quiz/surveyRequest';
import { assessmentSummary } from './assessmentSummary';
import './assessmentSummary.css';

export function AssessmentResults() {
  const id = useWs(s => s.draftId), generation = useWs(s => s.draft.v2Assessment?.generationId);
  const [survey, setSurvey] = useState<Stored | null>(null), [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    if (id) void request(`/api/v2/drafts/${id}/survey`).then(v => { if (active) { setSurvey(v); setError(''); } }).catch(() => { if (active) setError('저장된 테스트 결과를 읽지 못했어요.'); });
    return () => { active = false; };
  }, [id, generation, attempt]);
  if (error) return <div className="card"><p role="alert">{error}</p><div className="actions"><button type="button" className="btn line" onClick={() => { setError(''); setAttempt(n => n + 1); }}>다시 불러오기</button></div></div>;
  if (!survey?.completed) return <p role="status">테스트 결과를 불러오는 중…</p>;
  return <CompletedAssessment key={survey.generationId} survey={survey} />;
}

/** 스킬별 결과를 먼저 보여 준다(#224). 문항별 답과 해설은 그 아래 */
function ResultSummary({ survey }: { survey: Stored }) {
  const summary = assessmentSummary(survey, survey.answers);
  return (
    <section className="card result-summary" aria-label="역량 테스트 결과 요약">
      <h2>한눈에 보기</h2>
      <p className="result-summary-lead">
        {summary.quizTotal ? <>퀴즈 <b>{summary.quizTotal}문항 중 {summary.quizCorrect}문항</b>을 맞혔어요. </> : null}
        이 결과를 바탕으로 로드맵 3안을 만들어요.
      </p>
      <ul>
        {summary.skills.map(row => (
          <li key={row.skill}>
            <b>{row.skill}</b>
            <span>퀴즈 {row.quizTotal ? `${row.quizCorrect} / ${row.quizTotal} 정답` : '채점 정보 없음'}</span>
            <span>설문 자기 평가 {row.selfAverage == null ? '없음' : `평균 ${row.selfAverage} / 5`}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// 테스트 직후 설문 탭이 먼저 보이면 앞 단계로 돌아간 것처럼 보여 퀴즈 결과부터 연다. 탭 순서는 그대로다.
export function CompletedAssessment({ survey }: { survey: Stored }) {
  return <>
    <ResultSummary survey={survey} />
    <SurveyFlow survey={survey} initialAnswers={survey.answers} initialCompleted initialPhase="quizzes" review onSave={async () => {}} />
  </>;
}

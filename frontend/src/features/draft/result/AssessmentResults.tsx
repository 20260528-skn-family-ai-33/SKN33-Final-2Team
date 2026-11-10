import { useEffect,useState } from 'react';
import { useWs } from '@/shared/state/workspace';
import { SurveyFlow } from '../quiz/assessment/SurveyFlow';
import { request,type Stored } from '../quiz/surveyRequest';
export function AssessmentResults(){
 const id=useWs(s=>s.draftId),generation=useWs(s=>s.draft.v2Assessment?.generationId);
 const [survey,setSurvey]=useState<Stored|null>(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;if(id)void request(`/api/v2/drafts/${id}/survey`).then(v=>{if(active)setSurvey(v);}).catch(()=>{if(active)setError('저장된 점검 결과를 읽지 못했어요.');});return()=>{active=false;};},[id,generation]);
 if(error)return <p role="alert">{error}</p>;
 if(!survey?.completed)return <p role="status">완료한 점검 결과를 불러오는 중…</p>;
 return <CompletedAssessment key={survey.generationId} survey={survey}/>;
}
// 테스트 직후 설문 탭이 먼저 보이면 앞 단계로 돌아간 것처럼 보여 퀴즈 결과부터 연다. 탭 순서는 그대로다.
export function CompletedAssessment({survey}:{survey:Stored}){
 return <SurveyFlow survey={survey} initialAnswers={survey.answers} initialCompleted initialPhase="quizzes" review onSave={async()=>{}}/>;
}

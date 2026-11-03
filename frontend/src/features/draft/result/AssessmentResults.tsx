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
 return <SurveyFlow key={survey.generationId} survey={survey} initialAnswers={survey.answers} initialCompleted review onSave={async()=>{}}/>;
}

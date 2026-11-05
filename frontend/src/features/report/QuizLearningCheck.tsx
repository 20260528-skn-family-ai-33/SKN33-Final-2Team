import type { Report } from '@/api/types/plan';
import { quizSummary } from './quizSummary';
import './quizLearningCheck.css';

type Evidence=NonNullable<Report['quizEvidence']>;
export function QuizLearningCheck({ evidence }: { evidence:Evidence }) {
 if(!evidence.length)return null;
 const skills=Array.from(new Set(evidence.map(row=>row.skill)));
 return <details className="card report-survey learning-check" open>
  <summary><span>학습 점검</span><span className="learning-check-count">{skills.length}개 스킬</span></summary>
  <p className="learning-check-intro">어떤 개념을 확인했는지, 사전·사후 정답 수를 함께 살펴보세요.</p>
  <div className="learning-check-groups">{skills.map((skill,index)=>{
   const rows=quizSummary(evidence.filter(row=>row.skill===skill));
   return <section className="learning-check-skill" key={skill} aria-label={skill}>
    <header><span className="learning-check-index">{String(index+1).padStart(2,'0')}</span><h3>{skill}</h3><small>{rows.length}개 항목</small></header>
    <div className="learning-check-head" aria-hidden="true"><span>확인한 개념</span><span>사전</span><span>사후</span></div>
    {rows.map(row=><div className="learning-check-row" key={row.label}>
     <span className="learning-check-concept">{row.label.slice(skill.length+3)}</span>
     <span className="learning-check-score pre" aria-label={`사전 ${row.count}문항 중 ${row.pre}개 정답`}><b>{row.pre}</b><span>/ {row.count}</span></span>
     <span className="learning-check-score post" aria-label={`사후 ${row.count}문항 중 ${row.post}개 정답`}><b>{row.post}</b><span>/ {row.count}</span></span>
    </div>)}
   </section>;
  })}</div>
  <p className="learning-check-note">정답 수 / 문항 수 · 사전·사후는 같은 개념의 다른 문제입니다. 결과는 학습 확인 자료이며 난이도를 보정한 역량 점수가 아닙니다.</p>
 </details>;
}

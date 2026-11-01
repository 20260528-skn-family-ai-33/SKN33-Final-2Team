import type { PlanRecord } from '@/api/types/plan';
import { setAt } from '@/shared/state/bind';
import '@/features/draft/quiz/assessment/style.css';

export function PostQuiz({ R, disabled }: { R: PlanRecord; disabled: boolean }) {
  const groups = R.post.quizSurvey?.groups || [];
  if (!groups.some(group => group.quizzes.length)) return null;
  const questions = groups.flatMap(group => group.quizzes);
  const answered = questions.filter(q => Object.hasOwn(R.post.quizAnswers || {}, q.id)).length;
  return <div className="v2-survey"><h2>배운 내용을 확인해 볼까요?</h2><p>사전과 같은 스킬·개념의 새 문제예요. 가장 적절한 답을 하나 골라 주세요.</p>
    <p className="muted" role="status">답한 문항 {answered} / {questions.length}</p>
    {groups.map(group => <section key={group.skill}><h2>{group.title || group.skill}</h2><p className="muted">확인할 역량: {group.skill}</p>{group.quizzes.map((q, index) => <fieldset key={q.id} disabled={disabled}>
      <legend>{index + 1}. {q.q || q.text}</legend><div className="choices">{q.options?.map((option, value) => <label className={R.post.quizAnswers?.[q.id] === String(value) ? 'selected' : ''} key={value}>
        <input type="radio" name={`post-quiz-${R.id}-${q.id}`} value={value} checked={R.post.quizAnswers?.[q.id] === String(value)} onChange={() => setAt(`plans.${R.id}.post.quizAnswers.${q.id}`, String(value))} /><span>{value + 1}. {option}</span>
      </label>)}</div>
    </fieldset>)}</section>)}
  </div>;
}

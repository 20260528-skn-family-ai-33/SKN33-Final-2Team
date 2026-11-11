import type { PlanRecord } from '@/api/types/plan';
import { setAt } from '@/shared/state/bind';
import { planReports, useWs } from '@/shared/state/workspace';
import '@/features/draft/quiz/assessment/style.css';

export function PostQuiz({ R, disabled, review = false }: { R: PlanRecord; disabled: boolean; review?: boolean }) {
  const details = useWs((s) => planReports(s, R)[0]?.postQuizDetails);
  const detailMap = new Map((details || []).map((d) => [d.id, d]));
  const groups = R.post.quizSurvey?.groups || [];
  if (!groups.some(group => group.quizzes.length)) return null;
  const questions = groups.flatMap(group => group.quizzes);
  const answered = questions.filter(q => Object.hasOwn(R.post.quizAnswers || {}, q.id)).length;
  return <div className={`v2-survey${review ? ' v2-survey-review' : ''}`}><h2>배운 내용을 확인해 볼까요?</h2>
    <p>{review ? '저장한 응답을 확인하는 화면입니다. 답변은 변경할 수 없어요.' : '사전과 같은 스킬·개념의 새 문제예요. 가장 적절한 답을 하나 골라 주세요.'}</p>
    <p className="muted" role="status">답한 문항 {answered} / {questions.length}</p>
    {groups.map(group => <section key={group.skill}><h2>{group.title || group.skill}</h2><p className="muted">확인할 역량: {group.skill}</p>{group.quizzes.map((q, index) => {
      const detail = detailMap.get(q.id);
      const answer = typeof q.answer === 'number' ? q.answer : typeof detail?.correctIndex === 'number' ? detail.correctIndex : detail?.correct && q.options ? q.options.indexOf(detail.correct) : -1;
      const explain = q.explain || detail?.explanation;
      const ans = R.post.quizAnswers?.[q.id] ?? (detail?.selectedIndex !== undefined ? String(detail.selectedIndex) : undefined);
      const hasAnswer = answer >= 0;
      const outcome = review && hasAnswer && ans !== undefined ? (Number(ans) === answer ? 'correct' : 'wrong') : null;
      return <fieldset key={q.id} disabled={disabled}>
        <legend>{review ? <><span className={`quiz-result-number${outcome ? ' ' + outcome : ''}`}>{index + 1}{outcome ? ` · ${outcome === 'correct' ? '정답' : '오답'}` : ''}</span> {q.q || q.text}</> : <>{index + 1}. {q.q || q.text}</>}</legend>
        <div className="choices">{q.options?.map((option, value) => {
          const chosen = ans === String(value);
          const correct = review && hasAnswer && answer === value;
          const wrong = review && chosen && hasAnswer && !correct;
          return <label className={[chosen ? 'selected' : '', correct ? 'answer-correct' : '', wrong ? 'answer-wrong' : '', correct && chosen ? 'answer-chosen-correct' : ''].filter(Boolean).join(' ')} key={value}>
            <input type="radio" name={`post-quiz-${R.id}-${q.id}`} value={value} checked={chosen} onChange={() => setAt(`plans.${R.id}.post.quizAnswers.${q.id}`, String(value))} />
            <span>{value + 1}. {option}{review && (correct ? <small className="answer-label">{chosen ? '내 선택 · 정답' : '정답'}</small> : wrong ? <small className="answer-label">내 선택 · 오답</small> : chosen ? <small className="answer-label">내 선택</small> : null)}</span>
          </label>;
        })}</div>
        {review && explain && <p className="quiz-explanation"><b>해설</b> {explain}</p>}
      </fieldset>;
    })}</section>)}
  </div>;
}

import { useImperativeHandle, useState, type Ref } from 'react';
import { complete, type Answers, type Phase, type Survey } from './flow';
import './style.css';

export type SurveyFlowHandle = { randomize: () => number };
type Props = { onRetry?: () => void; ref?: Ref<SurveyFlowHandle>; survey: Survey; initialAnswers?: Answers; initialCompleted?: boolean; review?: boolean; initialPhase?: Phase; onProgress?: (answers: Answers, phase: Phase) => void; onContinue?: () => void;
  onSave: (answers: Answers, finished: boolean) => Promise<void> };
const scale = ['전혀 아니다', '아니다', '보통이다', '그렇다', '매우 그렇다'];

export function SurveyFlow({ onRetry, ref, survey, initialAnswers = {}, initialCompleted = false, review = false, initialPhase, onProgress, onContinue, onSave }: Props) {
  const [answers, setAnswers] = useState<Answers>(initialAnswers);
  const [phase, setPhase] = useState<Phase>(initialPhase || (!initialCompleted && complete(survey, initialAnswers, 'surveys') ? 'quizzes' : 'surveys'));
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [finished, setFinished] = useState(initialCompleted);
  /* 빠뜨린 문항 표시: 넘어가려다 막혔을 때부터 켠다 */
  const [marked, setMarked] = useState(false);
  useImperativeHandle(ref, () => ({ randomize: () => {
    if (saving || finished) return 0;
    const random: Answers = { ...answers };
    for (const group of survey.groups) {
      for (const q of group.surveys) if (!Object.hasOwn(random, q.id)) random[q.id] = Math.floor(Math.random() * 5) + 1;
      for (const q of group.quizzes) {
        if (q.options?.length && !Object.hasOwn(random, q.id)) random[q.id] = Math.floor(Math.random() * q.options.length);
      }
    }
    const count = Object.keys(random).length - Object.keys(answers).length;
    if (count) { setAnswers(random); onProgress?.(random, phase); setError(''); }
    return count;
  } }));
  const questions = survey.groups.flatMap(g => g[phase]);
  const answered = questions.filter(q => Object.hasOwn(answers, q.id)).length;
  const totalAnswered = survey.groups.flatMap(g => [...g.surveys, ...g.quizzes]).filter(q => Object.hasOwn(answers, q.id)).length;
  function showMissing(message: string) {
    setMarked(true); setError(message);
    requestAnimationFrame(() => document.querySelector('.v2-survey fieldset.is-missing')?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  }
  function navigate(target: Phase) {
    if (saving) return;
    if (!review && target === 'quizzes' && !complete(survey, answers, 'surveys')) {
      showMissing('설문에 아직 답하지 않은 문항이 있어요. 표시한 문항에 답한 뒤 퀴즈로 이동해 주세요.');
      return;
    }
    setMarked(false);
    setPhase(target); onProgress?.(answers, target); setError('');
  }
  async function next() {
    if (saving) return;
    if (!complete(survey, answers, phase)) {
      showMissing(`아직 답하지 않은 문항이 ${questions.length - answered}개 있어요. 표시한 문항에 답해 주세요.`);
      return;
    }
    setMarked(false);
    setSaving(true); setError('');
    try {
      await onSave({ ...answers }, phase === 'quizzes');
      if (phase === 'surveys') { setPhase('quizzes'); onProgress?.(answers, 'quizzes'); window.scrollTo(0, 0); }
      else { setFinished(true); onContinue?.(); }
    } catch {
      setError('응답을 저장하지 못했어요. 선택한 답변은 유지됩니다. 다시 시도해 주세요.');
    } finally { setSaving(false); }
  }
  if (finished && !review) return <div className="v2-survey"><h2>역량 테스트를 완료했어요.</h2><p>설문과 퀴즈 응답이 저장되었습니다.</p>{onContinue && <button className="primary" onClick={onContinue}>다음: 테스트 결과</button>}</div>;
  const quizPending = phase === 'quizzes' && (survey.quizStatus === 'pending' || (!questions.length && survey.quizStatus !== 'failed'));
  const quizFailed = phase === 'quizzes' && survey.quizStatus === 'failed';
  return <div className={`v2-survey${review?' v2-survey-review':''}`}>
    <nav aria-label="역량 테스트 순서"><button type="button" disabled={saving} aria-current={phase === 'surveys' ? 'step' : undefined} onClick={() => navigate('surveys')}>1. 설문</button>
      <button type="button" disabled={saving} aria-current={phase === 'quizzes' ? 'step' : undefined} onClick={() => navigate('quizzes')}>2. 퀴즈</button></nav>
    {quizPending ? <div className="loading" role="status" aria-live="polite"><span className="sp" aria-hidden="true" /><span>퀴즈를 준비하고 있어요.</span></div>
      : quizFailed ? <div className="card"><p role="alert">퀴즈 준비를 완료하지 못했어요. 설문 응답은 유지됩니다.</p><div className="actions"><button type="button" className="btn pri" onClick={onRetry}>퀴즈 다시 준비</button></div></div>
      : <>
        <h2>{review ? phase === 'surveys' ? '설문에서 고른 답' : '퀴즈 정답과 해설' : phase === 'surveys' ? '지금의 나를 살펴볼까요?' : '배울 내용을 확인해 볼까요?'}</h2>
        <p>{review ? '저장한 응답을 확인하는 화면입니다. 답변은 변경할 수 없어요.' : phase === 'surveys' ? '각 문장에 나에게 맞는 정도를 선택해 주세요.' : '각 문항에서 가장 적절한 답을 하나 골라 주세요.'}</p>
        {!review && <p className="muted" role="status">답한 문항 {answered} / {questions.length} · 전체 {totalAnswered}/{survey.questionCount}문항</p>}
        {survey.groups.map(group => <section key={group.skill}>
          <h2>{group.title}</h2><p className="muted">확인할 역량: {group.skill}</p>
          {group[phase].map((q, index) => {
            const outcome=review&&phase==='quizzes'&&typeof q.answer==='number'&&Object.hasOwn(answers,q.id)?answers[q.id]===q.answer?'correct':'wrong':null;
            const missing=marked&&!review&&!Object.hasOwn(answers,q.id);
            return <fieldset key={q.id} disabled={saving || review} className={missing?'is-missing':undefined}>
            <legend>{review&&phase==='quizzes'?<><span className={`quiz-result-number${outcome?' '+outcome:''}`}>{index+1}{outcome?` · ${outcome==='correct'?'정답':'오답'}`:''}</span> {q.q}</>:<>{index + 1}. {phase === 'surveys' ? q.text : q.q}{missing&&<span className="missing-tag">답을 골라 주세요</span>}</>}</legend>
            <div className={phase === 'surveys' ? 'scale' : 'choices'}>
              {(phase === 'surveys' ? scale : q.options ?? []).map((label, i) => {
                const value = phase === 'surveys' ? i + 1 : i;
                const chosen=answers[q.id]===value;
                const correct=review&&phase==='quizzes'&&q.answer===value;
                const wrong=review&&phase==='quizzes'&&chosen&&q.answer!==undefined&&!correct;
                return <label key={value} className={[chosen?'selected':'',correct?'answer-correct':'',wrong?'answer-wrong':'',correct&&chosen?'answer-chosen-correct':''].filter(Boolean).join(' ')}>
                  {!(review&&phase==='surveys')&&<input type="radio" name={q.id} value={value} checked={answers[q.id] === value}
                    onChange={() => { const next = { ...answers, [q.id]: value }; setAnswers(next); onProgress?.(next, phase); setError(''); }} />}
                  <span>{i + 1}. {label}{review&&phase==='quizzes'&&<>{correct?<small className="answer-label">{chosen?'내 선택 · 정답':'정답'}</small>:wrong?<small className="answer-label">내 선택 · 오답</small>:chosen?<small className="answer-label">내 선택</small>:null}</>}</span>
                </label>;
              })}
            </div>
            {review&&phase==='quizzes'&&q.explain&&<p className="quiz-explanation"><b>해설</b> {q.explain}</p>}
          </fieldset>;})}
        </section>)}
      </>}
    {error && <p role="alert" className="error">{error}</p>}
    {!review&&phase==='quizzes'&&!quizPending&&!quizFailed&&<p className="muted finish-note">완료하면 답을 바꿀 수 없어요.</p>}
    {!review&&<footer>{phase === 'quizzes' && <button disabled={saving} onClick={() => navigate('surveys')}>이전: 설문</button>}
      <button className="primary" disabled={saving || quizPending || quizFailed} onClick={() => void next()}>
        {saving ? '저장 중…' : phase === 'surveys' ? '다음: 퀴즈' : '역량 테스트 완료'}
      </button></footer>}
  </div>;
}

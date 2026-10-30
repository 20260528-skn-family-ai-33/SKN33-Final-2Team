import { useState } from 'react';
import { complete, type Answers, type Phase, type Survey } from './flow';
import './style.css';

type Props = { survey: Survey; initialAnswers?: Answers; initialCompleted?: boolean; onContinue?: () => void;
  onSave: (answers: Answers, finished: boolean) => Promise<void> };
const scale = ['전혀 아니다', '아니다', '보통이다', '그렇다', '매우 그렇다'];

export function SurveyFlow({ survey, initialAnswers = {}, initialCompleted = false, onContinue, onSave }: Props) {
  const [answers, setAnswers] = useState<Answers>(initialAnswers);
  const [phase, setPhase] = useState<Phase>(!initialCompleted && complete(survey, initialAnswers, 'surveys') ? 'quizzes' : 'surveys');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [finished, setFinished] = useState(false);
  const questions = survey.groups.flatMap(g => g[phase]);
  const answered = questions.filter(q => Object.hasOwn(answers, q.id)).length;
  async function next() {
    if (saving) return;
    if (!complete(survey, answers, phase)) {
      setError('모든 문항 선택을 완료해 주세요.');
      return;
    }
    setSaving(true); setError('');
    try {
      await onSave({ ...answers }, phase === 'quizzes');
      if (phase === 'surveys') { setPhase('quizzes'); window.scrollTo(0, 0); }
      else if (onContinue) onContinue();
      else setFinished(true);
    } catch {
      setError('응답을 저장하지 못했어요. 선택한 답변은 유지됩니다. 다시 시도해 주세요.');
    } finally { setSaving(false); }
  }
  if (finished) return <div className="v2-survey"><h2>사전 점검을 완료했어요.</h2><p>설문과 퀴즈 응답이 저장되었습니다.</p>{onContinue && <button className="primary" onClick={onContinue}>다음: 점검 결과</button>}</div>;
  return <div className="v2-survey">
    <nav aria-label="사전 점검 순서"><span aria-current={phase === 'surveys' ? 'step' : undefined}>1. 설문</span>
      <span aria-current={phase === 'quizzes' ? 'step' : undefined}>2. 퀴즈</span></nav>
    <h2>{phase === 'surveys' ? '지금의 나를 살펴볼까요?' : '배울 내용을 확인해 볼까요?'}</h2>
    <p>{phase === 'surveys' ? '각 문장에 나에게 맞는 정도를 선택해 주세요.' : '각 문항에서 가장 적절한 답을 하나 골라 주세요.'}</p>
    <p className="muted" role="status">답한 문항 {answered} / {questions.length} · 전체 {survey.questionCount}문항</p>
    {survey.groups.map(group => <section key={group.skill}>
      <h2>{group.title}</h2><p className="muted">확인할 역량: {group.skill}</p>
      {group[phase].map((q, index) => <fieldset key={q.id} disabled={saving}>
        <legend>{index + 1}. {phase === 'surveys' ? q.text : q.q}</legend>
        <div className={phase === 'surveys' ? 'scale' : 'choices'}>
          {(phase === 'surveys' ? scale : q.options ?? []).map((label, i) => {
            const value = phase === 'surveys' ? i + 1 : i;
            return <label key={value} className={answers[q.id] === value ? 'selected' : ''}>
              <input type="radio" name={q.id} value={value} checked={answers[q.id] === value}
                onChange={() => { setAnswers(a => ({ ...a, [q.id]: value })); setError(''); }} />
              <span>{i + 1}. {label}</span>
            </label>;
          })}
        </div>
      </fieldset>)}
    </section>)}
    {error && <p role="alert" className="error">{error}</p>}
    <footer>{phase === 'quizzes' && <button disabled={saving} onClick={() => { setPhase('surveys'); setError(''); }}>이전: 설문</button>}
      <button className="primary" disabled={saving} onClick={() => void next()}>
        {saving ? '저장 중…' : phase === 'surveys' ? '다음: 퀴즈' : '사전 점검 완료'}
      </button></footer>
  </div>;
}

import type { Report } from '@/api/types/plan';
import { quizComparison, type Mark, type QuizItem, type Tally } from './comparison';
import './comparisonViz.css';
import './quizLearningCheck.css';

type Evidence = NonNullable<Report['quizEvidence']>;
type Phase = 'pre' | 'post';
const PHASE_TEXT: Record<Phase, string> = { pre: '사전', post: '사후' };
const MARK_TEXT: Record<Mark, string> = { correct: '정답', wrong: '오답', none: '채점 근거 없음' };

/** 채점한 문항이 없으면 0 / 0 대신 '채점 근거 없음'으로 읽힌다 */
const tallyLabel = (phase: Phase, tally: Tally) => (tally.graded ? `${PHASE_TEXT[phase]} ${tally.graded}문항 중 ${tally.correct}개 정답` : `${PHASE_TEXT[phase]} 채점 근거 없음`);

/** 스킬 한 줄의 사전 또는 사후: 점 하나가 문항 하나, 같은 자리의 점은 같은 개념 */
function DotCell({ items, tally, phase }: { items: QuizItem[]; tally: Tally; phase: Phase }) {
  return (
    <span className="cmp-grid-cell" role="img" aria-label={tallyLabel(phase, tally)}>
      <span className="cmp-grid-phase">{PHASE_TEXT[phase]}</span>
      <span className="cmp-dots">
        {items.map((item, index) => (
          <span key={index} className={`cmp-dot ${phase} ${item[phase]}`} title={`${item.concept || '스킬 단위'}: ${PHASE_TEXT[phase]} ${MARK_TEXT[item[phase]]}`} />
        ))}
      </span>
      <span className="cmp-grid-count">{tally.graded ? `${tally.correct} / ${tally.graded}` : '–'}</span>
    </span>
  );
}

function Score({ phase, tally }: { phase: Phase; tally: Tally }) {
  return (
    <span className={`learning-check-score ${phase}`} aria-label={tallyLabel(phase, tally)}>
      {tally.graded ? (
        <>
          <b>{tally.correct}</b>
          <span>/ {tally.graded}</span>
        </>
      ) : (
        <span>–</span>
      )}
    </span>
  );
}

export function QuizLearningCheck({ evidence, postDetails }: { evidence: Evidence; postDetails?: Report['postQuizDetails'] }) {
  if (!evidence.length && !postDetails?.length) return null;
  const quiz = quizComparison(evidence);
  const skillCount = evidence.length ? quiz.skills.length : new Set((postDetails ?? []).map((row) => row.skill)).size;
  return (
    <details className="card report-survey learning-check" open>
      <summary>
        <span>학습 점검</span>
        <span className="learning-check-count">{skillCount}개 스킬</span>
      </summary>
      {!!evidence.length && (
        <>
          <p className="learning-check-intro">스킬별로 사전·사후 퀴즈에서 맞힌 문항을 점으로 보여 줍니다. 점 하나가 문항 하나이고, 같은 자리의 점은 같은 개념입니다.</p>
          <ul className="cmp-grid" aria-label="스킬별 사전·사후 정답 수">
            <li className="cmp-grid-head" aria-hidden="true">
              <span>스킬</span>
              <span>사전</span>
              <span>사후</span>
            </li>
            {quiz.skills.map((skill) => (
              <li className="cmp-grid-row" key={skill.skill}>
                <span className="cmp-grid-skill">{skill.skill}</span>
                <DotCell items={skill.items} tally={skill.pre} phase="pre" />
                <DotCell items={skill.items} tally={skill.post} phase="post" />
              </li>
            ))}
          </ul>
          <ul className="cmp-legend">
            <li>
              <span className="cmp-dot pre correct" aria-hidden="true" />
              사전 정답
            </li>
            <li>
              <span className="cmp-dot post correct" aria-hidden="true" />
              사후 정답
            </li>
            <li>
              <span className="cmp-dot wrong" aria-hidden="true" />
              오답
            </li>
            {quiz.ungraded > 0 ? (
              <li>
                <span className="cmp-dot none" aria-hidden="true" />
                채점 근거 없음
              </li>
            ) : null}
          </ul>
          <details className="cmp-more">
            <summary>개념별 정답 수</summary>
            <div className="learning-check-groups">
              {quiz.skills.map((skill, index) => (
                <section className="learning-check-skill" key={skill.skill} aria-label={skill.skill}>
                  <header>
                    <span className="learning-check-index">{String(index + 1).padStart(2, '0')}</span>
                    <h3>{skill.skill}</h3>
                    <small>{skill.concepts.length}개 항목</small>
                  </header>
                  <div className="learning-check-head" aria-hidden="true">
                    <span>확인한 개념</span>
                    <span>사전</span>
                    <span>사후</span>
                  </div>
                  {skill.concepts.map((row) => (
                    <div className="learning-check-row" key={row.concept}>
                      <span className="learning-check-concept">{row.concept || '스킬 단위'}</span>
                      <Score phase="pre" tally={row.pre} />
                      <Score phase="post" tally={row.post} />
                    </div>
                  ))}
                </section>
              ))}
            </div>
          </details>
        </>
      )}
      {!!postDetails?.length && (
        <details className="cmp-more">
          <summary>사후 퀴즈 문항별 결과</summary>
          <ol>
            {postDetails.map((row) => (
              <li key={row.id}>
                <strong>
                  {row.skill} · {row.isCorrect ? '정답' : '오답'}
                </strong>
                <p>{row.question}</p>
                <p>선택 답안 · {row.selected}</p>
                <p>정답 · {row.correct}</p>
                {row.explanation && <p>해설 · {row.explanation}</p>}
              </li>
            ))}
          </ol>
        </details>
      )}
      {!!evidence.length && <p className="learning-check-note">정답 수 / 문항 수 · 사전·사후는 같은 개념의 다른 문제입니다. 결과는 학습 확인 자료이며 난이도를 보정한 역량 점수가 아닙니다.</p>}
    </details>
  );
}

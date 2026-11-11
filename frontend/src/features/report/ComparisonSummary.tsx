/* 결과 보고서 맨 위의 사전·사후 요약 (#116)
   본인 보고서에만 오는 퀴즈·설문 근거로 그린다. 근거가 없는 이전 보고서와 부서장 화면에서는 아무것도 그리지 않는다.
   향상률 같은 차이 값은 만들지 않는다: 퀴즈는 사전·사후가 같은 개념의 다른 문제다 */
import type { Report } from '@/api/types/plan';
import { percentOf, quizComparison, surveyComparison, type Tally } from './comparison';
import './comparisonViz.css';

function Meter({ label, tally, phase }: { label: string; tally: Tally; phase: 'pre' | 'post' }) {
  const percent = percentOf(tally);
  if (percent === null) {
    return (
      <div className="cmp-meter-row">
        <span>{label}</span>
        <span className="cmp-meter-empty">채점 근거 없음</span>
      </div>
    );
  }
  return (
    <div className="cmp-meter-row" role="img" aria-label={`${label} ${tally.graded}문항 중 ${tally.correct}개 정답, ${percent}%`}>
      <span>{label}</span>
      <span className="cmp-meter-track">
        <span className={`cmp-meter-fill ${phase}`} style={{ width: `${percent}%` }} />
      </span>
      <span className="cmp-meter-value">
        <b>{tally.correct}</b> / {tally.graded} <small>{percent}%</small>
      </span>
    </div>
  );
}

interface Segment {
  key: string;
  label: string;
  hint?: string;
  count: number;
}

/** 문항 수에 비례하는 띠와, 같은 순서의 범례(0개인 항목도 범례에는 남긴다) */
function Band({ label, segments }: { label: string; segments: Segment[] }) {
  return (
    <>
      <div className="cmp-band" role="img" aria-label={`${label}: ${segments.map((segment) => `${segment.label} ${segment.count}문항`).join(', ')}`}>
        {segments
          .filter((segment) => segment.count > 0)
          .map((segment) => (
            <span key={segment.key} className={`cmp-seg cmp-fill ${segment.key}`} style={{ flex: `${segment.count} 1 0` }} />
          ))}
      </div>
      <ul className="cmp-legend">
        {segments.map((segment) => (
          <li key={segment.key}>
            <span className={`cmp-swatch cmp-fill ${segment.key}`} aria-hidden="true" />
            <span>{segment.label}</span>
            <b>{segment.count}</b>
            {segment.hint ? <small>{segment.hint}</small> : null}
          </li>
        ))}
      </ul>
    </>
  );
}

export function ComparisonSummary({ r }: { r: Report }) {
  const quiz = r.quizEvidence?.length ? quizComparison(r.quizEvidence) : null;
  const survey = r.surveyEvidence?.length ? surveyComparison(r.surveyEvidence) : null;
  if (!quiz && !survey) return null;
  return (
    <section className="card cmp-summary" aria-label="사전·사후 한눈에 보기">
      <h2 className="st">사전·사후 한눈에 보기</h2>
      <div className="cmp-summary-cols">
        {quiz ? (
          <div className="cmp-block">
            <h3>퀴즈 정답 수</h3>
            <Meter label="사전" tally={quiz.pre} phase="pre" />
            <Meter label="사후" tally={quiz.post} phase="post" />
            {quiz.compared > 0 ? (
              <>
                <p className="cmp-sub">같은 개념끼리 짝지은 {quiz.compared}문항의 사전 → 사후</p>
                <Band
                  label="퀴즈 변화"
                  segments={[
                    { key: 'gained', label: '새로 맞힘', hint: '오답 → 정답', count: quiz.shifts.gained },
                    { key: 'kept', label: '계속 맞힘', count: quiz.shifts.kept },
                    { key: 'lost', label: '다시 확인', hint: '정답 → 오답', count: quiz.shifts.lost },
                    { key: 'missed', label: '보완 필요', hint: '오답 → 오답', count: quiz.shifts.missed },
                  ]}
                />
              </>
            ) : null}
            {quiz.ungraded > 0 ? <p className="cmp-sub">채점 근거가 없는 {quiz.ungraded}문항은 빼고 셌어요.</p> : null}
          </div>
        ) : null}
        {survey ? (
          <div className="cmp-block">
            <h3>설문 응답 변화</h3>
            {survey.compared > 0 ? (
              <>
                <p className="cmp-sub">같은 문항 {survey.compared}개의 사전 → 사후</p>
                <Band
                  label="설문 변화"
                  segments={[
                    { key: 'up', label: '높아짐', count: survey.counts.up },
                    { key: 'same', label: '같음', count: survey.counts.same },
                    { key: 'down', label: '낮아짐', count: survey.counts.down },
                  ]}
                />
              </>
            ) : (
              <p className="cmp-sub">사전·사후 응답이 모두 있는 문항이 없어 비교하지 않았어요.</p>
            )}
            {survey.compared > 0 && survey.counts.unknown > 0 ? <p className="cmp-sub">응답이 없는 {survey.counts.unknown}문항은 빼고 셌어요.</p> : null}
          </div>
        ) : null}
      </div>
      <p className="cmp-note">퀴즈는 같은 개념의 다른 문제로, 설문은 같은 문항으로 비교했어요. 학습 확인 자료이며 난이도를 보정한 역량 점수가 아니에요.</p>
    </section>
  );
}

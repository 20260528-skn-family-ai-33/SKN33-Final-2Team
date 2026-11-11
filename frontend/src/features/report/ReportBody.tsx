import { ComparisonSummary } from './ComparisonSummary';
import { QuizLearningCheck } from './QuizLearningCheck';
import { ReportRadars } from './ReportRadars';
import { ReportSchedule } from './ReportSchedule';
import { SurveyDumbbell } from './SurveyDumbbell';
import { SURVEY_CHOICES, surveyComparison } from './comparison';
import { buildSchedule, evidenceSkillCount } from './overview';
/* 보고서 본문: 직원 화면과 부서장 화면(소속 직원 보고서 · 10/15 전체 공개)이 함께 쓴다 (5차 P.reportBody · P.reportDeep) */
import type { PlanRecord, Report } from '@/api/types/plan';
import { DeepReveal } from '@/features/assessment/quizParts';
import { ansLabel } from '@/shared/lib/prefs';
import { Note } from '@/shared/ui/parts';
import './reportOverview.css';
import './surveyComparison.css';

function SurveyComparisonRow({ phase, value }: { phase: 'pre' | 'post'; value?: string | number | null }) {
  const label = phase === 'pre' ? '사전' : '사후';
  return <div className={`report-answer-row report-answer-${phase}`}>
    <b className="report-answer-phase">{label}</b>
    <ol className="report-answer-options" aria-label={`${label} 응답: ${value ? ansLabel(String(value)) : '응답 없음'}`}>
      {SURVEY_CHOICES.map((text, index) => <li key={text} className={Number(value) === index + 1 ? 'is-selected' : ''}>
        <span className="report-answer-number">{index + 1}</span><span>{text}</span>
        {Number(value) === index + 1 && <span className="report-answer-mark">✓ {label}</span>}
      </li>)}
    </ol>
  </div>;
}

/** R: 본인 화면에서만 넘긴다. 보고서 시점의 계획 주차로 전체 일정을 그리는 데 쓴다 */
export function ReportBody({ r, R }: { r: Report; R?: PlanRecord }) {
  const snapshot = r.executionSnapshot;
  // 스킬이 3개 이상이어야 레이더가 도형이 된다. 2개 이하(근거가 없는 부서장 화면·이전 보고서 포함)는 요약 띠를 쓰는 이전 구성으로 보여 준다
  const overview = evidenceSkillCount(r) >= 3;
  const plan = overview && snapshot && R ? [R.plan, ...(R.versions || [])].find((version) => version.version === snapshot.version) : undefined;
  const schedule = snapshot && plan ? buildSchedule(plan.acts, snapshot, plan.weeks) : null;
  // 일정 카드가 활동별 완료 여부를 보여 주면 실행 기록에는 목표 달성·결과물만 남긴다
  const showRecord = !schedule || r.goalSelf !== undefined || r.file !== undefined;
  return (
    <>
      {snapshot && schedule ? <ReportSchedule schedule={schedule} snapshot={snapshot} /> : snapshot && <div className="card"><h2 className="st">{snapshot.early ? '조기 종료 기준 기록' : '학습 종료 기준 기록'}</h2><p className="small muted">기준 시점: {new Date(snapshot.asOf).toLocaleString('ko-KR')} · 이 시점까지 저장된 활동·메모·제출 여부를 반영했어요. 첨부 내용은 검증하지 않았어요.</p></div>}
      {overview ? <ReportRadars r={r} /> : <ComparisonSummary r={r} />}
      {!!r.surveyEvidence?.length && <details className="card report-survey">
        <summary><span>설문 응답 비교</span></summary>
        <p className="small muted">동일한 문항의 사전·사후 선택을 비교해요.</p>
        <SurveyDumbbell survey={surveyComparison(r.surveyEvidence)} />
        <details className="cmp-more">
          <summary>선택지로 보기</summary>
          <ol className="report-survey-questions">{r.surveyEvidence.map((row, index) => <li key={row.id}>
            <b className="small muted">{row.skill || row.area}</b><p className={row.pre && row.post ? Number(row.post) > Number(row.pre) ? 'report-survey-post' : 'report-survey-pre' : undefined}>{index + 1}. {row.text}</p>
            <SurveyComparisonRow phase="pre" value={row.pre} />
            <SurveyComparisonRow phase="post" value={row.post} />
          </li>)}</ol>
        </details>
      </details>}
      {!!(r.quizEvidence?.length || r.postQuizDetails?.length) && <QuizLearningCheck evidence={r.quizEvidence ?? []} postDetails={r.postQuizDetails} open={!overview} />}
      {showRecord && <div className="card" style={{ marginTop: 12 }}>
        <h2 className="st">실행 기록</h2>
        <dl className="kv">
          {!schedule && (
            <>
              <dt>완료</dt>
              <dd>{r.doneTitles.join(', ') || '없음'}</dd>
              <dt>미완료 활동</dt>
              <dd className="muted">{r.restTitles.join(', ') || '없음'}</dd>
            </>
          )}
          {/* 목표 달성 답·결과물은 본인 화면에만 온다(부서장 응답에는 없음 · 없을 때 '붙이지 않음'으로 보이지 않게 줄째 숨김) */}
          {r.goalSelf !== undefined ? (
            <>
              <dt>목표 달성</dt>
              <dd>{r.goalSelf}</dd>
            </>
          ) : null}
          {r.file !== undefined ? (
            <>
              <dt>결과물</dt>
              <dd>
                {r.file ? (
                  <>
                    {r.file.name} <span className="small muted">· 내용 미검증</span>
                  </>
                ) : (
                  '제출물 없음'
                )}
              </dd>
            </>
          ) : null}
        </dl>
      </div>}
      {overview ? (
        <section className="card rpt-result" aria-label="학습 결과">
          <h2 className="st">학습 결과</h2>
          <div className="rpt-result-cols">
            <div className="rpt-result-col">
              <h3>잘된 점</h3>
              <ul className="plain-list">
                {r.good.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
            <div className="rpt-result-col">
              <h3>보완할 점</h3>
              <ul className="plain-list">
                {r.improve.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          </div>
          {r.next ? (
            <>
              <p className="rpt-result-bridge">이 기록을 바탕으로 제안해요 ↓</p>
              <div className="card acc">
                <p className="rpt-next-eyebrow">다음 로드맵 제안 · 참고용</p>
                <p className="rpt-next-goal">{r.next.goal}</p>
                <p className="small muted rpt-next-why">{r.next.why}</p>
              </div>
              <p className="small muted rpt-result-note">새 로드맵은 ‘새 로드맵 작성’에서 목표를 직접 적어 시작해요.</p>
            </>
          ) : null}
        </section>
      ) : (
        <>
          <div className="sec">
            <h2 className="st">잘된 점</h2>
            <div className="card">
              <ul className="plain-list">
                {r.good.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className="sec">
            <h2 className="st">보완할 점</h2>
            <div className="card">
              <ul className="plain-list">
                {r.improve.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className="sec">
            <h2 className="st">다음 로드맵 제안</h2>
            <div className="card acc">
              <p style={{ fontWeight: 650 }}>{r.next?.goal}</p>
              <p className="small muted" style={{ marginTop: 4 }}>
                {r.next?.why}
              </p>
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>
              참고용 제안이에요. 새 로드맵은 ‘새 로드맵 작성’에서 목표를 직접 적어 시작해요.
            </p>
          </div>
        </>
      )}
      <Note>자기보고 응답의 변화예요. 실제 개발 역량이나 인사평가 결과로 보지 않아요. 진단 에이전트가 계산한 수준값은 저장만 하고 보여주지 않아요.</Note>
    </>
  );
}

const RES_TAG: Record<string, string> = { 맞음: 'ok', 틀림: 'bad', 모름: 'mid', '답 안 함': 'mid' };
const LV_TAG: Record<string, string> = { 충분: 'ok', 부분: 'mid', 부족: 'bad' };

/** 보고서의 심화 질문 결과(10/23 · 본인 화면만 · 부서장 화면에는 서버가 빼고 보냄) */
export function ReportDeep({ r, R }: { r: Report; R?: PlanRecord }) {
  if (!r.deep) return null;
  const pd = R && R.post && R.post.deep;
  return (
    <>
      <div className="card" style={{ marginTop: 12 }}>
        <h2 className="st">
          심화 질문 결과{' '}
          <span className="muted small" style={{ fontWeight: 400 }}>
            나만 봐요 · 사전 → 사후
          </span>
        </h2>
        <ul className="plain-list">
          {r.deep.concepts.map((c, i) => (
            <li key={i}>
              {c.concept}{' '}
              <span className="small">
                <span className={`dr-tag ${RES_TAG[c.pre] || 'mid'}`}>{c.pre}</span> → <span className={`dr-tag ${RES_TAG[c.post] || 'mid'}`}>{c.post}</span>
              </span>
            </li>
          ))}
        </ul>
        {r.deep.essays.map((e, i) => (
          <p className="small" style={{ marginTop: 8 }} key={i}>
            <b>{e.area} 서술형</b> {e.pre || '-'} → <span className={`dr-tag ${LV_TAG[e.post || ''] || 'mid'}`}>{e.post || '판단 못 함'}</span>{' '}
            <span className="muted">{e.why || ''}</span>
          </p>
        ))}
        <p className="small muted" style={{ marginTop: 8 }}>
          심화 질문은 학습 확인용이에요. 역량 판정이나 인사평가에 쓰지 않아요.
        </p>
      </div>
      {pd && pd.judge && R?.plan.assess ? (
        <DeepReveal questions={R.plan.assess.questions} dq={pd.quiz} mcqAns={pd.mcq} essayAns={pd.essay} grade={pd.grade} judge={pd.judge} title="사후 심화 질문 정답·모범 답안 보기" />
      ) : null}
    </>
  );
}

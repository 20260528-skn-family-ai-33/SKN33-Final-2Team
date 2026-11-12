import { useRef, useState } from 'react';
import { DeliverableSelection, type DeliverableSelectionHandle } from './DeliverableSelection';
import { trackName, trackTrait } from '@/shared/constants/data';
/* 7. 검토·산출물 선택·확정 (5차 scr['new-review'] · P.confirm · #224)
   요약 → 주차별 일정 → 스킬별 산출물 과제 → 확정하면 일어나는 일 → 아래 고정 요약 줄.
   확정(API-35): 새 로드맵 기록. 시작 방식은 작성 탭에 들어올 때 고른 값을 쓴다(../startModeSheet) */
import { paths } from '@/app/paths';
import { addDays, followingStart, md, monthDay, planWeeks, today0 } from '@/features/home/ganttCalc';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { useGo } from '@/shared/hooks/useGo';
import { hrs } from '@/shared/lib/format';
import { recs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Page, Stats } from '@/shared/ui/parts';
import { Skeleton } from '@/shared/ui/Skeleton';
import { StagesView } from '@/shared/ui/StagesView';
import { confirmReview } from './confirmReview';
import { Stepper } from '../Stepper';
import { STEPS } from '../model';
import { useDraftWatch } from '../useDraftWatch';
import { reviewScope } from './reviewScope';
import { reviewSchedule, weekDates, weekLabel } from './reviewSchedule';
import type { ReviewPlanState } from './reviewPlan';
import '../stepLayout.css';
import './reviewStep.css';

const KIND = { course: '강좌', book: '도서', task: '과제' } as const;

export function ReviewStep() {
  const go = useGo();
  const assessment = useWs(s => !!s.draft.v2Assessment);
  const deliverables = useRef<DeliverableSelectionHandle>(null);
  const scope = useWs(reviewScope);
  const [review, setReview] = useState<ReviewPlanState | null>(null);
  const reviewPlan = review?.scope === scope ? review.plan : null;
  const reviewError = review?.scope === scope ? review.error : undefined;
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const pl = useWs((s) => s.draftPlan);
  const g = useWs((s) => s.draft.gen);
  const chosen = useWs((s) => s.draft.chosen);
  const goal = useWs((s) => s.draft.goal);
  const startMode = useWs((s) => s.draft.startMode);
  const plans = useWs((s) => s.plans);
  const selectedSkills = useWs((s) => s.draft.selectedSkills?.length || 0);
  useDraftWatch();
  async function submit() {
    if (busy || submitting || (assessment && !ready)) return;
    setSubmitting(true);
    try { await confirmReview(go, assessment ? () => deliverables.current?.save() || Promise.resolve(false) : undefined); }
    finally { setSubmitting(false); }
  }
  const optionsLabel = STEPS.find(step => step[0] === 'options')?.[1] || '이전 단계';
  const back = (
    <button type="button" className="btn line" disabled={submitting} onClick={() => go(paths.newOptions)}>
      <Icon name="left" />
      이전: {optionsLabel}
    </button>
  );

  /* 자료를 따로 고르지 않는 예전 흐름: 화면 구성을 그대로 둔다 */
  if (!assessment) {
    if (!pl) return <><Stepper cur="review" busy={submitting} /><Page title="이 로드맵으로 확정할까요?" foot={<>{back}<button className="btn pri" disabled={busy || submitting || !ready} onClick={() => void submit()}>확정하기</button></>}>
      <p role="status">최종 검토 결과를 불러오는 중…</p>
    </Page></>;
    return (
      <>
        <Stepper cur="review" busy={submitting} />
        <Page eyebrow={`${trackName(pl.opt, pl.name)}${g && g.hist && (g.hist[pl.opt] || []).length > 1 ? ` · 버전 ${((g.cur || {})[pl.opt] || 0) + 1}` : ''}`}
          title="이 로드맵으로 확정할까요?" foot={<>{back}<button className="btn pri" disabled={busy || submitting} onClick={() => void submit()}>확정하기</button></>}>
          <div className="card">
            <p style={{ fontWeight: 650 }}>{pl.goal}</p>
            <div style={{ marginTop: 16 }}><Stats pl={pl} bare periodLabel="기간" /></div>
          </div>
          <SkillMap pl={pl} /><div className="sec"><StagesView pl={pl} /></div>
        </Page>
      </>
    );
  }

  const opt = chosen || pl?.opt || '';
  const option = opt ? g?.options[opt] : undefined;
  const courseName = opt ? trackName(opt, option?.name || pl?.name) : '';
  const version = g?.hist && opt && (g.hist[opt] || []).length > 1 ? ((g.cur || {})[opt] || 0) + 1 : null;
  const focus = trackTrait(opt);
  const name = reviewPlan?.displayTitle || pl?.displayTitle || option?.displayTitle || '';
  /* 시작 시점: '끝나고 시작'만 서버가 진행 중인 로드맵이 끝난 다음 주로 미룬다(시작 방식 창과 같은 계산) */
  const today = today0();
  const next = followingStart(recs({ plans }, 'active'));
  const later = startMode === 'after' && next > today;
  const start = later ? next : today;
  const weeks = reviewPlan ? planWeeks(reviewPlan) : null;
  const rows = reviewPlan ? reviewSchedule(reviewPlan) : [];
  const taskCount = reviewPlan ? reviewPlan.acts.filter(act => !act.res).length : 0;
  const costText = (cost: number, unknown: boolean) => cost === 0 ? (unknown ? '가격 확인 필요' : '무료') : `${cost.toLocaleString('ko-KR')}원${unknown ? '+' : ''}`;
  /* 계산을 기다리는 동안에는 값 자리에 뼈대를 그린다(높이는 값이 들어왔을 때와 같다). 실패하면 글로 알린다 */
  const waiting = reviewError ? '계산하지 못했어요' : <span className="skel rv-skel-num" aria-hidden="true" />;
  const waitingSub = reviewError ? ' ' : <span className="skel rv-skel-sub" aria-hidden="true" />;
  const skillCount = Math.min(3, Math.max(1, selectedSkills || 2));
  /* 확정할 수 없는 이유는 버튼 옆에 미리 적는다 */
  const block = reviewError ? '검토 내용을 불러오지 못했어요. 아래에서 다시 불러와 주세요'
    : submitting ? '확정하고 있어요'
    : busy || !ready || !reviewPlan ? '검토 내용을 준비하고 있어요'
    : null;

  return (
    <>
      <Stepper cur="review" busy={submitting} />
      <Page eyebrow={[courseName, focus, version ? `버전 ${version}` : ''].filter(Boolean).join(' · ')}
        title="이대로 시작할까요?">
        <section className="card rv-summary" aria-label="로드맵 요약">
          {name ? <><span className="rv-label">로드맵 이름</span><h2>{name}</h2></> : null}
          <p className="rv-goal">{pl?.goal || goal}</p>
          <dl className="rv-stats">
            <div>
              <dt>기간</dt>
              <dd><b>{weeks != null ? `${weeks}주` : waiting}</b>
                <span>{weeks == null ? waitingSub : later ? `${monthDay(start)}부터 · 진행 중인 로드맵이 끝난 다음 주` : `오늘 확정하면 ${md(start)} ~ ${md(addDays(start, weeks * 7 - 1))}`}</span></dd>
            </div>
            <div>
              <dt>주당 학습</dt>
              <dd><b>{reviewPlan ? `${reviewPlan.hours}시간` : waiting}</b><span>{' '}</span></dd>
            </div>
            <div>
              <dt>총 학습 시간</dt>
              <dd><b>{reviewPlan ? `약 ${hrs(reviewPlan.totalH)}` : waiting}</b>
                <span>{reviewPlan ? `강좌 ${hrs(reviewPlan.materialHours ?? 0)} + 과제 ${hrs(reviewPlan.taskHours ?? 0)}${reviewPlan.totalHUnknown ? ' · 시간 미확인 자료 있음' : ''}` : waitingSub}</span></dd>
            </div>
            <div>
              <dt>예상 비용</dt>
              <dd><b>{reviewPlan ? costText(reviewPlan.cost, reviewPlan.costUnknown) : waiting}</b>
                <span>{reviewPlan?.costUnknown ? '일부 자료는 가격 확인 필요' : ' '}</span></dd>
            </div>
          </dl>
        </section>

        <section className="step-sec" aria-label="주차별 일정">
          <header className="step-sec-head">
            <span className="step-num">1</span>
            <div>
              <h2>주차별 일정</h2>
            </div>
          </header>
          {rows.length ? (
            <ol className="rv-weeks">
              {rows.map(row => (
                <li key={row.skill}>
                  <div className="rv-week-head"><b>{weekLabel(row)}</b><span>{weekDates(start, row)}</span></div>
                  <h3>{row.skill}</h3>
                  <ul>
                    {row.items.map((item, index) => (
                      <li key={index}>
                        <span className={`rv-dot is-${item.kind}`} aria-hidden="true" />
                        <span className="rv-week-tx">{KIND[item.kind]} · {item.title}</span>
                        <em>{item.kind === 'book' ? '틈틈이' : item.hours != null ? hrs(item.hours) : '시간 미확인'}</em>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          ) : reviewError ? <div className="rv-weeks-wait" role="status">일정을 계산하지 못했어요.</div>
            : <div className="rv-weeks-skel" role="status" aria-label="일정을 계산하고 있어요"><Skeleton kind="columns" count={skillCount} /></div>}
        </section>

        <DeliverableSelection ref={deliverables} onReadyChange={setReady} onBusyChange={setBusy} onPlanChange={setReview} onChangeMaterials={() => go(paths.newOptions)} />

        <section className="rv-after" aria-label="확정하면 일어나는 일">
          <h2>확정하면</h2>
          <ul>
            <li><Icon name="play" /><span><b>{later ? `${monthDay(start)}부터 시작해요.` : `오늘(${md(today)})부터 1주차가 시작돼요.`}</b>
              {later ? ' 진행 중인 로드맵이 끝난 다음 주예요.' : startMode === 'archive' ? ' 진행 중이던 로드맵은 보관돼요.' : ''}</span></li>
            <li><Icon name="users" /><span><b>나와 부서장만 볼 수 있어요.</b></span></li>
            <li><Icon name="edit" /><span><b>확정 뒤에도 내 로드맵에서 수정 요청을 보낼 수 있어요.</b></span></li>
          </ul>
        </section>

        <div className="step-bar">
          <div className="step-bar-sum" aria-live="polite">
            <b>{name || courseName}</b>
            {block ? <span className="step-bar-wait">{block}</span>
              : reviewPlan && weeks != null ? <><span>{weeks}주</span><span>주 {reviewPlan.hours}시간</span><span>{costText(reviewPlan.cost, reviewPlan.costUnknown)}</span><span>과제 {taskCount}개</span></>
              : null}
          </div>
          <div className="step-bar-btns">
            {back}
            <button type="button" className="btn pri" disabled={busy || submitting || !ready} onClick={() => void submit()}>이대로 확정하기</button>
          </div>
        </div>
      </Page>
    </>
  );
}

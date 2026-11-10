import { useRef, useState } from 'react';
import { DeliverableSelection, type DeliverableSelectionHandle } from './DeliverableSelection';
import { trackName } from '@/shared/constants/data';
/* 6. 검토·확정 (5차 scr['new-review'] · P.confirm)
   확정(API-35): 새 로드맵 기록. 진행 중인 로드맵이 있으면 시작 방식을 먼저 묻는다(startModeSheet) */
import type { StartMode } from '@/api/types/draft';
import { paths } from '@/app/paths';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { useGo } from '@/shared/hooks/useGo';
import { useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Page, Stats } from '@/shared/ui/parts';
import { StagesView } from '@/shared/ui/StagesView';
import { confirmReview } from './confirmReview';
import { chooseStartMode } from './startModeSheet';
import { useKickSupport } from '../generation/GenerationStep';
import { SupCell, SupNote } from '../options/support';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';
import { reviewScope } from './reviewScope';
import type { ReviewPlanState } from './reviewPlan';

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
  useDraftWatch();
  useKickSupport();
  async function confirm(startMode?: StartMode) {
    setSubmitting(true);
    try { await confirmReview(go, assessment ? () => deliverables.current?.save() || Promise.resolve(false) : undefined, startMode); }
    finally { setSubmitting(false); }
  }
  function submit() {
    if (busy || submitting || (assessment && !ready)) return;
    chooseStartMode((startMode) => void confirm(startMode));
  }
  if (!pl) return <><Stepper cur="review" busy={submitting} /><Page title="이 로드맵으로 확정할까요?" foot={<>
    <button className="btn line" disabled={submitting} onClick={() => go(paths.newOptions)}>이전: 로드맵·자료 선택</button>
    <button className="btn pri" disabled={busy || submitting || !ready} onClick={submit}>확정하기</button>
  </>}>
    {assessment && (reviewPlan ? <Stats pl={reviewPlan} bare periodLabel="자료 학습 예상 기간" /> : <p role="status">{reviewError ? '검토 시간을 계산하지 못했어요. 아래에서 다시 불러와 주세요.' : '검토할 자료와 선택한 과제 시간을 계산 중…'}</p>)}
    {assessment ? <DeliverableSelection ref={deliverables} onReadyChange={setReady} onBusyChange={setBusy} onPlanChange={setReview} /> : <p role="status">최종 검토 결과를 불러오는 중…</p>}
  </Page></>;
  const o = (g && g.options[pl.opt]) || pl.def;
  return (
    <>
      <Stepper cur="review" busy={submitting} />
      <Page
        eyebrow={`${trackName(pl.opt, pl.name)}${g && g.hist && (g.hist[pl.opt] || []).length > 1 ? ` · 버전 ${((g.cur || {})[pl.opt] || 0) + 1}` : ''}`}
        title="이 로드맵으로 확정할까요?"
        foot={
          <>
            <button className="btn line" disabled={submitting} onClick={() => go(paths.newOptions)}>
              <Icon name="left" />
              이전: 로드맵·자료 선택
            </button>
            <button className="btn pri" disabled={busy || submitting || (assessment && !ready)} onClick={submit}>
              확정하기
            </button>
          </>
        }
      >
        <div className="card">
          <p style={{ fontWeight: 650 }}>{pl.goal}</p>
          <div style={{ marginTop: 16 }}>
            {assessment ? reviewPlan ? <Stats pl={reviewPlan} bare periodLabel="자료 학습 예상 기간" /> : <p role="status">{reviewError ? '검토 시간을 계산하지 못했어요. 아래에서 다시 불러와 주세요.' : '검토할 자료와 선택한 과제 시간을 계산 중…'}</p> : <Stats pl={pl} bare periodLabel="기간" />}
          </div>
        </div>
        {assessment && <DeliverableSelection ref={deliverables} onReadyChange={setReady} onBusyChange={setBusy} onPlanChange={setReview} />}
        {!assessment && <><SkillMap pl={pl} /><div className="sec"><StagesView pl={pl} /></div></>}
        <p className="small muted">자료를 바꾸려면 <button className="link" onClick={() => go(paths.newOptions)}>자료 선택으로 돌아가기</button></p>
        <div className="sec">
          <details className="card flat"><summary>지원 조건 보기</summary>
            <dl className="kv">
              <dt>지원 조건</dt>
              <dd>
                <SupCell o={o} />
              </dd>
            </dl>
          </details>
          <SupNote />
        </div>

      </Page>
    </>
  );
}

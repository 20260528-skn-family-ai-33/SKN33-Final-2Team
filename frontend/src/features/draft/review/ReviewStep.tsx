import { useRef, useState } from 'react';
import { DeliverableSelection, type DeliverableSelectionHandle } from './DeliverableSelection';
import { trackName } from '@/shared/constants/data';
/* 6. 검토·확정 (5차 scr['new-review'] · P.confirm)
   확정(API-35): 새 로드맵 기록. 진행 중인 다른 로드맵은 보관하지 않고 함께 진행한다(10/14 · 묻지 않음) */
import { paths } from '@/app/paths';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { useGo } from '@/shared/hooks/useGo';
import { useMe } from '@/shared/state/session';
import { recs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note, Page, Stats } from '@/shared/ui/parts';
import { StagesView } from '@/shared/ui/StagesView';
import { confirmReview } from './confirmReview';
import { useKickSupport } from '../generation/GenerationStep';
import { SupCell, SupNote } from '../options/support';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';

export function ReviewStep() {
  const go = useGo();
  const assessment = useWs(s => !!s.draft.v2Assessment);
  const deliverables = useRef<DeliverableSelectionHandle>(null);
  const [materialWeeks, setMaterialWeeks] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const pl = useWs((s) => s.draftPlan);
  const g = useWs((s) => s.draft.gen);
  const active = useWs((s) => recs(s, 'active').length);
  const me = useMe();
  useDraftWatch();
  useKickSupport();
  async function submit() {
    if (busy || submitting || (assessment && !ready)) return;
    setSubmitting(true);
    try { await confirmReview(go, assessment ? () => deliverables.current?.save() || Promise.resolve(false) : undefined); }
    finally { setSubmitting(false); }
  }
  if (!pl) return <><Stepper cur="review" busy={submitting} /><Page title="이 로드맵으로 확정할까요?" foot={<>
    <button className="btn line" disabled={submitting} onClick={() => go(paths.newOptions)}>이전: 로드맵·자료 선택</button>
    <button className="btn pri" disabled={busy || submitting || !ready} onClick={() => void submit()}>확정하기</button>
  </>}>
    {assessment ? <DeliverableSelection ref={deliverables} onReadyChange={setReady} onBusyChange={setBusy} onDurationChange={setMaterialWeeks} /> : <p role="status">최종 검토 결과를 불러오는 중…</p>}
  </Page></>;
  const o = (g && g.options[pl.opt]) || pl.def;
  const sup = me?.mySupervisor;
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
            <button className="btn pri" disabled={busy || submitting || (assessment && !ready)} onClick={() => void submit()}>
              확정하기
            </button>
          </>
        }
      >
        <div className="card">
          <p style={{ fontWeight: 650 }}>{pl.goal}</p>
          <div style={{ marginTop: 16 }}>
            <Stats pl={pl} bare periodLabel={assessment ? '자료 학습 예상 기간' : '기간'} periodWeeks={assessment ? materialWeeks : undefined} />
          </div>
        </div>
        {assessment && <DeliverableSelection ref={deliverables} onReadyChange={setReady} onBusyChange={setBusy} onDurationChange={setMaterialWeeks} />}
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
        <Note>
          확정은 내 학습 계획을 정하는 것이에요. 기관의 승인·결재가 아니에요.
          {sup ? ` 확정하면 내 계획을 보는 부서장 ${sup.name} 님은 확정한 로드맵, 진행 상태, 결과 보고서를 볼 수 있어요.` : null}
        </Note>
        {active ? <Note>지금 진행 중인 로드맵 {active}개가 있어요.</Note> : null}
      </Page>
    </>
  );
}

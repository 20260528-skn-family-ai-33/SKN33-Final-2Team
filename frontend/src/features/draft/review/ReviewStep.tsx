import { trackName } from '@/shared/constants/data';
/* 6. 검토·확정 (5차 scr['new-review'] · P.confirm)
   확정(API-35): 새 로드맵 기록. 진행 중인 다른 로드맵은 보관하지 않고 함께 진행한다(10/14 · 묻지 않음) */
import { draftsApi } from '@/api/endpoints/drafts';
import { paths } from '@/app/paths';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { useMe } from '@/shared/state/session';
import { recs, updateWs, useWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note, Page, Stats } from '@/shared/ui/parts';
import { StagesView } from '@/shared/ui/StagesView';
import { DraftSaveError, flush, reloadWorkspace } from '../draftSync';
import { useKickSupport } from '../generation/GenerationStep';
import { openRegenSheet } from '../options/OptionsStep';
import { SupCell, SupNote } from '../options/support';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';

export async function confirmDraft(go: ReturnType<typeof useGo>): Promise<void> {
  try {
    await flush();
    const r = await draftsApi.confirm(ws().draftId as string);
    await reloadWorkspace();
    updateWs((s) => void (s.lastNew = null));
    go(paths.confirmed(r.planId), { force: true });
  } catch (err) {
    if (!(err instanceof DraftSaveError)) failToast(err, '로드맵을 확정하지 못했어요');
  }
}

export function ReviewStep() {
  const go = useGo();
  const pl = useWs((s) => s.draftPlan);
  const g = useWs((s) => s.draft.gen);
  const active = useWs((s) => recs(s, 'active').length);
  const me = useMe();
  useDraftWatch();
  useKickSupport();
  if (!pl) return null;
  const o = (g && g.options[pl.opt]) || pl.def;
  const sup = me?.mySupervisor;
  return (
    <>
      <Stepper cur="review" />
      <Page
        eyebrow={`${trackName(pl.opt, pl.name)}${g && g.hist && (g.hist[pl.opt] || []).length > 1 ? ` · 버전 ${((g.cur || {})[pl.opt] || 0) + 1}` : ''}`}
        title="이 로드맵으로 확정할까요?"
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newOptions)}>
              <Icon name="left" />
              재선택
            </button>
            <button className="btn pri" onClick={() => void confirmDraft(go)}>
              확정하기
            </button>
          </>
        }
      >
        <div className="card">
          <p style={{ fontWeight: 650 }}>{pl.goal}</p>
          <div style={{ marginTop: 16 }}>
            <Stats pl={pl} bare />
          </div>
        </div>
        <SkillMap pl={pl} />
        <div className="sec">
          <StagesView pl={pl} />
        </div>
        <p className="small muted rv-fix">
          고치고 싶은 활동이 있으면{' '}
          <button
            className="link"
            onClick={() => {
              const id = ws().draftPlan?.opt;
              go(paths.newOptions);
              if (id) openRegenSheet(id);
            }}
          >
            <Icon name="history" />
            3안 비교에서 이 안 다시 만들기
          </button>
        </p>
        <div className="sec">
          <div className="card flat">
            <dl className="kv">
              <dt>지원 조건</dt>
              <dd>
                <SupCell o={o} />
              </dd>
            </dl>
          </div>
          <SupNote />
        </div>
        <Note>
          확정은 내 학습 계획을 정하는 것이에요. 기관의 승인·결재가 아니에요.
          {sup ? ` 확정하면 내 계획을 보는 부서장 ${sup.name} 님은 확정한 로드맵, 진행 상태, 결과 보고서를 볼 수 있어요.` : null}
        </Note>
        {active ? <Note>지금 진행 중인 로드맵 {active}개는 그대로 두고, 이 로드맵을 함께 진행해요.</Note> : null}
      </Page>
    </>
  );
}

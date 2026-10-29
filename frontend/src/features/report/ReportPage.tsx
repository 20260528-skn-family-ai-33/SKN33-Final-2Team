import { trackName } from '@/shared/constants/data';
/* 결과 보고서 (5차 scr.report · report-ok) — '확인했어요'를 누르면 이 로드맵을 마친 것으로 기록한다 */
import { useParams } from 'react-router';
import { plansApi } from '@/api/endpoints/plans';
import { paths } from '@/app/paths';
import { reloadWorkspace } from '@/features/draft/draftSync';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { useMe } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { useWs } from '@/shared/state/workspace';
import { Note, Page } from '@/shared/ui/parts';
import { ReportBody, ReportDeep } from './ReportBody';

export function ReportPage() {
  const { rid } = useParams();
  const go = useGo();
  const me = useMe();
  const r = useWs((s) => s.reports.find((x) => x.id === rid) || null);
  const R = useWs((s) => (r ? s.plans[r.planId] : undefined));
  if (!r) return <Page back={paths.checks} title="결과 보고서가 없어요" />;
  const sup = me?.mySupervisor;
  const ok = async () => {
    try {
      await plansApi.confirmReport(r.id);
      await reloadWorkspace();
      go(paths.home);
      toast('결과 보고서를 확인했어요 · 이 로드맵은 지난 로드맵으로 옮겼어요');
    } catch (err) {
      failToast(err, '보고서 확인을 저장하지 못했어요');
    }
  };
  return (
    <Page
      back={paths.checks}
      eyebrow={`결과 보고서 · ${trackName(r.opt)} v${r.version} · ${r.createdAt}`}
      title="학습 결과 보고서"
      lead={r.goal}
      foot={
        r.confirmed ? (
          R ? (
            <button className="btn line" onClick={() => go(paths.roadmap(R.id))}>
              로드맵 보기
            </button>
          ) : undefined
        ) : (
          <button className="btn pri" onClick={() => void ok()}>
            확인했어요
          </button>
        )
      }
    >
      <ReportBody r={r} />
      <ReportDeep r={r} R={R} />
      {sup ? <Note>이 보고서는 내 계획을 보는 부서장 {sup.name} 님도 볼 수 있어요.</Note> : null}
      {r.confirmed ? null : (
        <Note>
          ‘확인했어요’를 누르면 이 로드맵을 마친 것으로 기록하고 내 로드맵의 ‘지난 로드맵’으로 옮겨요. 확인하기 전에는 사후 점검을 다시 작성해 새 보고서를 만들 수 있고, 확인한
          뒤에는 읽기 전용이라 다시 점검하려면 새 로드맵에서 시작해요.
          {R && R.status === 'active' ? (
            <>
              {' '}
              <button className="link" onClick={() => go(paths.post(R.id))}>
                사후 점검 다시 작성하기
              </button>
            </>
          ) : null}
        </Note>
      )}
    </Page>
  );
}

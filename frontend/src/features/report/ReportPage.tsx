import { trackName } from '@/shared/constants/data';
/* 결과 보고서 (5차 scr.report) — 사후 점검 완료 시 보고서 생성과 함께 로드맵이 완료된다 */
import { useParams } from 'react-router';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { useMe } from '@/shared/state/session';
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
  return (
    <Page
      back={paths.checks}
      eyebrow={`결과 보고서 · ${trackName(r.opt)} v${r.version} · ${r.createdAt}`}
      title="학습 결과 보고서"
      lead={r.goal}
      foot={
        R ? (
          <button className="btn line" onClick={() => go(paths.roadmap(R.id))}>
            로드맵 보기
          </button>
        ) : undefined
      }
    >
      <ReportBody r={r} />
      <ReportDeep r={r} R={R} />
      {sup ? <Note>이 보고서는 내 계획을 보는 부서장 {sup.name} 님도 볼 수 있어요.</Note> : null}
    </Page>
  );
}

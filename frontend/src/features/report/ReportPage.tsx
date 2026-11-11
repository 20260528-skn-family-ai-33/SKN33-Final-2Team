import { ApiError } from '@/api/client';
import { useQuery } from '@tanstack/react-query';
import { plansApi } from '@/api/endpoints/plans';
import { trackName } from '@/shared/constants/data';
import { useParams } from 'react-router';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { useMe } from '@/shared/state/session';
import { useWs } from '@/shared/state/workspace';
import { Loading, Note, Page } from '@/shared/ui/parts';
import { ReportBody, ReportDeep } from './ReportBody';
import { MemberReportTasks } from './ReportTasks';

export function ReportPage() {
  const { rid } = useParams();
  const go = useGo();
  const me = useMe();
  const cached = useWs((s) => s.reports.find((x) => x.id === rid) || null);
  const lookup = useQuery({
    queryKey: ['report-lookup', me?.id, rid],
    enabled: !!me && !!rid && !cached,
    queryFn: () => plansApi.report(rid!),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
  const r = cached ?? lookup.data;
  const R = useWs((s) => (r ? s.plans[r.planId] : undefined));
  if (!r && lookup.isFetching) return <Page back={paths.checks} title="결과 보고서"><Loading text="보고서를 불러오는 중…" /></Page>;
  if (!r && lookup.isError && !(lookup.error instanceof ApiError && lookup.error.status === 404)) return <Page back={paths.checks} title="보고서를 불러오지 못했어요">
    <button className="btn line" onClick={() => void lookup.refetch()}>보고서 다시 불러오기</button>
  </Page>;
  if (!r) return <Page back={paths.checks} title="결과 보고서가 없어요" />;
  const sup = me?.mySupervisor;
  return (
    <Page
      back={paths.checks}
      eyebrow={`결과 보고서 · ${trackName(r.opt)} v${r.version} · ${r.createdAt}`}
      title="학습 결과 보고서"
      lead={r.goal}
      foot={R ? <button className="btn line" onClick={() => go(paths.roadmap(R.id))}>로드맵 보기</button> : undefined}
    >
      <MemberReportTasks planId={r.planId} />
      <ReportBody r={r} R={R} />
      <ReportDeep r={r} R={R} />
      {sup ? <Note>이 보고서는 내 계획을 보는 부서장 {sup.name} 님도 볼 수 있어요.</Note> : null}
    </Page>
  );
}

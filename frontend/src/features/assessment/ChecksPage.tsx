/* 점검·보고서 (5차 scr.checks) — 진행 중인 로드맵의 사후 점검 시작 · 사전 점검 응답 · 결과 보고서 기록 */
import { paths } from '@/app/paths';
import { NoPlan, openPreAnswers, postStart } from '@/features/roadmap/parts';
import { useGo } from '@/shared/hooks/useGo';
import { count } from '@/shared/lib/plan';
import { useMe } from '@/shared/state/session';
import { recs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Page } from '@/shared/ui/parts';

export function ChecksPage() {
  const go = useGo();
  const me = useMe();
  const plans = useWs((s) => s.plans);
  const reports = useWs((s) => s.reports);
  const all = recs({ plans });
  const act = recs({ plans }, 'active');
  if (!all.length && !reports.length)
    return (
      <Page title="점검·보고서">
        <NoPlan />
      </Page>
    );
  const sup = me?.mySupervisor;
  return (
    <Page
      title="점검·보고서"
      lead={sup ? `점검 응답은 나만 봐요. 결과 보고서는 내 계획을 보는 부서장 ${sup.name} 님도 볼 수 있어요.` : undefined}
    >
      {act.length ? (
        <div className="card acc">
          <h2 className="st">로드맵을 마쳤나요?</h2>
          <p className="muted">사전 점검과 같은 문항에 다시 답하면 진단 에이전트가 결과 보고서를 만들어 드려요. 활동이 남아 있어도 시작할 수 있어요.</p>
          <div className="list ck-list">
            {act.map((R) => {
              const c = count(R.plan, R.progress);
              return (
                <div className="li" key={R.id}>
                  <span className="idx">
                    <Icon name="map" />
                  </span>
                  <div className="tx">
                    <b>{R.plan.goal}</b>
                    <small>
                      {R.plan.name} v{R.plan.version} · 활동 {c.done}/{c.t} 완료
                    </small>
                  </div>
                  <button className={`btn ${c.done === c.t ? 'pri' : 'line'} sm`} onClick={() => postStart(go, R.id)}>
                    사후 점검
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      <div className="sec">
        <div className="sec-h">
          <h2 className="st">기록</h2>
        </div>
        <div className="list">
          {all.map((R) => (
            <button className="li" key={R.id} onClick={() => openPreAnswers(R.id)}>
              <span className="idx">
                <Icon name="file" />
              </span>
              <div className="tx">
                <b>사전 점검 응답 · {R.plan.name}</b>
                <small>
                  {R.plan.goal} · {R.createdAt} · {R.plan.assess?.questions.length || 0}문항
                </small>
              </div>
              <span className="end">
                {R.status !== 'active' ? <span className="tag line">{R.status === 'done' ? '마침' : '보관'}</span> : null}
                <Icon name="right" />
              </span>
            </button>
          ))}
          {reports.map((r) => (
            <button className="li" key={r.id} onClick={() => go(paths.report(r.id))}>
              <span className="idx">
                <Icon name="chart" />
              </span>
              <div className="tx">
                <b>
                  결과 보고서 · {r.opt} v{r.version}
                </b>
                <small>
                  {r.goal} · {r.createdAt} · {r.confirmed ? '확인함' : '확인 전'}
                </small>
              </div>
              <span className="end">
                <Icon name="right" />
              </span>
            </button>
          ))}
        </div>
      </div>
    </Page>
  );
}

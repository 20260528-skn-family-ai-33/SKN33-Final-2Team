import { trackName } from '@/shared/constants/data';
/* 점검·보고서 (5차 scr.checks) — 진행 중인 로드맵의 사후 점검 시작 · 역량 테스트 응답 · 결과 보고서 기록 */
import { paths } from '@/app/paths';
import {
  NoPlan,
  openPreAnswers,
  openPostAnswers,
  postStart,
} from '@/features/roadmap/parts';
import { MySkillMap } from '@/features/skillmap/MySkillMap';
import { useGo } from '@/shared/hooks/useGo';
import { count, isPlanComplete } from '@/shared/lib/plan';
import { useMe } from '@/shared/state/session';
import { recs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Page } from '@/shared/ui/parts';
import { useState } from 'react';
import type { PlanRecord } from '@/api/types/plan';


function isCompletedRecord(R: PlanRecord): boolean {
  return R.status === 'done' && isPlanComplete(R.plan, R.progress);
}

function sortByDateOrder(items: PlanRecord[], dateOrder: 'latest' | 'oldest'): PlanRecord[] {
  return items
    .map((R, idx) => ({ R, idx }))
    .sort((a, b) => {
      const aTime = Date.parse(a.R.createdAt || a.R.plan.confirmedAt || '');
      const bTime = Date.parse(b.R.createdAt || b.R.plan.confirmedAt || '');

      if (!Number.isFinite(aTime)) return Number.isFinite(bTime) ? 1 : 0;
      if (!Number.isFinite(bTime)) return -1;
      if (aTime !== bTime) return dateOrder === 'latest' ? bTime - aTime : aTime - bTime;

      return dateOrder === 'latest' ? b.idx - a.idx : a.idx - b.idx;
    })
    .map(({ R }) => R);
}

export function ChecksPage() {
  const go = useGo();
  const me = useMe();
  const plans = useWs((s) => s.plans);
  const reports = useWs((s) => s.reports);
  const [dateOrder, setDateOrder] = useState<'latest' | 'oldest'>('latest');

  const all = recs({ plans });
  const act = recs({ plans }, 'active');

  const completedRecords = sortByDateOrder(
    all.filter((R) => isCompletedRecord(R)),
    dateOrder,
  );
  const incompleteRecords = sortByDateOrder(
    all.filter((R) => !isCompletedRecord(R)),
    dateOrder,
  );
  const recordSections = [
    { key: 'completed', title: '완료', items: completedRecords },
    { key: 'incomplete', title: '미완료', items: incompleteRecords },
  ].filter(({ items }) => items.length > 0);
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
          <p className="muted">설문은 같은 문항에 다시 답하고, 퀴즈는 같은 개념의 다른 문항을 풀어요. 응답을 제출하면 진단 에이전트가 결과 보고서를 만들어 드려요. 활동이 남아 있어도 시작할 수 있어요.</p>
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
                      {trackName(R.plan.opt, R.plan.name)} v{R.plan.version} · 활동 {c.done}/{c.t} 완료
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
      <MySkillMap />
      {recordSections.map(({ key, title, items }, idx) => (
        <div className="sec" key={key}>
          <div className="sec-h">
            <h2 className="st">
              {title} {items.length}
            </h2>
            {idx === 0 ? (
              <select
                className="record-sort"
                aria-label="기록 날짜 정렬"
                value={dateOrder}
                onChange={(event) => setDateOrder(event.target.value === 'oldest' ? 'oldest' : 'latest')}
              >
                <option value="latest">최신순</option>
                <option value="oldest">오래된순</option>
              </select>
            ) : null}
          </div>
          <div className="check-plan-groups">
            {items.map((R) => {
              const linkedReports = reports.filter((report) => report.planId === R.id);
              const hasPostAnswers = Object.values(R.post.answers || {}).some(Boolean);
              const activity = count(R.plan, R.progress);
              const complete = isPlanComplete(R.plan, R.progress);
              const ratio = complete ? 1 : activity.done / (activity.t || 1);
              const percent = Math.round(ratio * 100);
              const hue = Math.max(0, Math.min(120, ratio * 120));
              const statusText = R.status === 'archived'
                ? '보관'
                : R.status === 'done'
                  ? complete ? '완료' : '조기 종료'
                  : '진행 중';
              const statusTone = R.status === 'done' ? (complete ? ' done' : ' early') : '';
              return (
                <section className="check-plan-group" key={R.id}>
                  <div className="check-plan-heading">
                    <h3 className="check-plan-title">
                      <button
                        type="button"
                        className="check-plan-open"
                        aria-label={`${R.plan.displayTitle || R.plan.goal} 로드맵 보기`}
                        onClick={() => go(paths.roadmap(R.id))}
                      >
                        {R.plan.displayTitle || R.plan.goal}
                      </button>
                    </h3>
                    <div className="check-plan-progress">
                      <span
                        className="check-plan-percent"
                        style={{ color: `hsl(${hue}, 75%, 30%)` }}
                        title={`활동 ${activity.done}/${activity.t} 완료`}
                      >
                        {percent}%
                      </span>
                      <span className={`roadmap-info-badge${statusTone}`}>{statusText}</span>
                    </div>
                  </div>

                  <div className="list">
                    <button
                      type="button"
                      className="li"
                      onClick={() => openPreAnswers(R.id)}
                    >
                      <span className="idx">
                        <Icon name="file" />
                      </span>
                      <div className="tx">
                        <b>역량 테스트 응답</b>
                        <small>
                          {R.createdAt} · {R.plan.assess?.questions.length || 0}문항
                        </small>
                      </div>
                      <span className="end">
                        <Icon name="right" />
                      </span>
                    </button>

                    {!hasPostAnswers ? (
                      <div className="li">
                        <span className="idx">
                          <Icon name="file" />
                        </span>

                        <div className="tx">
                          <b>사후 점검 전</b>
                          <small>아직 저장된 사후 점검 응답이 없어요.</small>
                        </div>

                        {R.status === 'active' ? (
                          <button
                            type="button"
                            className="btn line sm"
                            onClick={() => postStart(go, R.id)}
                          >
                            사후 점검
                          </button>
                        ) : null}
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="li"
                        onClick={() => openPostAnswers(R.id)}
                      >
                        <span className="idx"><Icon name="file" /></span>
                        <div className="tx">
                          <b>사후 점검 응답</b>
                          <small>
                            응답 {Object.values(R.post.answers || {}).filter(Boolean).length}
                            /{R.plan.assess?.questions.length || 0}문항
                          </small>
                        </div>
                        <span className="end"><Icon name="right" /></span>
                      </button>
                    )}

                    {linkedReports.map((report) => (
                      <button
                        type="button"
                        className="li"
                        key={report.id}
                        onClick={() => go(paths.report(report.id))}
                      >
                        <span className="idx">
                          <Icon name="chart" />
                        </span>
                        <div className="tx">
                          <b>결과 보고서</b>
                          <small>
                            {report.createdAt}
                          </small>
                        </div>
                        <span className="end">
                          <Icon name="right" />
                        </span>
                      </button>
                    ))}

                    {!linkedReports.length ? (
                      <p className="check-plan-empty">
                        아직 결과 보고서가 없어요.
                      </p>
                    ) : null}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      ))}
    </Page>
  );
}

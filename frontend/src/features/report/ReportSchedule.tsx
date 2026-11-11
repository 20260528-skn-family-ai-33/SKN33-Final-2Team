/* 결과 보고서 개요: 전체 학습·과제 일정
   막대 = 계획한 주차, 완료 여부 = 보고서를 만든 시점에 고정한 기록. 홈 일정표와 같이 완료는 채우고 나머지는 옅게 둔다.
   본인 화면에만 오는 실행 기록(executionSnapshot)과 계획의 주차가 모두 있을 때만 그린다 */
import type { CSSProperties } from 'react';
import type { Report } from '@/api/types/plan';
import { useCatalog } from '@/shared/state/catalog';
import type { Schedule } from './overview';
import './comparisonViz.css';
import './reportOverview.css';

type Snapshot = NonNullable<Report['executionSnapshot']>;

export function ReportSchedule({ schedule, snapshot }: { schedule: Schedule; snapshot: Snapshot }) {
  const resources = useCatalog((state) => state.res);
  const weeks = Array.from({ length: schedule.weeks }, (_, index) => index + 1);
  const done = schedule.rows.filter((row) => row.done).length;
  const columns = { '--n': schedule.weeks } as CSSProperties;
  return (
    <section className="card rpt-viz rpt-schedule" aria-label="전체 학습·과제 일정">
      <div className="rpt-card-head">
        <h2 className="st">전체 학습·과제 일정</h2>
        <span className="rpt-card-meta">
          {snapshot.early ? '조기 종료' : '학습 종료'} 기준 · {new Date(snapshot.asOf).toLocaleString('ko-KR')}
        </span>
      </div>
      <p className="rpt-card-sub">막대는 계획한 기간이에요. 완료 여부는 이 시점까지 저장된 기록 기준이고, 첨부 내용은 검증하지 않았어요.</p>
      <div className="rpt-gantt">
        <div className="rpt-gantt-head" aria-hidden="true">
          <span>활동</span>
          <span className="rpt-gantt-weeks" style={columns}>
            {weeks.map((week) => (
              <span key={week}>{schedule.weeks > 8 ? week : `${week}주`}</span>
            ))}
          </span>
          <span>상태</span>
        </div>
        <ul className="rpt-gantt-rows">
          {schedule.rows.map((row) => (
            <li className="rpt-gantt-row" key={row.key}>
              <span className="rpt-gantt-label">
                <small>{row.task ? '과제' : (row.res && resources[row.res]?.kind) || '자료'}</small>
                <span className="rpt-gantt-title" title={row.title}>
                  {row.title}
                </span>
              </span>
              <span className="rpt-gantt-weeks" style={columns} role="img" aria-label={`${row.from === row.to ? row.from : `${row.from}~${row.to}`}주차`}>
                {weeks.map((week) => (
                  <i key={week} className={week >= row.from && week <= row.to ? (row.done ? 'on done' : 'on') : undefined} />
                ))}
              </span>
              <span className={`rpt-gantt-state${row.done ? ' done' : ''}`}>{row.done ? '완료' : '미완료'}</span>
            </li>
          ))}
        </ul>
      </div>
      <ul className="cmp-legend rpt-gantt-key">
        <li>
          <i className="rpt-gantt-swatch done" aria-hidden="true" />
          완료한 활동 <b>{done}</b>
        </li>
        <li>
          <i className="rpt-gantt-swatch" aria-hidden="true" />
          완료하지 않은 활동 <b>{schedule.rows.length - done}</b>
        </li>
      </ul>
    </section>
  );
}

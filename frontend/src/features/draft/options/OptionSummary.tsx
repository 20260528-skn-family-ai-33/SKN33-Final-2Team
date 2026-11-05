import './optionSummary.css';
import { optionSummary } from '@/shared/lib/planDescription';
import type { CrashCore } from './crashCore';

const short = (value: string, expanded: boolean, limit = 32) => expanded ? value : value.slice(0, limit).trimEnd();

export function OptionSummary({ reason, pros, expanded, id, core }: { reason?: string; pros: string[]; expanded: boolean; id: string; core?: CrashCore | null }) {
  const { text, benefits } = optionSummary(reason, pros);
  return <div id={id} className="course-explanation small">
    <span className="course-explanation-label muted">추천 이유</span>
    <div className="course-reason"><span id={`${id}-reason`}>{expanded ? text : text.slice(0, 48).trimEnd()}</span></div>
    <div className="course-benefits"><span className="course-explanation-label muted">장점</span>
      <ul id={`${id}-pros`}>{(expanded ? benefits : benefits.slice(0, 2)).map((value, index) => <li key={index}>{expanded ? value : value.slice(0, 32).trimEnd()}</li>)}</ul>
    </div>
    {core ? <div className="course-core">
      <span className="course-explanation-label muted">핵심 결과물</span>
      <ul id={`${id}-core`}>{(expanded ? core.rows : core.rows.slice(0, 2)).map(row => <li key={row.name}>
        <b>{row.name}</b> {short(row.outcome, expanded)}
        {expanded ? <ul className="course-core-criteria">{row.criteria.map((value, index) => <li key={index}>{value}</li>)}</ul> : null}
      </li>)}</ul>
      {core.followUp.length ? <>
        <span className="course-explanation-label muted">후속 학습</span>
        <ul id={`${id}-follow-up`}>{(expanded ? core.followUp : core.followUp.slice(0, 2)).map((value, index) => <li key={index}>{short(value, expanded)}</li>)}</ul>
      </> : null}
    </div> : null}
  </div>;
}

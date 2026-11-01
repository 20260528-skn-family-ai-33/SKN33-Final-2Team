import './optionSummary.css';

export function OptionSummary({ reason, pros, expanded, id }: { reason?: string; pros: string[]; expanded: boolean; id: string }) {
  const text = (reason || '').trim();
  return <div id={id} className="course-explanation small">
    <span className="course-explanation-label muted">추천 이유</span>
    <div className="course-reason"><span id={`${id}-reason`}>{expanded ? text : text.slice(0, 48).trimEnd()}</span></div>
    <div className="course-benefits"><span className="course-explanation-label muted">장점</span>
      <ul id={`${id}-pros`}>{(expanded ? pros : pros.slice(0, 2)).map((value, index) => <li key={index}>{expanded ? value : value.slice(0, 32).trimEnd()}</li>)}</ul>
    </div>

  </div>;
}

/* 설문 사전·사후 응답을 1~5 눈금 위의 두 점으로 보여 준다 (#116)
   빈 원 = 사전, 채운 원 = 사후. 값이 같으면 원 안에 점이 들어간다. 응답이 없으면 그 점을 그리지 않는다 */
import { SURVEY_CHOICES, type Change, type SurveyComparison, type SurveyItem } from './comparison';
import './comparisonViz.css';

const RATINGS = [1, 2, 3, 4, 5];
const CHANGE_TEXT: Record<Change, string> = { up: '높아짐', same: '같음', down: '낮아짐', unknown: '' };
/** 눈금 위치: 너비 170 을 다섯 칸으로 나눈 칸 가운데(위쪽 숫자 줄과 맞춘다) */
const x = (rating: number) => 17 + 34 * (rating - 1);

function Track({ item }: { item: SurveyItem }) {
  const { pre, post } = item;
  const same = pre !== null && pre === post;
  return (
    <svg className="cmp-track" viewBox="0 0 170 24" width="170" height="24" aria-hidden="true" focusable="false">
      <line className="cmp-track-axis" x1={x(1)} y1="12" x2={x(5)} y2="12" />
      {RATINGS.map((rating) => (
        <circle key={rating} className="cmp-track-tick" cx={x(rating)} cy="12" r="2" />
      ))}
      {pre !== null && post !== null && !same ? <line className="cmp-track-link" x1={x(pre)} y1="12" x2={x(post)} y2="12" /> : null}
      {pre !== null ? <circle className="cmp-track-pre" cx={x(pre)} cy="12" r={same ? 8 : 6} /> : null}
      {post !== null ? <circle className="cmp-track-post" cx={x(post)} cy="12" r={same ? 4 : 6} /> : null}
    </svg>
  );
}

const spoken = (label: string, rating: number | null) => (rating === null ? `${label} 응답 없음` : `${label} ${rating} ${SURVEY_CHOICES[rating - 1]}`);

function Row({ item }: { item: SurveyItem }) {
  const missing = item.pre === null && item.post === null ? '응답 없음' : item.pre === null ? '사전 없음' : item.post === null ? '사후 없음' : '';
  const label = [spoken('사전', item.pre), spoken('사후', item.post), CHANGE_TEXT[item.change]].filter(Boolean).join(', ');
  return (
    <li className="cmp-dumbbell-row">
      <span className="cmp-dumbbell-text">{item.text}</span>
      <span className="cmp-dumbbell-mark" role="img" aria-label={label}>
        <Track item={item} />
        <span className="cmp-dumbbell-value">
          <b>
            {item.pre ?? '–'} → {item.post ?? '–'}
          </b>{' '}
          {missing || CHANGE_TEXT[item.change]}
        </span>
      </span>
    </li>
  );
}

export function SurveyDumbbell({ survey }: { survey: SurveyComparison }) {
  const groups: { skill: string; items: SurveyItem[] }[] = [];
  for (const item of survey.items) {
    const last = groups[groups.length - 1];
    if (last && last.skill === item.skill) last.items.push(item);
    else groups.push({ skill: item.skill, items: [item] });
  }
  return (
    <div className="cmp-dumbbell">
      <div className="cmp-dumbbell-scale" aria-hidden="true">
        <span />
        <span className="cmp-dumbbell-mark">
          <span className="cmp-scale-ticks">
            {RATINGS.map((rating) => (
              <span key={rating}>{rating}</span>
            ))}
          </span>
          <span />
        </span>
      </div>
      {groups.map((group, index) => (
        <section key={index} aria-label={group.skill}>
          <h3 className="cmp-dumbbell-skill">{group.skill}</h3>
          <ul className="cmp-dumbbell-list">
            {group.items.map((item) => (
              <Row key={item.id} item={item} />
            ))}
          </ul>
        </section>
      ))}
      <ul className="cmp-legend">
        <li>
          <span className="cmp-legend-ring" aria-hidden="true" />
          사전
        </li>
        <li>
          <span className="cmp-legend-dot" aria-hidden="true" />
          사후
        </li>
        <li>
          <small>
            1 {SURVEY_CHOICES[0]} ~ 5 {SURVEY_CHOICES[4]}
          </small>
        </li>
      </ul>
    </div>
  );
}

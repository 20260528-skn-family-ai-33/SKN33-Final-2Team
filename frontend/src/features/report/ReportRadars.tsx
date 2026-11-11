/* 결과 보고서 개요: 스킬별 사전·사후를 레이더로 겹쳐 보여 주는 카드 두 장
   - 사전 = 점선·빈 원, 사후 = 실선·채운 원(색을 못 봐도 구분된다). 값은 축 이름 아래에 글자로도 적는다
   - 스킬이 3개보다 적으면 레이더가 선이 되므로 그 카드는 그리지 않는다(보고서 전체가 2개 이하면 ReportBody 가 이전 구성을 쓴다)
   - 본인 보고서에만 오는 근거로 그린다. 근거가 없는 이전 보고서와 부서장 화면에서는 아무것도 그리지 않는다 */
import type { Report } from '@/api/types/plan';
import { quizComparison, surveyComparison } from './comparison';
import { quizBySkill, quizRingCount, quizStepCount, surveyBySkill, type SkillValue } from './overview';
import './comparisonViz.css';
import './reportOverview.css';

const RADIUS = 92;
/** 맨 위 축 이름표(두 줄)가 들어갈 높이 */
const TOP_ROOM = 56;
/** 아래쪽 축 이름표가 들어갈 높이 */
const BOTTOM_ROOM = 64;
const fix = (value: number) => Math.round(value * 10) / 10;

type Phase = 'pre' | 'post';
const PHASE_TEXT: Record<Phase, string> = { pre: '사전', post: '사후' };

/** 축 방향: 12시부터 시계 방향 */
function direction(index: number, count: number) {
  const angle = -Math.PI / 2 + (2 * Math.PI * index) / count;
  return { cos: Math.cos(angle), sin: Math.sin(angle) };
}
/** 옆으로 뻗은 축: 이름표를 꼭짓점 위아래가 아니라 바깥 옆에 둔다 */
const isSide = (sin: number) => Math.abs(sin) <= 0.35;

/** 축 수에 맞춘 그림 크기. 옆으로 뻗은 축이 있으면 이름표 자리만큼 넓히고, 맨 아래 꼭짓점에 맞춰 높이를 정한다 */
function frame(count: number) {
  const directions = Array.from({ length: count }, (_, index) => direction(index, count));
  const width = directions.some((d) => isSide(d.sin)) ? 384 : 320;
  const centerY = TOP_ROOM + RADIUS;
  const height = Math.round(centerY + RADIUS * Math.max(...directions.map((d) => d.sin)) + BOTTOM_ROOM);
  const at = (index: number, value = 1) => ({ x: width / 2 + RADIUS * value * directions[index].cos, y: centerY + RADIUS * value * directions[index].sin });
  const points = (valueAt: (index: number) => number) =>
    directions
      .map((_, index) => {
        const point = at(index, valueAt(index));
        return `${fix(point.x)},${fix(point.y)}`;
      })
      .join(' ');
  /** 이름표 자리: 위·아래 축은 꼭짓점 위아래(가운데에서 벗어난 축은 바깥쪽으로 조금 밀어 서로 겹치지 않게), 옆 축은 바깥 옆 */
  const label = (index: number) => {
    const { cos, sin } = directions[index];
    const tip = at(index);
    const side = isSide(sin);
    const place = side ? (cos > 0 ? 'right' : 'left') : `${sin < 0 ? 'above' : 'below'}${Math.abs(cos) > 0.2 ? (cos > 0 ? ' out-right' : ' out-left') : ''}`;
    const x = side ? tip.x + 10 * Math.sign(cos) : tip.x;
    const y = side ? tip.y : tip.y + 8 * Math.sign(sin);
    return { place, style: { left: `${fix((x / width) * 100)}%`, top: `${fix((y / height) * 100)}%` } };
  };
  return { width, height, centerX: width / 2, centerY, at, points, label };
}

function Radar({ axes, rings }: { axes: SkillValue[]; rings: number }) {
  const { width, height, centerX, centerY, at, points, label } = frame(axes.length);
  return (
    <div className="rpt-radar" style={{ aspectRatio: `${width} / ${height}`, maxWidth: Math.round(width * 1.15) }}>
      <svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {Array.from({ length: rings }, (_, ring) => (
          <polygon key={ring} className={`rpt-radar-ring${ring === rings - 1 ? ' outer' : ''}`} points={points(() => (ring + 1) / rings)} />
        ))}
        {axes.map((axis, index) => {
          const tip = at(index);
          return <line key={axis.skill} className="rpt-radar-axis" x1={centerX} y1={centerY} x2={fix(tip.x)} y2={fix(tip.y)} />;
        })}
        {(['pre', 'post'] as const).map((phase) =>
          // 값이 없는 축이 있으면 0으로 이어 그리지 않고 점만 찍는다
          axes.every((axis) => axis[phase] !== null) ? <polygon key={phase} className={`rpt-radar-area ${phase}`} points={points((index) => axes[index][phase] ?? 0)} /> : null,
        )}
        {(['pre', 'post'] as const).map((phase) =>
          axes.map((axis, index) => {
            const value = axis[phase];
            if (value === null) return null;
            const point = at(index, value);
            return (
              <circle key={`${phase}:${axis.skill}`} className={`rpt-radar-mark ${phase}`} cx={fix(point.x)} cy={fix(point.y)} r={phase === 'pre' ? 5 : 4}>
                <title>{`${axis.skill}: ${PHASE_TEXT[phase]} ${axis[`${phase}Text`]}`}</title>
              </circle>
            );
          }),
        )}
      </svg>
      {axes.map((axis, index) => {
        const { place, style } = label(index);
        return (
          <span key={axis.skill} className={`rpt-radar-label ${place}`} style={style} title={axis.skill}>
            <span className="rpt-radar-name">{axis.skill}</span>
            <span className="rpt-radar-value">
              {axis.preText} → <b>{axis.postText}</b>
            </span>
          </span>
        );
      })}
    </div>
  );
}

function PhaseKey({ phase }: { phase: Phase }) {
  return (
    <svg className="rpt-key-line" viewBox="0 0 30 12" width="30" height="12" aria-hidden="true">
      <line className={`rpt-radar-area ${phase}`} x1="1" y1="6" x2="29" y2="6" />
      <circle className={`rpt-radar-mark ${phase}`} cx="15" cy="6" r={phase === 'pre' ? 4.5 : 4} />
    </svg>
  );
}

const spoken = (text: string) => (text === '–' ? '없음' : text);

function SkillCard({ title, sub, axes, rings, unit, children }: { title: string; sub: string; axes: SkillValue[]; rings: number; unit: string; children: React.ReactNode }) {
  const label = `${title}: ${axes.map((axis) => `${axis.skill} 사전 ${spoken(axis.preText)}, 사후 ${spoken(axis.postText)}`).join(' · ')}`;
  if (axes.length < 3) return null;
  return (
    <section className="card rpt-viz rpt-skill-card" aria-label={title}>
      <h2 className="st">{title}</h2>
      <p className="rpt-card-sub">{sub}</p>
      <div className="rpt-skill-chart" role="img" aria-label={label}>
        <Radar axes={axes} rings={rings} />
      </div>
      <ul className="cmp-legend rpt-skill-key">
        <li>
          <PhaseKey phase="pre" />
          사전
        </li>
        <li>
          <PhaseKey phase="post" />
          사후
        </li>
        <li>
          <small>눈금 한 칸 = {unit}</small>
        </li>
      </ul>
      <p className="rpt-card-foot">{children}</p>
    </section>
  );
}

export function ReportRadars({ r }: { r: Report }) {
  const survey = r.surveyEvidence?.length ? surveyComparison(r.surveyEvidence) : null;
  const quiz = r.quizEvidence?.length ? quizComparison(r.quizEvidence) : null;
  if (!survey && !quiz) return null;
  return (
    <div className="rpt-pair">
      {survey ? (
        <SkillCard title="설문 응답 결과" sub="같은 문항의 자기보고 응답(1~5점) · 스킬별 문항 평균" axes={surveyBySkill(survey)} rings={5} unit="1점">
          {survey.compared > 0 ? (
            <>
              같은 문항 {survey.compared}개 중 높아짐 <b>{survey.counts.up}</b> · 같음 <b>{survey.counts.same}</b> · 낮아짐 <b>{survey.counts.down}</b>
              {survey.counts.unknown > 0 ? ` · 응답이 없는 ${survey.counts.unknown}문항은 빼고 셌어요` : ''}
            </>
          ) : (
            '사전·사후 응답이 모두 있는 문항이 없어 변화는 세지 않았어요.'
          )}
        </SkillCard>
      ) : null}
      {quiz ? (
        <SkillCard title="학습 점검 결과" sub="스킬별 퀴즈 정답 수 · 사전·사후는 같은 개념의 다른 문제" axes={quizBySkill(quiz)} rings={quizRingCount(quiz)} unit={quizStepCount(quiz) ? '1문항 · 가장 안쪽 = 0문항' : '정답률 약 33% · 가장 안쪽 = 0%'}>
          전체 정답 사전{' '}
          {quiz.pre.graded ? (
            <b>
              {quiz.pre.correct} / {quiz.pre.graded}
            </b>
          ) : (
            '채점 근거 없음'
          )}{' '}
          → 사후{' '}
          {quiz.post.graded ? (
            <b>
              {quiz.post.correct} / {quiz.post.graded}
            </b>
          ) : (
            '채점 근거 없음'
          )}
          {quiz.ungraded > 0 ? ` · 채점 근거가 없는 ${quiz.ungraded}문항은 빼고 셌어요` : ''}
        </SkillCard>
      ) : null}
    </div>
  );
}

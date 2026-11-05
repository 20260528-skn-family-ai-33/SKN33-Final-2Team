/* AI 답변을 기다리는 동안 들어올 내용의 자리를 미리 그리는 뼈대(스켈레톤 · 시험 적용).
   진행 안내 문구(role="status")는 그대로 두고 그 옆에 붙인다. 뼈대는 꾸밈이라 스크린리더에서 숨긴다.
   모양은 들어올 내용과 비슷하게만 고른다: 후보 카드(cards) · 순서 목록(rows) · 문항(quiz) · 자료 카드(grid) · 코스 비교(columns) · 글 줄(lines) */
import './skeleton.css';

export type SkeletonKind = 'cards' | 'rows' | 'quiz' | 'grid' | 'columns' | 'lines';

/* 줄 길이가 모두 같으면 글처럼 보이지 않아 순서대로 돌려 쓴다 */
const W = ['72%', '58%', '84%', '64%', '76%'];
const w = (i: number) => W[i % W.length];

const Bar = ({ width, cls = '' }: { width?: string; cls?: string }) => <span className={`skel ${cls}`} style={width ? { width } : undefined} />;

const Card = ({ i }: { i: number }) => (
  <div className="skel-card">
    <Bar cls="skel-title" width={w(i)} />
    <Bar width={w(i + 2)} />
  </div>
);

const Row = ({ i }: { i: number }) => (
  <div className="skel-card skel-row">
    <Bar cls="skel-dot" />
    <div className="skel-stack">
      <Bar cls="skel-title" width={w(i + 1)} />
      <Bar width={w(i + 3)} />
    </div>
    <Bar cls="skel-btn" />
  </div>
);

const Quiz = () => (
  <div className="skel-card">
    <Bar cls="skel-title" width="68%" />
    <Bar width="42%" />
    <div className="skel-choices">
      {[0, 1, 2, 3].map((i) => <Bar key={i} cls="skel-choice" />)}
    </div>
  </div>
);

const Res = ({ i }: { i: number }) => (
  <div className="skel-card">
    <Bar cls="skel-thumb" />
    <Bar cls="skel-title" width={w(i)} />
    <Bar width={w(i + 2)} />
  </div>
);

const Column = ({ i }: { i: number }) => (
  <div className="skel-card skel-column">
    <Bar cls="skel-title" width={w(i + 1)} />
    <Bar width="38%" />
    {[0, 1, 2].map((k) => (
      <div className="skel-block" key={k}>
        <Bar cls="skel-title" width={w(i + k)} />
        <Bar width={w(i + k + 2)} />
      </div>
    ))}
  </div>
);

export function Skeleton({ kind, count = 3 }: { kind: SkeletonKind; count?: number }) {
  const n = Array.from({ length: kind === 'quiz' ? 1 : count }, (_, i) => i);
  return (
    <div className={`skel-wrap skel-${kind}`} style={kind === 'columns' ? { gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` } : undefined} aria-hidden="true">
      {n.map((i) =>
        kind === 'cards' ? <Card key={i} i={i} /> : kind === 'rows' ? <Row key={i} i={i} /> : kind === 'quiz' ? <Quiz key={i} /> : kind === 'grid' ? <Res key={i} i={i} /> : kind === 'lines' ? <Bar key={i} width={w(i)} /> : <Column key={i} i={i} />,
      )}
    </div>
  );
}

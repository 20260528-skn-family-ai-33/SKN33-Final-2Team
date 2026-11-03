/* 홈 '나의 학습 공간' — 자주 가는 세 곳(내 로드맵 · 학습 자료 · 점검·보고서)으로 가는 그림 카드.
   그림은 CSS 배경으로 넣어 화면 테마(skins/<id>/skin.css)가 카드마다 자기 그림으로 바꿀 수 있게 한다(learningSpace.css 설명) */
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { Icon } from '@/shared/ui/Icon';
import './learningSpace.css';

const CARDS = [
  { to: paths.roadmaps, title: '나의 로드맵', desc: '목표부터 실행까지, 나의 성장 여정을 한눈에.', go: '로드맵 살펴보기' },
  { to: paths.resources, title: '학습 자료 탐색', desc: '새로운 역량을 채워 줄 강좌와 도서를 만나세요.', go: '자료 둘러보기' },
  { to: paths.checks, title: '성장 돌아보기', desc: '점검과 보고서로 쌓여 가는 변화를 확인해요.', go: '점검·보고서 보기' },
];

export function LearningSpace() {
  const go = useGo();
  return (
    <section className="ls" aria-labelledby="lsTitle">
      <div className="ls-top">
        <h2 className="ls-t" id="lsTitle">
          나의 학습 공간
        </h2>
        <span className="ls-sub">오늘도 한 걸음 더</span>
      </div>
      <div className="ls-grid">
        {CARDS.map((c, i) => (
          <a
            key={c.to}
            className="ls-card"
            href={c.to}
            onClick={(e) => {
              e.preventDefault();
              go(c.to);
            }}
          >
            <div className="ls-h">
              <h3>{c.title}</h3>
              <span className="ls-no">{String(i + 1).padStart(2, '0')}</span>
            </div>
            <p className="ls-d">{c.desc}</p>
            <span className="ls-art" aria-hidden="true" />
            <span className="ls-go">
              {c.go}
              <Icon name="arrow" />
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}

/* 내 스킬 지도: 확정한 로드맵이 없는 직원에게도 지도를 그린다(내 정보 화면에서 빈 채로 사라지지 않게).
   뱃지는 학습 기록으로만 주고, 내 정보의 보유 스킬은 골드로 치지 않는다(#213) */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Account } from '@/api/types/account';
import type { SkillMapData } from '@/api/types/catalog';
import type { PlanRecord, Report } from '@/api/types/plan';
import { useSession } from '@/shared/state/session';
import { useWs } from '@/shared/state/workspace';
import { MySkillMap } from './MySkillMap';

// 서버 렌더링에서 zustand 훅은 초기 상태를 읽으므로, 테스트가 넣어 둔 상태를 읽도록 바꾼다
vi.mock('@/shared/state/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/state/workspace')>();
  const read = (selector: Parameters<typeof actual.useWs>[0]) => selector(actual.useWs.getState());
  return { ...actual, useWs: Object.assign(read, actual.useWs) };
});
vi.mock('@/shared/state/session', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/state/session')>();
  return { ...actual, useMe: () => actual.meOf(actual.useSession.getState().account) };
});
// 글자 폭은 브라우저 캔버스로 재므로 테스트에서는 글자 수로 대신한다
vi.mock('./layout', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./layout')>();
  return { ...actual, canvasMeasure: () => (text: string, size: number) => text.length * size * 0.6 };
});

const data: SkillMapData = {
  skills: [
    { id: 1, name: 'SQL', category: '데이터', resources: 4 },
    { id: 2, name: 'SQL 튜닝', category: '데이터', resources: 4 },
  ],
  prerequisites: [[1, 2]],
  unmatched: [],
  prerequisiteSource: 'draft',
};

function render() {
  const client = new QueryClient();
  client.setQueryData(['skills-map'], data);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MySkillMap />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** 내 정보에 두 스킬을 모두 보유 스킬로 등록한 직원 */
const ownsBoth = () =>
  useSession.setState({
    account: { accountType: 'employee', user: { tech: ['SQL / 2026-05-01~2026-10-28 / 조인 쿼리 점검', 'SQL 튜닝'], certs: [] } } as unknown as Account,
  });
type Act = { id: string; skill: string };
const rec = (id: string, status: string, acts: Act[], done: string[]): PlanRecord =>
  ({ id, status, plan: { goal: `${id} 목표`, def: {}, acts }, progress: Object.fromEntries(done.map((act) => [act, { status: 'done' }])) }) as unknown as PlanRecord;
const fullQuiz = (planId: string, skill: string): Report =>
  ({ planId, quizEvidence: [0, 1, 2].map(() => ({ skill, question: '', pre: '오답', post: '정답' })) }) as unknown as Report;

describe('MySkillMap', () => {
  afterEach(() => useSession.setState({ account: null }));

  it('확정한 로드맵이 없어도 스킬을 모두 그리고 채우는 방법을 안내한다', () => {
    useWs.setState({ plans: {}, reports: [] });
    const html = render();
    expect(html).toContain('내 스킬 지도');
    expect(html.match(/class="sm-n off"/g)).toHaveLength(2);
    expect(html).toContain('로드맵을 확정하고 활동을 완료로 기록하면');
  });

  it('보유 스킬만 있고 학습 기록이 없으면 뱃지를 주지 않는다', () => {
    ownsBoth();
    useWs.setState({ plans: {}, reports: [] });
    const html = render();
    expect(html.match(/class="sm-n off"/g)).toHaveLength(2);
    expect(html).not.toContain('class="medal');
    expect(html).toContain('골드 0 · 실버 0 · 브론즈 0');
    expect(html).toContain('골드 · 사후 퀴즈 모두 정답');
    expect(html).not.toContain('보유 스킬');
  });

  it('보유 스킬이어도 뱃지는 학습 기록대로: 배우는 중이면 학습 중, 사후 퀴즈 만점이면 골드', () => {
    ownsBoth();
    const learning = rec('p1', 'active', [{ id: 'a', skill: 'SQL' }], []);
    const finished = rec('p2', 'done', [{ id: 'b', skill: 'SQL 튜닝' }], ['b']);
    useWs.setState({ plans: { p1: learning, p2: finished }, reports: [fullQuiz('p2', 'SQL 튜닝')] });
    const html = render();
    expect(html).toContain('aria-label="SQL · 학습 중"');
    expect(html).toContain('aria-label="SQL 튜닝 · 골드"');
    expect(html.match(/class="medal gold"/g)).toHaveLength(1);
    expect(html).toContain('골드 1 · 실버 0 · 브론즈 0');
  });
});

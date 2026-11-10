/* 내 스킬 지도: 확정한 로드맵이 없는 직원에게도 지도를 그린다(내 정보 화면에서 빈 채로 사라지지 않게) */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { SkillMapData } from '@/api/types/catalog';
import { useWs } from '@/shared/state/workspace';
import { MySkillMap } from './MySkillMap';

// 서버 렌더링에서 zustand 훅은 초기 상태를 읽으므로, 테스트가 넣어 둔 상태를 읽도록 바꾼다
vi.mock('@/shared/state/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/state/workspace')>();
  const read = (selector: Parameters<typeof actual.useWs>[0]) => selector(actual.useWs.getState());
  return { ...actual, useWs: Object.assign(read, actual.useWs) };
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

describe('MySkillMap', () => {
  it('확정한 로드맵이 없어도 스킬을 모두 그리고 채우는 방법을 안내한다', () => {
    useWs.setState({ plans: {}, reports: [] });
    const html = render();
    expect(html).toContain('내 스킬 지도');
    expect(html.match(/class="sm-n off"/g)).toHaveLength(2);
    expect(html).toContain('로드맵을 확정하고 활동을 완료로 기록하면');
  });
});

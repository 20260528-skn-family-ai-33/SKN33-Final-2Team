/* 도서는 진행 상태 없이 보여 주고, 홈 일정표와 스킬별 완료 수에서는 뺀다 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { Activity, PlanRecord } from '@/api/types/plan';
import { ChecksPage } from '@/features/assessment/ChecksPage';
import { GanttAll } from '@/features/home/Gantt';
import { mergeRes } from '@/shared/state/catalog';
import { useWs } from '@/shared/state/workspace';
import { ActRow } from './parts';
import { RoadmapActivityList } from './RoadmapLearning';
import { RoadmapList } from './RoadmapPages';

// 서버 렌더링에서 zustand 훅은 초기 상태를 읽으므로, 테스트가 넣어 둔 상태를 읽도록 바꾼다
vi.mock('@/shared/state/catalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/state/catalog')>();
  const read = (selector: Parameters<typeof actual.useCatalog>[0]) => selector(actual.useCatalog.getState());
  return { ...actual, useCatalog: Object.assign(read, actual.useCatalog) };
});
vi.mock('@/shared/state/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/state/workspace')>();
  const read = (selector: Parameters<typeof actual.useWs>[0]) => selector(actual.useWs.getState());
  return { ...actual, useWs: Object.assign(read, actual.useWs) };
});

const act = (id: string, skill: string, res: string | null, wFrom: number, wTo: number, title: string) =>
  ({ id, skill, res, title, task: !res, stage: 1, hours: 4, how: '', wFrom, wTo }) as Activity;

const record = (acts: Activity[], progress: PlanRecord['progress'] = {}, status: PlanRecord['status'] = 'active') =>
  ({
    id: 'plan',
    status,
    createdAt: '2026-10-26',
    progress,
    post: { answers: {} },
    plan: {
      goal: '목표',
      opt: 'A1',
      name: '기초',
      version: 1,
      weeks: 5,
      hours: 4,
      cost: 0,
      acts,
      def: {
        learningSkills: [{ name: 'SQL' }, { name: '독서' }],
        materialSchedule: [
          { skill: 'SQL', weeks: 3, startWeek: 1, endWeek: 3 },
          { skill: '독서', weeks: 1, startWeek: 4, endWeek: 4 },
        ],
      },
    },
  }) as unknown as PlanRecord;

const course = act('course', 'SQL', 'r-course', 1, 2, 'SQL 강좌');
const book = act('book', 'SQL', 'r-book', 3, 3, 'SQL 도서');
const bookOnly = act('book-only', '독서', 'r-book-2', 4, 4, '혼자 읽는 도서');
const task = act('task', 'SQL', null, 1, 3, 'SQL 과제');

beforeAll(() => {
  mergeRes({
    'r-course': { id: 'r-course', title: 'SQL 강좌', provider: '기관', kind: '강좌', type: 'course', hours: 8, cost: 0 },
    'r-book': { id: 'r-book', title: 'SQL 도서', provider: '출판사', kind: '도서', type: 'book', hours: null, cost: null },
    'r-book-2': { id: 'r-book-2', title: '혼자 읽는 도서', provider: '출판사', kind: '도서', type: 'book', hours: null, cost: null },
  });
});

// 점검·보고서의 내 스킬 지도가 스킬 자료를 불러오므로 질의 클라이언트를 함께 둔다(서버 렌더링이라 요청은 나가지 않고 불러오는 중으로 그려진다)
const inRouter = (node: React.ReactNode) =>
  renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );

describe('홈 일정표의 도서', () => {
  it('도서 줄·도서만 있는 스킬을 빼고 완료 수도 도서 없이 센다', () => {
    const html = inRouter(<GanttAll list={[record([course, book, bookOnly], { course: { status: 'done' }, book: { status: 'done' } })]} />);
    expect(html).toContain('강좌 1개');
    expect(html).not.toContain('도서');
    expect(html).not.toContain('독서');
    expect(html).toContain('활동 1개 중 1개 완료');
  });

  it('과제가 없으면 도서 주차를 뺀 강좌 구간까지만 스킬 막대를 그린다', () => {
    expect(inRouter(<GanttAll list={[record([course, book])]} />)).toContain('data-tv="1~2주차');
  });

  it('과제가 있으면 과제 주차까지 스킬 막대를 유지한다', () => {
    expect(inRouter(<GanttAll list={[record([course, book, task])]} />)).toContain('data-tv="1~3주차');
  });

  it('도서만 있는 로드맵도 진행 막대를 숫자로 계산한다', () => {
    expect(inRouter(<GanttAll list={[record([bookOnly])]} />)).not.toContain('NaN');
  });
});

describe('마친 로드맵의 완료·조기 종료 표시', () => {
  const cases: [string, PlanRecord, string, string][] = [
    ['도서만 있으면 남은 활동이 없어 완료', record([bookOnly], { 'book-only': { status: 'done' } }, 'done'), '완료', '100%'],
    ['도서 기록이 없어도 도서만 있으면 완료', record([bookOnly], {}, 'done'), '완료', '100%'],
    ['강좌를 마치면 완료', record([course], { course: { status: 'done' } }, 'done'), '완료', '100%'],
    ['강좌가 남으면 조기 종료', record([course, book], { book: { status: 'done' } }, 'done'), '조기 종료', '0%'],
    ['활동이 하나도 없으면 조기 종료', record([], {}, 'done'), '조기 종료', '0%'],
  ];
  const render = (R: PlanRecord, page: React.ReactNode) => {
    useWs.setState({ plans: { [R.id]: R }, reports: [] });
    return inRouter(page);
  };

  it.each(cases)('내 로드맵: %s', (_name, R, label) => {
    expect(render(R, <RoadmapList />)).toContain(`<span class="roadmap-info-badge">${label}</span>`);
  });

  it.each(cases)('점검·보고서: %s', (_name, R, label, percent) => {
    const html = render(R, <ChecksPage />);
    expect(html).toContain(`<span class="roadmap-info-badge">${label}</span>`);
    expect(html).toMatch(new RegExp(`class="check-plan-percent"[^>]*>${percent}<`));
  });
});

describe('로드맵 활동의 도서 상태', () => {
  it('활동 줄에 도서만 진행 상태를 표시하지 않는다', () => {
    const R = record([course, book, task], { book: { status: 'done' } });
    const bookRow = inRouter(<ActRow a={book} R={R} />);
    expect(bookRow).not.toContain('진행 중');
    expect(bookRow).not.toContain('완료');
    expect(bookRow).toContain('aria-label="SQL 도서, 실행 기록 열기"');
    expect(inRouter(<ActRow a={course} R={R} />)).toContain('미완료 · 0%');
    expect(inRouter(<ActRow a={task} R={R} />)).toContain('진행 중');
  });

  it('스킬별 완료 수에서 도서를 빼고 읽기 전용 줄에도 상태를 두지 않는다', () => {
    const html = inRouter(<RoadmapActivityList R={record([course, book, bookOnly], { course: { status: 'done' } }, 'done')} />);
    expect(html).toContain('1/1 완료');
    expect(html).not.toContain('0/1 완료');
    expect(html.match(/class="stt /g)).toHaveLength(1);
    expect(html).toContain('혼자 읽는 도서');
  });
});

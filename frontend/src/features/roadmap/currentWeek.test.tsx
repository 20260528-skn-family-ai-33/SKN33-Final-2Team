/* 이번 주 표시는 일정만 보고, 완료 여부와 따로 보여 준다(#101) */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import type { Activity, PlanRecord } from '@/api/types/plan';
import { StageCard } from '@/features/home/HomePage';
import { mergeRes, useCatalog } from '@/shared/state/catalog';
import { RoadmapActivityList } from './RoadmapLearning';
import { currentWeekSkillNames, weekToneClass } from './roadmapLearningData';

// 서버 렌더링에서 zustand 훅은 초기 상태를 읽으므로, 테스트가 넣어 둔 상태를 읽도록 바꾼다
vi.mock('@/shared/state/catalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/state/catalog')>();
  const read = (selector: Parameters<typeof actual.useCatalog>[0]) => selector(actual.useCatalog.getState());
  return { ...actual, useCatalog: Object.assign(read, actual.useCatalog) };
});

const act = (id: string, skill: string, res: string | null, wFrom: number, wTo: number) =>
  ({ id, skill, res, title: id, task: !res, stage: 1, hours: 4, how: '', wFrom, wTo }) as Activity;

// 2026-10-26 에 시작해 오늘(2026-11-02)이 2주차가 되게 둔다
const record = (acts: Activity[], progress: PlanRecord['progress'] = {}, status: PlanRecord['status'] = 'active') =>
  ({
    id: 'plan', status, createdAt: '2026-10-26', progress, post: { answers: {} },
    plan: { goal: '목표', opt: 'A1', name: '기초', version: 1, weeks: 4, hours: 4, cost: 0, acts, def: { learningSkills: [{ name: 'SQL' }, { name: 'Python' }, { name: '독서' }] } },
  }) as unknown as PlanRecord;

const sqlCourse = act('sql-course', 'SQL', 'r-course', 1, 2);
const sqlTask = act('sql-task', 'SQL', null, 2, 2);
const pastTask = act('py-task', 'Python', null, 1, 1);
const nextTask = act('py-next', 'Python', null, 3, 3);
const bookOnly = act('book-only', '독서', 'r-book', 2, 2);

beforeAll(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 10, 2, 9));
  mergeRes({
    'r-course': { id: 'r-course', title: 'SQL 강좌', provider: '기관', kind: '강좌', type: 'course', hours: 8, cost: 0 },
    'r-book': { id: 'r-book', title: '혼자 읽는 도서', provider: '출판사', kind: '도서', type: 'book', hours: null, cost: null },
  });
});
afterAll(() => vi.useRealTimers());

describe('이번 주 스킬', () => {
  const resources = () => useCatalog.getState().res;

  it('이번 주 활동을 모두 완료해도 이번 주 스킬로 남긴다', () => {
    const acts = [sqlCourse, sqlTask, pastTask];
    expect(currentWeekSkillNames(record(acts), resources())).toEqual(['SQL']);
    expect(currentWeekSkillNames(record(acts, { 'sql-course': { status: 'done' }, 'sql-task': { status: 'done' } }), resources())).toEqual(['SQL']);
  });

  it('주차 경계: 지난주에 끝난 활동과 다음 주에 시작할 활동은 넣지 않는다', () => {
    expect(currentWeekSkillNames(record([pastTask, nextTask]), resources())).toEqual([]);
    // 같은 스킬이라도 이번 주에 걸친 활동이 하나 있으면 이번 주 스킬이다
    expect(currentWeekSkillNames(record([pastTask, act('py-now', 'Python', null, 2, 3)]), resources())).toEqual(['Python']);
  });

  it('도서만 이번 주에 있는 스킬은 일정에 넣지 않으므로 표시하지 않는다', () => {
    expect(currentWeekSkillNames(record([sqlCourse, bookOnly]), resources())).toEqual(['SQL']);
  });

  it('마친 로드맵과 보관한 로드맵은 이번 주를 표시하지 않는다', () => {
    const progress = { 'sql-course': { status: 'done' as const }, 'sql-task': { status: 'done' as const } };
    expect(currentWeekSkillNames(record([sqlCourse, sqlTask], progress, 'done'), resources())).toEqual([]);
    expect(currentWeekSkillNames(record([sqlCourse, sqlTask], {}, 'archived'), resources())).toEqual([]);
  });
});

describe('스킬 카드 밖 활동 목록의 이번 주 강조', () => {
  const groupClass = (html: string, skill: string) => {
    const at = html.indexOf(`<h2>${skill}</h2>`);
    return html.slice(html.lastIndexOf('<details', at), at).match(/class="([^"]*)"/)?.[1] || '';
  };

  it('이번 주 묶음은 이번 주 색, 모두 마치면 완료색으로 바꾸고 남은 줄만 이번 주 색으로 칠한다', () => {
    const before = renderToStaticMarkup(<RoadmapActivityList R={record([sqlCourse, sqlTask])} readOnly />);
    const partial = renderToStaticMarkup(<RoadmapActivityList R={record([sqlCourse, sqlTask], { 'sql-course': { status: 'done' } })} readOnly />);
    const after = renderToStaticMarkup(<RoadmapActivityList R={record([sqlCourse, sqlTask], { 'sql-course': { status: 'done' }, 'sql-task': { status: 'done' } })} readOnly />);
    expect(groupClass(before, 'SQL')).toContain('is-current-week');
    expect(before.match(/roadmap-learning-anchor is-current-week/g)).toHaveLength(2);
    expect(groupClass(partial, 'SQL')).toContain('is-current-week');
    expect(partial.match(/roadmap-learning-anchor is-current-week/g)).toHaveLength(1);
    expect(groupClass(after, 'SQL')).toContain('is-week-done');
    expect(groupClass(after, 'SQL')).not.toContain('is-current-week');
    expect(after).toContain('2/2 완료');
    expect(after).not.toContain('roadmap-learning-anchor is-current-week');
  });

  it('지난 주차는 모두 마쳤을 때만 완료색, 남았으면 강조하지 않는다', () => {
    const left = renderToStaticMarkup(<RoadmapActivityList R={record([sqlCourse, pastTask])} readOnly />);
    expect(groupClass(left, 'SQL')).toContain('is-current-week');
    expect(groupClass(left, 'Python')).toBe('card roadmap-learning-group');
    const done = renderToStaticMarkup(<RoadmapActivityList R={record([sqlCourse, pastTask], { 'py-task': { status: 'done' } })} readOnly />);
    expect(groupClass(done, 'Python')).toContain('is-week-done');
  });
});

describe('주차 강조 클래스', () => {
  const acts = [{ id: 'a' }, { id: 'b' }];
  it('모두 마치면 이번 주 여부와 상관없이 완료, 아니면 이번 주일 때만 이번 주', () => {
    const all = { a: { status: 'done' as const }, b: { status: 'done' as const } };
    expect(weekToneClass(acts, all, true)).toBe(' is-week-done');
    expect(weekToneClass(acts, all, false)).toBe(' is-week-done');
    expect(weekToneClass(acts, { a: { status: 'done' as const } }, true)).toBe(' is-current-week');
    expect(weekToneClass(acts, { a: { status: 'done' as const } }, false)).toBe('');
    expect(weekToneClass(acts, undefined, true)).toBe(' is-current-week');
  });
  it('진행 상태를 남기는 활동이 없으면(도서만) 완료로 보지 않는다', () => {
    expect(weekToneClass([], {}, false)).toBe('');
    expect(weekToneClass([], {}, true)).toBe(' is-current-week');
  });
});

describe('홈 이번 주차 활동의 완료 강조', () => {
  const groupClass = (html: string, skill: string) => {
    const at = html.indexOf(`<h3>${skill}`);
    return html.slice(html.lastIndexOf('<section', at), at).match(/class="([^"]*)"/)?.[1] || '';
  };
  const render = (R: PlanRecord) => renderToStaticMarkup(<MemoryRouter><StageCard R={R} /></MemoryRouter>);

  it('접힌 보기에서는 이번 주 색 없이, 모든 활동을 마친 묶음만 완료색과 완료 표시를 붙인다', () => {
    const acts = [sqlCourse, sqlTask, act('py-now', 'Python', null, 2, 2)];
    const html = render(record(acts, { 'sql-course': { status: 'done' }, 'sql-task': { status: 'done' } }));
    expect(groupClass(html, 'SQL')).toBe('home-skill-group is-week-done');
    expect(groupClass(html, 'Python')).toBe('home-skill-group');
    expect(html).toContain('<span class="tag done">완료</span>');
    expect(html).not.toContain('is-current-week');
    expect(html).not.toContain('<span class="tag week">');
  });

  it('완료한 활동 줄은 이번 주 색이 아닌 완료 표시를 쓴다', () => {
    const html = render(record([sqlCourse, sqlTask], { 'sql-course': { status: 'done' } }));
    expect(html).toContain('<span class="tag done">');
    expect(html).not.toContain('tag acc');
  });
});

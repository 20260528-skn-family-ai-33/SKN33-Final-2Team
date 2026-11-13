import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReviewSkillBlocks, type ReviewMaterials } from './ReviewSkillBlocks';
import { DURATION_METHOD, type DurationEstimate } from '../result/skillOrder';

function render(courses?: string[], outcomes = ['기존 역량'], estimate: DurationEstimate = {weeks: 5}) {
  const materials: ReviewMaterials = {
    recommendations: { skills: [{ name: 'SQL', courses: [
      { id: 'one', title: '원래 강좌' }, { id: 'two', title: '추가 강좌' }], books: [] }] },
    choices: { SQL: { course: 'one', courses, books: [] } }, skillOrder: ['SQL'],
    durationEstimates: { SQL: estimate }, skillDetails: [{ name: 'SQL', application: '', competencySummary: outcomes }],
  };
  return renderToStaticMarkup(createElement(ReviewSkillBlocks, { materials, acts: [], selectedIds: [], busy: false }));
}

describe('확정한 로드맵의 이번 주·완료 표시(#101)', () => {
  const materials: ReviewMaterials = {
    recommendations: { skills: [{ name: 'SQL', courses: [{ id: 'c', title: 'SQL 강좌' }], books: [{ id: 'b', title: 'SQL 도서' }] }] },
    choices: { SQL: { course: 'c', books: ['b'] } }, skillOrder: ['SQL'],
  };
  const acts = [
    { id: 'course', title: 'SQL 강좌', skill: 'SQL', how: '', hours: 4, res: 'c' },
    { id: 'book', title: 'SQL 도서', skill: 'SQL', how: '', hours: 0, res: 'b' },
    { id: 'task', title: '쿼리 정리', skill: 'SQL', how: '', hours: 2, res: null },
  ];
  const render = (progress: Record<string, { status: 'done' | 'doing' }>, currentSkillNames: string[] = ['SQL']) =>
    renderToStaticMarkup(createElement(ReviewSkillBlocks, { materials, acts, busy: false, progress, currentSkillNames }));

  it('이번 주 스킬을 모두 마치면 이번 주 색 대신 완료색으로 바꾸고 이번 주 표시는 남긴다', () => {
    const html = render({ course: { status: 'done' }, task: { status: 'done' } });
    expect(html).toContain('rv-skill review-skill-block is-week-done"');
    expect(html).not.toContain('is-current-week');
    expect(html).toContain('<span class="tag week">이번 주</span>');
    expect(html).toContain('<span class="tag done">완료</span>');
    expect(html).toContain('rv-task is-static is-done');
  });
  it('일부만 마쳤으면 이번 주 색을 유지하고, 도서는 완료 판단에서 뺀다', () => {
    const partial = render({ course: { status: 'done' } });
    expect(partial).toContain('rv-skill review-skill-block is-current-week"');
    expect(partial).not.toContain('<span class="tag done">완료</span>');
    expect(render({ course: { status: 'done' }, task: { status: 'done' }, book: { status: 'doing' } })).toContain('is-week-done');
  });
  it('이번 주가 아니어도 모두 마친 스킬은 완료색, 남은 스킬은 강조하지 않는다', () => {
    const done = render({ course: { status: 'done' }, task: { status: 'done' } }, []);
    expect(done).toContain('is-week-done');
    expect(done).not.toContain('이번 주');
    const left = render({}, []);
    expect(left).not.toContain('is-week-done');
    expect(left).not.toContain('is-current-week');
  });
});

describe('수정 후 스킬별 자료 상세', () => {
  it('추가된 강좌도 같은 스킬의 상세에 표시한다', () => {
    const html = render(['one', 'two']);
    expect(html).toContain('원래 강좌'); expect(html).toContain('추가 강좌');
    expect(html).toContain('예상 5주');
  });
  it('구형 단일 강좌 선택은 추가 강좌를 표시하지 않는다', () => {
    const html = render();
    expect(html).toContain('원래 강좌'); expect(html).not.toContain('추가 강좌');
  });
  it('자료 변경으로 초기화한 역량을 과거 요약으로 대체하지 않는다', () => {
    const html = render(['one', 'two'], []);
    expect(html).not.toContain('기존 역량'); expect(html).toContain('역량 요약이 아직 없어요');
  });
  it('공유 강좌의 실제 구간과 추가 0주를 구분하며 미확인 시간을 표시한다', () => {
    const html = render(undefined, [], {method: DURATION_METHOD, weeks: 2, startWeek: 1, endWeek: 2, addedWeeks: 0, totalWeeks: 5, unknownCourses: ['one']});
    expect(html).toContain('1–2주차 · 시간 미확인');
    expect(html).not.toContain('예상 2주');
  });
});

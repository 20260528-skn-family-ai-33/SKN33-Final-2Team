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
    expect(html).toContain('1–2주차 · 추가 0주 · 시간 미확인');
    expect(html).not.toContain('예상 2주');
  });
});

import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { optionSummary, planDescription } from './planDescription';
import { activityTime } from './resourceTime';
import { OptionSummary } from '@/features/draft/options/OptionSummary';
import { Stats } from '@/shared/ui/parts';

describe('계산값과 AI 설명 분리', () => {
  it.each(['총 56시간 분량의 강좌로 구성했어요.', '전체 40시간짜리 강좌 묶음이에요.', '합계 30시간 강의를 골랐어요.'])('총계에는 개별 강좌 예외를 적용하지 않는다: %s', text => {
    expect(planDescription(text)).toBe('기간·비용은 현재 선택 자료 기준의 계산값을 확인해 주세요.');
  });
  it.each(['1~2주차에는 SQL 기초를 다져요.', '3일차 실습에서 API를 연결해요.', '약 2시간짜리 짧은 강좌를 골랐어요.', '약 2시간 분량의 강좌를 골랐어요.'])('개별 활동·강좌 설명은 보존한다: %s', text => {
    expect(planDescription(text)).toBe(text);
  });
  it('필터 후 더 볼 내용이 없으면 확장 버튼도 필요하지 않다', () => {
    const reason = '약 4.5주가 걸리며 총 119,900원으로 전체 과정을 마치고 프로젝트까지 완료할 수 있어요. SQL 검증에 집중해요.';
    expect(optionSummary(reason, [])).toMatchObject({text: 'SQL 검증에 집중해요.', expandable: false});
    expect(optionSummary('SQL 검증에 집중해요.', ['총 66,000원이에요. 짧아요.'])).toMatchObject({benefits: ['짧아요.'], expandable: false});
    expect(optionSummary('SQL 검증에 집중해요. '.repeat(6), []).expandable).toBe(true);
    expect(optionSummary('', ['첫째', '둘째', '셋째']).expandable).toBe(true);
  });
  it('주차·개별 강좌 설명과 한 문장에 있는 전체 합계는 여전히 제한한다', () => {
    expect(planDescription('3일차 실습 후 총 17시간이면 끝나요.')).not.toContain('17시간');
    expect(planDescription('약 2시간짜리 강좌를 들어 총 20시간으로 마쳐요.')).not.toContain('20시간');
    expect(planDescription('무료(0원) 강좌만으로 구성했어요.')).not.toContain('0원');
  });
  it.each(['약 4.5주면 마칠 수 있어요.', '8.5주로 줄였어요.', '총 119,900원이에요.', '총 17.01시간이 필요해요.', '비용은 12만원으로 잡았어요.'])('오래된 AI 합계는 현재 값으로 표시하지 않는다: %s', text => {
    expect(planDescription(text)).toBe('기간·비용은 현재 선택 자료 기준의 계산값을 확인해 주세요.');
  });
  it('편성 근거·주당 입력·수행 내용 숫자는 보존하고 저장 원문은 변경하지 않는다', () => {
    const raw = '주당 5시간을 활용해요. SQL 3개를 비교해요. 약 4.5주가 걸려요.';
    expect(planDescription(raw)).toBe('주당 5시간을 활용해요. SQL 3개를 비교해요.');
    expect(raw).toContain('4.5주');
    expect(planDescription('주 5시간 학습해요.')).toBe('주 5시간 학습해요.');
  });
  it('접힌 설명과 펼친 설명 모두 옛 합계를 노출하지 않는다', () => {
    for (const expanded of [false, true]) {
      const html = renderToStaticMarkup(createElement(OptionSummary, { id: 'summary', reason: '약 4.5주예요. SQL 검증에 집중해요.', pros: ['총 66,000원으로 마쳐요.'], expanded }));
      expect(html).not.toContain('4.5'); expect(html).not.toContain('66,000'); expect(html).toContain('SQL 검증');
    }
  });
  it('대표 기간의 상세는 강좌 시간만 표시한다', () => {
    const html = renderToStaticMarkup(createElement(Stats, { pl: { weeks: 4, hours: 5, cost: 66000, costUnknown: true, durationBasis: 'materials-only', materialHours: 18.5, taskHours: 8 } }));
    expect(html).toContain('자료 학습 예상 기간'); expect(html).toContain('강좌 시간 기준');
    expect(html).not.toContain('도서 1권 = 1주'); expect(html).toContain('18시간 30분'); expect(html).not.toContain('과제 별도');
    expect(html).toContain('66,000'); expect(html).toContain('일부 비용 확인 필요');
  });
  it('도서는 배정시간과 원래 카탈로그 참고값을 구분하고 구형 활동은 그대로 둔다', () => {
    expect(activityTime({ res: 'book', hours: 5, catalogHours: 10, hoursAllocation: 'book-week' })).toMatchObject({ text: '도서 1주 배정 · 5시간' });
    expect(activityTime({ res: 'book', hours: 5, catalogHours: 10, hoursAllocation: 'book-week' }).title).toContain('10시간');
    expect(activityTime({ res: 'book', hours: 10 }).text).toContain('계획 10시간');
  });
});

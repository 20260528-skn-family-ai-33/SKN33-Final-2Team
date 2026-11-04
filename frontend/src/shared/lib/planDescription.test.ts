import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { planDescription } from './planDescription';
import { activityTime } from './resourceTime';
import { OptionSummary } from '@/features/draft/options/OptionSummary';
import { Stats } from '@/shared/ui/parts';

describe('계산값과 AI 설명 분리', () => {
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
  it('대표 기간은 자료 기준이고 과제·도서 기준을 함께 표시한다', () => {
    const html = renderToStaticMarkup(createElement(Stats, { pl: { weeks: 4, hours: 5, cost: 66000, costUnknown: true, durationBasis: 'materials-only', materialHours: 18.5, taskHours: 8 } }));
    expect(html).toContain('자료 학습 예상 기간'); expect(html).toContain('산출물 과제 시간 제외');
    expect(html).toContain('도서 1권 = 1주'); expect(html).toContain('18시간 30분'); expect(html).toContain('8시간');
    expect(html).toContain('66,000'); expect(html).toContain('일부 비용 확인 필요');
  });
  it('도서는 배정시간과 원래 카탈로그 참고값을 구분하고 구형 활동은 그대로 둔다', () => {
    expect(activityTime({ res: 'book', hours: 5, catalogHours: 10, hoursAllocation: 'book-week' })).toMatchObject({ text: '도서 1주 배정 · 5시간' });
    expect(activityTime({ res: 'book', hours: 5, catalogHours: 10, hoursAllocation: 'book-week' }).title).toContain('10시간');
    expect(activityTime({ res: 'book', hours: 10 }).text).toContain('계획 10시간');
  });
});

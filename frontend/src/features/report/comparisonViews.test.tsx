/* 설문 덤벨이 저장된 응답을 그대로, 글자로도 보여 주는지 (#116) */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SurveyDumbbell } from './SurveyDumbbell';
import { surveyComparison } from './comparison';

const survey = (id: string, pre: string | null, post: string, skill = 'SQL') => ({ id, area: skill, skill, text: `문항 ${id}`, pre, post });
const count = (html: string, needle: string) => html.split(needle).length - 1;

describe('SurveyDumbbell', () => {
  it('문항마다 사전·사후 값을 글자로도 읽을 수 있게 그린다', () => {
    const html = renderToStaticMarkup(<SurveyDumbbell survey={surveyComparison([survey('q1', '2', '4'), survey('q2', '3', '3'), survey('q3', '4', '3', 'API')])} />);
    expect(html).toContain('사전 2 아니다, 사후 4 그렇다, 높아짐');
    expect(html).toContain('사전 3 보통이다, 사후 3 보통이다, 같음');
    expect(html).toContain('사전 4 그렇다, 사후 3 보통이다, 낮아짐');
    expect(count(html, 'cmp-dumbbell-skill')).toBe(2);
    expect(count(html, 'cmp-track-link')).toBe(2);
  });

  it('사전 응답이 없으면 사전 점을 그리지 않고 없다고 적는다', () => {
    const html = renderToStaticMarkup(<SurveyDumbbell survey={surveyComparison([survey('q1', null, '4')])} />);
    expect(html).toContain('사전 응답 없음, 사후 4 그렇다');
    expect(html).toContain('사전 없음');
    expect(count(html, 'cmp-track-pre')).toBe(0);
    expect(count(html, 'cmp-track-post')).toBe(1);
    expect(count(html, 'cmp-track-link')).toBe(0);
  });
});

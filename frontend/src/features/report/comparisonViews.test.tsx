/* 사전·사후 요약과 설문 덤벨이 저장된 근거의 수치·분모를 그대로 보여 주는지 (#116) */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { Report } from '@/api/types/plan';
import { ComparisonSummary } from './ComparisonSummary';
import { SurveyDumbbell } from './SurveyDumbbell';
import { surveyComparison } from './comparison';

const quiz = (skill: string, concept: string, pre: string, post: string) => ({ skill, concept, question: '', pre, post });
const survey = (id: string, pre: string | null, post: string, skill = 'SQL') => ({ id, area: skill, skill, text: `문항 ${id}`, pre, post });
const report = (part: Partial<Report>) => part as Report;
const count = (html: string, needle: string) => html.split(needle).length - 1;

describe('ComparisonSummary', () => {
  it('근거가 없는 이전 보고서와 부서장 화면에는 요약을 그리지 않는다', () => {
    expect(renderToStaticMarkup(<ComparisonSummary r={report({})} />)).toBe('');
    expect(renderToStaticMarkup(<ComparisonSummary r={report({ quizEvidence: [], surveyEvidence: [] })} />)).toBe('');
  });

  it('퀴즈 정답 수를 분모와 함께, 변화를 네 갈래로 보여 준다', () => {
    const html = renderToStaticMarkup(
      <ComparisonSummary
        r={report({
          quizEvidence: [
            quiz('SQL', '조인', '오답', '정답'),
            quiz('SQL', '집계', '정답', '정답'),
            quiz('SQL', '인덱스', '정답', '오답'),
            quiz('API', '오류 응답', '오답', '오답'),
            quiz('API', '인증', '오답', '정답'),
          ],
        })}
      />,
    );
    expect(html).toContain('사전 5문항 중 2개 정답, 40%');
    expect(html).toContain('사후 5문항 중 3개 정답, 60%');
    expect(html).toContain('같은 개념끼리 짝지은 5문항');
    expect(html).toContain('퀴즈 변화: 새로 맞힘 2문항, 계속 맞힘 1문항, 다시 확인 1문항, 보완 필요 1문항');
    expect(count(html, 'cmp-seg ')).toBe(4);
    expect(html).not.toContain('설문 응답 변화');
    expect(html).toContain('같은 개념의 다른 문제');
  });

  it('채점 근거가 없으면 0점·0%를 만들지 않는다', () => {
    const html = renderToStaticMarkup(<ComparisonSummary r={report({ quizEvidence: [quiz('SQL', '조인', '채점 근거 없음', '채점 근거 없음')] })} />);
    expect(count(html, '채점 근거 없음')).toBe(2);
    expect(html).not.toContain('%');
    expect(html).not.toContain('cmp-band');
    expect(html).toContain('채점 근거가 없는 1문항은 빼고 셌어요');
  });

  it('사전·사후 분모가 다르면 각자의 분모로 보여 준다', () => {
    const html = renderToStaticMarkup(<ComparisonSummary r={report({ quizEvidence: [quiz('SQL', '조인', '채점 근거 없음', '정답'), quiz('SQL', '집계', '오답', '정답')] })} />);
    expect(html).toContain('사전 1문항 중 0개 정답, 0%');
    expect(html).toContain('사후 2문항 중 2개 정답, 100%');
    expect(html).toContain('같은 개념끼리 짝지은 1문항');
  });

  it('설문은 높아짐·같음·낮아짐 문항 수를 세고 응답 없는 문항은 뺀다', () => {
    const html = renderToStaticMarkup(<ComparisonSummary r={report({ surveyEvidence: [survey('q1', '2', '4'), survey('q2', '3', '3'), survey('q3', '4', '3'), survey('q4', null, '5')] })} />);
    expect(html).toContain('같은 문항 3개의 사전 → 사후');
    expect(html).toContain('설문 변화: 높아짐 1문항, 같음 1문항, 낮아짐 1문항');
    expect(html).toContain('응답이 없는 1문항은 빼고 셌어요');
    expect(html).not.toContain('퀴즈 정답 수');
  });

  it('사전 응답이 하나도 없으면 변화 수치를 만들지 않는다', () => {
    const html = renderToStaticMarkup(<ComparisonSummary r={report({ surveyEvidence: [survey('q1', null, '4')] })} />);
    expect(html).toContain('비교하지 않았어요');
    expect(html).not.toContain('cmp-band');
    expect(html).not.toContain('높아짐');
  });
});

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

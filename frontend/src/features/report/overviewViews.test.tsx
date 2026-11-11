/* 보고서 개요 카드가 저장된 근거의 값을 그대로, 글자로도 보여 주는지 */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { Report } from '@/api/types/plan';
import { ReportRadars } from './ReportRadars';
import { ReportSchedule } from './ReportSchedule';

const quiz = (skill: string, concept: string, pre: string, post: string) => ({ skill, concept, question: '', pre, post });
const survey = (id: string, skill: string, pre: string | null, post: string) => ({ id, area: skill, skill, text: `문항 ${id}`, pre, post });
const report = (part: Partial<Report>) => part as Report;
const count = (html: string, needle: string) => html.split(needle).length - 1;

describe('ReportRadars', () => {
  it('근거가 없는 이전 보고서와 부서장 화면에는 그리지 않는다', () => {
    expect(renderToStaticMarkup(<ReportRadars r={report({})} />)).toBe('');
    expect(renderToStaticMarkup(<ReportRadars r={report({ quizEvidence: [], surveyEvidence: [] })} />)).toBe('');
  });

  it('스킬이 3개 이상이면 사전·사후를 레이더로 겹치고 값을 글자로도 적는다', () => {
    const html = renderToStaticMarkup(
      <ReportRadars
        r={report({
          surveyEvidence: [survey('q1', 'SQL', '2', '4'), survey('q2', 'API', '3', '4'), survey('q3', '테스트', '2', '3')],
          quizEvidence: [quiz('SQL', '조인', '오답', '정답'), quiz('API', '인증', '정답', '정답'), quiz('테스트', '단위', '오답', '오답')],
        })}
      />,
    );
    expect(html).toContain('설문 응답 결과: SQL 사전 2, 사후 4 · API 사전 3, 사후 4 · 테스트 사전 2, 사후 3');
    expect(html).toContain('학습 점검 결과: SQL 사전 0/1, 사후 1/1 · API 사전 1/1, 사후 1/1 · 테스트 사전 0/1, 사후 0/1');
    expect(count(html, 'rpt-radar-area pre" points')).toBe(2);
    expect(count(html, 'rpt-radar-area post" points')).toBe(2);
    expect(count(html, ': 사후 ')).toBe(6);
    expect(html).toContain('같은 문항 3개 중 높아짐 <b>3</b> · 같음 <b>0</b> · 낮아짐 <b>0</b>');
    expect(html).toContain('<b>1 / 3</b>');
    expect(html).toContain('<b>2 / 3</b>');
    expect(html).toContain('같은 개념의 다른 문제');
    expect(html).toContain('눈금 한 칸 = 1문항');
  });

  it('값이 없는 축은 0으로 이어 그리지 않고 점도 찍지 않는다', () => {
    const html = renderToStaticMarkup(<ReportRadars r={report({ surveyEvidence: [survey('q1', 'SQL', null, '4'), survey('q2', 'API', '3', '4'), survey('q3', '테스트', '2', '3')] })} />);
    expect(html).toContain('SQL 사전 없음, 사후 4');
    expect(count(html, 'rpt-radar-area pre" points')).toBe(0);
    expect(count(html, 'rpt-radar-area post" points')).toBe(1);
    expect(count(html, ': 사전 ')).toBe(2);
    expect(html).toContain('응답이 없는 1문항은 빼고 셌어요');
    expect(html).not.toContain('학습 점검 결과');
  });

  it('스킬이 3개보다 적은 근거는 카드를 그리지 않는다', () => {
    const html = renderToStaticMarkup(
      <ReportRadars
        r={report({
          surveyEvidence: [survey('q1', 'SQL', '2', '4'), survey('q2', 'API', '3', '4'), survey('q3', '테스트', '2', '3')],
          quizEvidence: [quiz('SQL', '조인', '오답', '정답'), quiz('API', '인증', '오답', '정답')],
        })}
      />,
    );
    expect(html).toContain('설문 응답 결과');
    expect(html).not.toContain('학습 점검 결과');
  });

  it('퀴즈를 하나도 못 맞힌 스킬도 중심이 아니라 첫 눈금에 점을 찍는다', () => {
    const html = renderToStaticMarkup(
      <ReportRadars r={report({ quizEvidence: [quiz('SQL', '조인', '오답', '오답'), quiz('API', '인증', '오답', '오답'), quiz('테스트', '단위', '오답', '정답')] })} />,
    );
    expect(html).toContain('SQL 사전 0/1, 사후 0/1');
    expect(html).toContain('가장 안쪽 = 0문항');
    // 축 3개 · 눈금 2개(0문항·1문항): 맨 위 축의 0문항 점은 중심(160,148)이 아니라 첫 눈금(160,102)에 있다
    expect(html).toContain('<circle class="rpt-radar-mark pre" cx="160" cy="102" r="5">');
    expect(html).not.toContain('cx="160" cy="148"');
  });
});

describe('ReportSchedule', () => {
  it('활동마다 계획한 주차만큼 칸을 채우고 완료 여부를 글자로 적는다', () => {
    const html = renderToStaticMarkup(
      <ReportSchedule
        snapshot={{ asOf: '2026-11-11T01:00:00+00:00', early: true, version: 1, activities: [] }}
        schedule={{
          weeks: 4,
          rows: [
            { key: 'a1', res: 'c1', task: false, title: 'SQL 기초 강좌', from: 1, to: 2, done: true },
            { key: 'a2', res: null, task: true, title: '조회 쿼리 과제', from: 3, to: 3, done: false },
          ],
        }}
      />,
    );
    expect(html).toContain('조기 종료 기준');
    expect(html).toContain('aria-label="1~2주차"');
    expect(html).toContain('aria-label="3주차"');
    expect(count(html, '<i class="on done">')).toBe(2);
    expect(count(html, '<i class="on">')).toBe(1);
    expect(count(html, '<i></i>')).toBe(5);
    expect(html).toContain('>완료</span>');
    expect(html).toContain('>미완료</span>');
    expect(html).toContain('<small>과제</small>');
    expect(html).toContain('<small>자료</small>');
  });
});

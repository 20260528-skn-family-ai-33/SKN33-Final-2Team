/* 보고서 구성은 같고, 스킬 수에 따라 사전·사후 자리만 갈리는지: 3개 이상은 레이더, 2개 이하는 요약 띠 */
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import type { PlanRecord, Report } from '@/api/types/plan';
import { ReportBody } from './ReportBody';

const quiz = (skill: string, pre: string, post: string) => ({ skill, concept: '개념', question: '', pre, post });
const survey = (id: string, skill: string) => ({ id, area: skill, skill, text: `문항 ${id}`, pre: '2', post: '4' });
const base = { doneTitles: ['강좌'], restTitles: [], good: ['잘된 점 내용'], improve: ['보완할 점 내용'], next: { goal: '다음 목표', why: '이유' } };
const snapshot = { asOf: '2026-11-11T01:00:00+00:00', early: false, version: 1, activities: [{ id: 'a1', title: '강좌', status: 'done', task: false }] };
const record = { plan: { version: 1, weeks: 2, acts: [{ id: 'a1', res: 'c1', wFrom: 1, wTo: 2 }] }, versions: [] } as unknown as PlanRecord;
const report = (skills: string[]) =>
  ({ ...base, executionSnapshot: snapshot, surveyEvidence: skills.map((skill, index) => survey(`q${index}`, skill)), quizEvidence: skills.map((skill) => quiz(skill, '오답', '정답')) }) as unknown as Report;

it('스킬이 3개 이상이면 일정·레이더·학습 결과 카드로 보여 준다', () => {
  const html = renderToStaticMarkup(<ReportBody r={report(['SQL', 'API', '테스트'])} R={record} />);
  expect(html).toContain('전체 학습·과제 일정');
  expect(html.split('class="rpt-radar"').length - 1).toBe(2);
  expect(html).toContain('rpt-result');
  expect(html).not.toContain('사전·사후 한눈에 보기');
  expect(html).not.toContain('미완료 활동');
});

it('스킬이 2개 이하면 도형 자리에만 요약 띠를 두고 나머지 구성은 같다', () => {
  const html = renderToStaticMarkup(<ReportBody r={report(['SQL', 'API'])} R={record} />);
  expect(html).toContain('사전·사후 한눈에 보기');
  expect(html).not.toContain('rpt-radar');
  expect(html).toContain('전체 학습·과제 일정');
  expect(html).toContain('rpt-result');
  expect(html).not.toContain('미완료 활동');
  expect(html).not.toContain('<details class="card report-survey learning-check" open');
});

it('근거가 오지 않는 부서장 화면과 이전 보고서는 실행 기록과 학습 결과 카드만 보여 준다', () => {
  const html = renderToStaticMarkup(<ReportBody r={base as unknown as Report} />);
  expect(html).toContain('미완료 활동');
  expect(html).toContain('rpt-result');
  expect(html).not.toContain('한눈에 보기');
  expect(html).not.toContain('rpt-radar');
  expect(html).not.toContain('전체 학습·과제 일정');
});

/* 에이전트 동작 보기: 길어도 자르지 않고, 모델을 바로 부른 기록도 보낸 내용·응답 전문을 보여 준다 */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { AgentLogDetail, AgentLogEntry } from '@/api/endpoints/account';
import { AgentLogBody, AgentLogList, readable } from './AgentLog';

const LONG = '가'.repeat(5000); // 이전에는 서버가 1600자에서 잘랐다
const base = { id: 1, at: '10:00:00', agent: '진단 에이전트', task: '역량 테스트 문항 생성', mode: 'api', model: 'gpt-test', ms: 1200 };

describe('에이전트 동작 기록', () => {
  it('JSON 은 들여쓰기해 보여 주고 아니면 그대로 둔다', () => {
    expect(readable('{"a":[1,2]}')).toBe('{\n  "a": [\n    1,\n    2\n  ]\n}');
    expect(readable('그냥 문장')).toBe('그냥 문장');
    expect(readable('{깨진 JSON')).toBe('{깨진 JSON');
  });

  it('모델을 바로 부른 기록은 시스템 지시·보낸 입력·응답 원문을 끝까지 보여 준다', () => {
    const detail: AgentLogDetail = {
      ...base,
      calls: [{ role: 'default', model: 'gpt-test', ms: 1200, system: `지시${LONG}`, images: 0, output: `응답${LONG}`,
        messages: [{ role: 'user', content: '이전 질문' }, { role: 'assistant', content: '이전 답변' }, { role: 'user', content: `입력${LONG}` }] }],
    };
    const html = renderToStaticMarkup(<AgentLogBody detail={detail} />);
    for (const text of [`지시${LONG}`, `입력${LONG}`, `응답${LONG}`]) expect(html).toContain(text);
    expect(html).toContain('5,002자');
    expect(html).toContain('이전 대화 · 질문');
    expect(html).toContain('이전 대화 · 답변');
    expect(html).toContain('보낸 입력');
    expect(html).not.toContain('에이전트 입력'); // 바로 부른 기록에는 에이전트 단위 입력·출력이 없다
  });

  it('에이전트 실행 기록은 입력·출력과 그 안의 모델 호출을 모두 보여 준다', () => {
    const call = { role: 'roadmap', model: 'qwen', ms: 5, system: '첫 지시', images: 2, output: '{}', messages: [{ role: 'user', content: '{}' }] };
    const html = renderToStaticMarkup(
      <AgentLogBody detail={{ ...base, input: LONG, output: `출력${LONG}`, error: undefined, calls: [call, { ...call, system: '고치기 지시', error: '모델 응답이 JSON 형식이 아니에요' }] }} />,
    );
    expect(html).toContain(LONG);
    expect(html).toContain(`출력${LONG}`);
    expect(html).toContain('모델 호출 1/2');
    expect(html).toContain('고치기 지시');
    expect(html).toContain('모델 응답이 JSON 형식이 아니에요');
    expect(html).toContain('이미지 2장');
  });

  it('가데이터 실행처럼 모델을 부르지 않은 기록은 그렇게 알린다', () => {
    const html = renderToStaticMarkup(<AgentLogBody detail={{ ...base, mode: 'mock', input: '{}', output: '{}', calls: [] }} />);
    expect(html).toContain('실제 모델을 부르지 않았어요');
  });

  it('실패 단계·추적 ID·단계별 결과와 모델 호출 위치를 함께 보여 준다', () => {
    const html = renderToStaticMarkup(<AgentLogBody detail={{
      ...base, traceId: 'trace-test', failedStage: { id: '4.contract', label: '4단계 · 답변 필드·출처 검증' },
      stages: [{ id: '1.classify', label: '질문 분류', status: 'ok', ms: 2 },
        { id: '4.contract', label: '답변 필드 검증', status: 'failed', ms: 1, errorType: 'LlmError' }],
      calls: [{ role: 'regulation', model: 'qwen', stageId: '4-2.generate', ms: 100,
        system: '지시', images: 0, output: '{"summary":"원문"}', messages: [] }],
    }} />);
    for (const text of ['실패 단계', '답변 필드·출처 검증', 'trace-test', '단계별 실행 로그',
      '질문 분류', 'failed', 'LlmError', '호출 단계 · 4-2.generate', '원문']) expect(html).toContain(text);
  });

  it('목록은 요약과 모델 호출 수만 보여 주고 전문은 펼칠 때 받는다', () => {
    const entries: AgentLogEntry[] = [{ ...base, employee: '시험 직원', by: '관리자', callCount: 3 }, { ...base, id: 2, callCount: 1 }];
    const html = renderToStaticMarkup(<AgentLogList entries={entries} />);
    expect(html).toContain('시험 직원');
    expect(html).toContain('관리자 실행');
    expect(html).toContain('모델 3회');
    expect(html.match(/모델 \d+회/g)).toHaveLength(1);
    expect(renderToStaticMarkup(<AgentLogList entries={[]} />)).toContain('아직 호출한 에이전트가 없어요');
  });
});

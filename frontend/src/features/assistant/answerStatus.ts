import type { AssistantAnswer, EvidenceStatus } from '@/api/endpoints/assistant';

/** 이전 대화·가데이터 응답에도 상태 이름을 제공한다. 오류는 이 함수로 변환하지 않는다. */
export function answerStatus(answer: AssistantAnswer): [string, string] {
  const topic = answer.kind === 'regulation' || answer.topic === 'regulation' ? 'regulation' : answer.topic || (Array.isArray(answer.knowledgeSources) ? 'company' : 'life');
  const status: EvidenceStatus = answer.evidenceStatus || (answer.level === 'refused' ? 'refused' : answer.level === 'ok' || (answer.knowledgeSources?.length || 0) > 0 ? 'found' : ['missing', 'unclear'].includes(answer.level) ? 'partial' : 'not_found');
  if (topic === 'life' && !Array.isArray(answer.knowledgeSources)) return status === 'refused' ? ['사내 생활 답변 불가', 'fail'] : ['사내 생활 안내', ''];
  const prefix = topic === 'regulation' ? '규정' : topic === 'company' ? '회사' : '사내 생활';
  const hasCitation = Boolean(topic === 'regulation' ? answer.basis?.length : answer.knowledgeSources?.length);
  const displayStatus = status === 'partial' ? (hasCitation ? 'found' : 'not_found') : status;
  const labels: Record<typeof displayStatus, [string, string]> = {
    found: ['근거 확인', 'ok'],
    not_found: ['근거 확인 불가', 'warn'],
    refused: ['답변 불가', 'fail'],
  };
  const [label, style] = labels[displayStatus];
  return [`${prefix} ${label}`, style];
}

import type { AssistantAnswer, EvidenceStatus } from '@/api/endpoints/assistant';

/** 이전 대화·가데이터 응답에도 상태 이름을 제공한다. 오류는 이 함수로 변환하지 않는다. */
export function answerStatus(answer: AssistantAnswer): [string, string] {
  if (answer.kind === 'out' || answer.evidenceStatus === 'refused' || answer.level === 'refused') {
    return ['답변 불가', 'fail'];
  }
  const hasCitation = Boolean(answer.kind === 'regulation' ? answer.basis?.length : answer.knowledgeSources?.length);
  const status: EvidenceStatus = answer.evidenceStatus ?? (answer.level === 'ok' || hasCitation ? 'found' : 'not_found');
  const displayStatus = status === 'partial' ? (hasCitation ? 'found' : 'not_found') : status;
  return displayStatus === 'found' ? ['근거 확인', 'ok'] : ['근거 확인 불가', 'warn'];
}

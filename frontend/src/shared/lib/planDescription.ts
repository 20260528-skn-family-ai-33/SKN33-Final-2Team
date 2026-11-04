/** AI 설명 전용 표시 보호. 저장 원문·사용자 요청·자료 원문에는 적용하지 않는다. */
const amount = /(?:₩|\$)\s*\d|\d[\d,.]*\s*(?:만\s*)?(?:원|달러|USD|KRW)/i;
const duration = /\d[\d,.]*\s*(?:주(?!당|제|문|차)|개월|달(?!성)|일(?!반|부|정|차))/;
const aggregateHours = /(?:총|전체|합계|합산|총합)\s*\d[\d,.]*\s*시간|약\s*\d[\d,.]*\s*시간(?!\s*(?:짜리|분량의\s*(?:강좌|강의|영상)|(?:강좌|강의|영상)))/;
const fallback = '기간·비용은 현재 선택 자료 기준의 계산값을 확인해 주세요.';

export function planDescription(text: string | null | undefined): string {
  if (!text?.trim()) return '';
  // 문장을 통째로 숨긴다. 숫자를 교체하면 사용자의 희망 조건이나 자료 원문을 왜곡할 수 있다.
  const sentences = text.trim().split(/(?<=[.!?。])\s+|\n+/);
  const visible = sentences.filter(sentence => !amount.test(sentence) && !duration.test(sentence) && !aggregateHours.test(sentence));
  return visible.length ? visible.join(' ') : fallback;
}

/** 문장 필터와 접기 버튼은 같은 표시용 값을 사용한다. */
export function optionSummary(reason: string | undefined, pros: string[]) {
  const text = planDescription(reason);
  const benefits = pros.map(planDescription).filter(Boolean);
  return { text, benefits, expandable: text.length > 48 || benefits.length > 2 || benefits.some(value => value.length > 32) };
}

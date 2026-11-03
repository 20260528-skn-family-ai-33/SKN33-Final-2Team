import type { Gen } from '@/api/types/draft';

/** 비교 화면에서 다음으로 넘어갈 때 현재 표시한 세 안의 출처만 보낸다. */
export function comparisonEvidence(generation: Gen | null | undefined) {
  const rows: { course: string; optionId: string; promptVersionId: string }[] = [];
  for (const course of ['A1', 'A2', 'A3']) {
    const option = generation?.options[course];
    if (!option?.optionId || !option.promptProvenance?.promptVersionId || generation?.regenRun?.[course]) return undefined;
    rows.push({ course, optionId: option.optionId, promptVersionId: option.promptProvenance.promptVersionId });
  }
  return rows;
}

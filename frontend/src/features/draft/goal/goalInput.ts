/** 직접 입력을 우선하고, 비어 있을 때만 첫 후보를 사용한다. */
export function resolveGoalInput(input: string | null | undefined, firstCandidate: string | null | undefined): string {
  return input?.trim() ? input : firstCandidate?.trim() ?? '';
}

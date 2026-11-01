import type { Answers, Phase } from './flow';
type Pending = { answers: Answers; phase: Phase };
const memory = new Map<string, Pending>();
export const answerMemoryKey = (owner: string | null, draftId: string | null, generation: string, inputs: string) => JSON.stringify([owner, draftId, generation, inputs]);
export function rememberAnswers(key: string, answers: Answers, phase: Phase) { memory.set(key, { answers: { ...answers }, phase }); }
export function pendingAnswers(key: string) { const value = memory.get(key); return value ? { answers: { ...value.answers }, phase: value.phase } : undefined; }

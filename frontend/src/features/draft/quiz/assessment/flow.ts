export type Question = { id: string; text?: string; q?: string; options?: string[] };
export type Group = { skill: string; title: string; surveys: Question[]; quizzes: Question[] };
export type Survey = { generationId: string; groups: Group[]; questionCount: number };
export type Answers = Record<string, number>;
export type Phase = 'surveys' | 'quizzes';
export function complete(survey: Survey, answers: Answers, phase: Phase): boolean {
  return survey.groups.length > 0 && survey.groups.every(g => g[phase].length > 0 && g[phase].every(q =>
    Object.hasOwn(answers, q.id) && Number.isInteger(answers[q.id]) &&
    answers[q.id] >= (phase === 'surveys' ? 1 : 0) && answers[q.id] <= (phase === 'surveys' ? 5 : 4)));
}

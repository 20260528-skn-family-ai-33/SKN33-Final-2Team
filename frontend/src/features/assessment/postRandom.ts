import type { PlanRecord } from '@/api/types/plan';

/** 테스트 편의: 준비된 문항만 채우며 보고서 생성이나 퀴즈 생성은 실행하지 않는다. */
export function fillRandomPost(record: PlanRecord, random = Math.random): void {
  const post = record.post;
  const pick = (count: number) => String(Math.floor(random() * count));
  for (const question of record.plan.assess?.questions || []) post.answers[question.id] = String(Number(pick(5)) + 1);
  post.quizAnswers ||= {};
  for (const group of post.quizSurvey?.groups || []) {
    for (const question of group.quizzes) if (question.options?.length) post.quizAnswers[question.id] = pick(question.options.length);
  }
  if (post.deep?.status === 'ready' && !post.deep.judge && post.deep.quiz) {
    post.deep.mcq ||= {};
    for (const [id, question] of Object.entries(post.deep.quiz.mcq)) if (question.options.length) post.deep.mcq[id] = pick(question.options.length);
  }
  post.goalSelf = String(Number(pick(5)) + 1);
}

/* 5단계 결과 요약(#224): 답안지를 다시 보여 주기 전에 스킬별로 몇 문제 맞았고 스스로 어떻게 평가했는지 먼저 보여 준다 */
import type { Answers, Survey } from '../quiz/assessment/flow';

export interface SkillSummary {
  skill: string;
  quizCorrect: number;
  /** 정답이 공개된 퀴즈 문항 수 */
  quizTotal: number;
  /** 설문(1~5점) 평균. 답한 문항이 없으면 null */
  selfAverage: number | null;
}
export interface AssessmentSummary {
  skills: SkillSummary[];
  quizCorrect: number;
  quizTotal: number;
}

export function assessmentSummary(survey: Pick<Survey, 'groups'>, answers: Answers): AssessmentSummary {
  const skills = survey.groups.map(group => {
    const graded = group.quizzes.filter(question => typeof question.answer === 'number');
    const scores = group.surveys.map(question => answers[question.id]).filter(value => Number.isInteger(value) && value >= 1 && value <= 5);
    return {
      skill: group.skill,
      quizCorrect: graded.filter(question => answers[question.id] === question.answer).length,
      quizTotal: graded.length,
      selfAverage: scores.length ? Math.round((scores.reduce((sum, value) => sum + value, 0) / scores.length) * 10) / 10 : null,
    };
  });
  return {
    skills,
    quizCorrect: skills.reduce((sum, row) => sum + row.quizCorrect, 0),
    quizTotal: skills.reduce((sum, row) => sum + row.quizTotal, 0),
  };
}

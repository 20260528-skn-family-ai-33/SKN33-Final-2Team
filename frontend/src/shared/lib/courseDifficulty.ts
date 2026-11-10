const labels: Record<string, string> = { BEGINNER: '초급', INTERMEDIATE: '중급', UPPER_INTERMEDIATE: '중상', ADVANCED: '고급' };

export function courseDifficultyLevel(difficulty?: string | null) {
  return labels[difficulty ?? ''] ?? '미기재';
}

export function courseDifficulty(r: { difficulty?: string | null }) {
  return `난이도 ${courseDifficultyLevel(r.difficulty)}`;
}

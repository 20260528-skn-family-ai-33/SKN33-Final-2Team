import { expect, it } from 'vitest';
import { courseDifficulty } from './courseDifficulty';

it.each([
  [{ difficulty: 'BEGINNER', estimated: ['difficulty'] }, '초급'],
  [{ difficulty: 'INTERMEDIATE', difficultySource: 'original' }, '중급'],
  [{ difficulty: 'UPPER_INTERMEDIATE', difficultySource: 'reviewed' }, '중상'],
  [{ difficulty: 'ADVANCED', difficultyEstimated: true }, '고급'],
  [{ difficulty: null }, '미기재'],
] as const)('추천 카드에는 난이도 등급만 표시한다: %s', (resource, level) => {
  expect(courseDifficulty(resource)).toBe(`난이도 ${level}`);
});

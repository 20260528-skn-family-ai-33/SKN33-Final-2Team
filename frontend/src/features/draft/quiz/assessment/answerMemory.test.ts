import { expect, it } from 'vitest';
import { sameJ } from '@/shared/lib/format';
import { answerMemoryKey, rememberAnswers, pendingAnswers } from './answerMemory';
it('DB가 응답 키 순서를 바꿔도 같은 답으로 판정해 완료 상태를 해제하지 않는다', () => {
  const key=answerMemoryKey('u','d','g','inputs');
  rememberAnswers(key,{'s-2':5,'s-1':3,'q-2':0,'q-1':4},'quizzes');
  const server={'q-1':4,'q-2':0,'s-1':3,'s-2':5};
  expect(sameJ(pendingAnswers(key)!.answers,server)).toBe(true);
  expect(sameJ(pendingAnswers(key)!.answers,{...server,'q-2':1})).toBe(false);
});

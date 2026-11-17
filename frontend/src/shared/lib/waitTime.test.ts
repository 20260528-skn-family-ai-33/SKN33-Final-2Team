import { expect, it } from 'vitest';
import { SLOW_WAIT, waitTime } from './waitTime';

it('RunPod-Ollama 면 걸리는 시간을 최대 10분으로 바꾸고, 아니면 화면의 보통 시간을 그대로 쓴다', () => {
  expect(SLOW_WAIT).toBe('최대 10분까지 걸릴 수 있어요');
  for (const usual of ['1~2분쯤 걸릴 수 있어요', '30초에서 1분쯤 걸려요']) {
    expect(waitTime(usual, false)).toBe(usual);
    expect(waitTime(usual, true)).toBe(SLOW_WAIT);
    expect(waitTime(usual, true).match(/\d+(초|분)/g)).toEqual(['10분']);
  }
});

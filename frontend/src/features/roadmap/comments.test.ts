/* 부서장 코멘트 모양 판정: 보여 주는 모양(CmItem)과 '보낸 코멘트 고치기' 칸(TeamPages)이 같은 판정을 쓴다 */
import { describe, expect, it } from 'vitest';
import { isFreeComment, isSkillFeedback } from './comments';

const base = { skill: '', fit: 'none', fitText: '', level: 'none', levelText: '', free: '' };

describe('isSkillFeedback', () => {
  it('스킬의 좋아요는 이유·메모 없이 스킬 피드백이다', () => {
    expect(isSkillFeedback({ ...base, skill: 'SQL', fit: 'good' })).toBe(true);
  });

  it('보완 필요는 이유 단추로 고른 값(없어도 됨)과 메모만 있으면 스킬 피드백이다', () => {
    expect(isSkillFeedback({ ...base, skill: 'SQL', fit: 'partial', fitText: '난이도·분량 / 학습 목표', free: '분량이 많아요' })).toBe(true);
    expect(isSkillFeedback({ ...base, skill: 'SQL', fit: 'partial' })).toBe(true);
  });

  it('직접 쓴 글이나 수준 의견이 있으면 예전 세 칸 코멘트로 본다', () => {
    expect(isSkillFeedback({ ...base, skill: 'SQL', fit: 'partial', fitText: '업무와 조금 달라요' })).toBe(false);
    expect(isSkillFeedback({ ...base, skill: 'SQL', fit: 'good', level: 'adjust' })).toBe(false);
    expect(isSkillFeedback({ ...base, skill: 'SQL', fit: 'good', fitText: '난이도·분량' })).toBe(false);
  });

  it('스킬이 없거나 의견이 없으면 스킬 피드백이 아니다', () => {
    expect(isSkillFeedback({ ...base, fit: 'good' })).toBe(false);
    expect(isSkillFeedback({ ...base, skill: 'SQL' })).toBe(false);
  });
});

describe('isFreeComment', () => {
  it('스킬 없이 글만 있으면 전체 코멘트다', () => {
    expect(isFreeComment({ ...base, free: '일정만 조정해 주세요' })).toBe(true);
  });

  it('스킬·선택 의견이 있거나 글이 없으면 전체 코멘트가 아니다', () => {
    expect(isFreeComment({ ...base, skill: 'SQL', free: '메모' })).toBe(false);
    expect(isFreeComment({ ...base, fit: 'good', free: '메모' })).toBe(false);
    expect(isFreeComment(base)).toBe(false);
  });
});

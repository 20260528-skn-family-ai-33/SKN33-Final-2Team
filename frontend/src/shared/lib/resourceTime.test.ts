import { describe, expect, it } from 'vitest';
import { activityTime, resourceTime, roundedDuration } from './resourceTime';
import type { Resource } from '@/api/types/catalog';

const base: Resource = { id:'fixture', title:'Fixture', provider:'Fixture', kind:'강좌' };
describe('resourceTime', () => {
  it('distinguishes saved estimates, confirmed time and old plans without time provenance', () => {
    expect(activityTime({ hours:1, res:'old-course' }).text).toBe('계획 1시간 (추정 여부 미기록)');
    expect(activityTime({ hours:1, res:'course', hoursEstimated:true }).text).toBe('계획 1시간 (추정)');
    expect(activityTime({ hours:1, res:'course', hoursEstimated:false }).text).toBe('계획 1시간');
    expect(activityTime({ hours:1, res:null }).text).toBe('계획 1시간');
    expect(activityTime({ hours:1, res:'course', hoursBasis:'저장된 근거' }).title).toBe('저장된 근거');
  });
  it('keeps provider video and learning time distinct', () => {
    expect(resourceTime({ ...base, hours:36540/3600, timeStatus:'confirmed', durationKind:'video' })).toBe('영상 10시간 10분');
    expect(resourceTime({ ...base, hours:71/60, timeStatus:'confirmed', durationKind:'learning' })).toBe('학습 1시간 10분');
  });
  it('labels curriculum estimates and missing values without inventing one hour', () => {
    expect(resourceTime({ ...base, hours:50/60, timeStatus:'estimated' })).toBe('계획 예상 50분');
    expect(resourceTime(base)).toBe('시간 미확인');
    expect(resourceTime({ ...base, hours:null })).toBe('시간 미확인');
    expect(roundedDuration(0)).toBe('시간 미확인');
    expect(roundedDuration(1/60)).toBe('10분 미만');
    expect(roundedDuration(65/60)).toBe('1시간 10분');
  });
});

import type { Resource } from '@/api/types/catalog';
import type { Activity } from '@/api/types/plan';
import { hrs } from './format';

/** Course runtime and a timetable allowance are distinct, even when both are numeric. */
export function roundedDuration(hours: number): string {
  if (!Number.isFinite(hours) || hours <= 0) return '시간 미확인';
  return hrs(hours);
}

export function resourceTime(r: Resource | null | undefined): string {
  if (r?.hours == null || !Number.isFinite(r.hours) || r.hours <= 0) return '시간 미확인';
  const time = roundedDuration(r.hours);
  if (r.timeStatus === 'estimated') return `계획 예상 ${time}`;
  if (r.durationKind === 'video') return `영상 ${time}`;
  if (r.durationKind === 'learning') return `학습 ${time}`;
  if (r.timeStatus === 'manual') return `계획 ${time} (관리자 입력)`;
  return time + ((r.estimated || []).includes('hours') ? ' (계획 추정)' : '');
}

/** Historical plans keep their own hours; today's catalog cannot prove the old basis. */
export function activityTime(a: Pick<Activity, 'hours' | 'hoursEstimated' | 'hoursBasis' | 'res'>): { text: string; title: string } {
  const unknown = Boolean(a.res) && a.hoursEstimated === undefined;
  const suffix = a.hoursEstimated ? ' (추정)' : unknown ? ' (추정 여부 미기록)' : '';
  return {
    text: `계획 ${roundedDuration(a.hours)}${suffix}`,
    title: a.hoursBasis || (unknown ? '저장 당시 시간 근거가 없어 확인된 시간인지 알 수 없어요. 기존 계획 시간은 유지해요.' : '로드맵에 저장된 계획 시간입니다'),
  };
}

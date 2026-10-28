import type { Resource } from '@/api/types/catalog';

/** Course runtime and a timetable allowance are distinct, even when both are numeric. */
export function roundedDuration(hours: number): string {
  if (!Number.isFinite(hours) || hours <= 0) return '시간 미확인';
  if (hours < 5 / 60) return '10분 미만';
  const minutes = Math.max(10, Math.round(hours * 6) * 10);
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return [h ? `${h}시간` : '', m ? `${m}분` : ''].filter(Boolean).join(' ');
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

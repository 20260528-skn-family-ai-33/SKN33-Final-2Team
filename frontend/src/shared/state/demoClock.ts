/* 시연 도구의 기준 날짜 — 로드맵 주차를 계산할 때 쓰는 오늘을 앞으로 옮겨 본다.
   서버 기록은 바꾸지 않는다. 부서장 계정으로 다시 로그인해도 같은 날짜로 확인하도록 탭 단위(sessionStorage)로 둔다.
   실제 오늘보다 이전으로는 옮기지 않는다: 로드맵 시작 전(0주차 이하)처럼 실제로는 생기지 않는 상태가 되기 때문이다. */
import { create } from 'zustand';
import { canUseDemo } from '@/shared/lib/demoAccess';
import { useAi } from './ai';

const KEY = 'gp-demo-day';
const DAY_FORMAT = /^\d{4}-\d{2}-\d{2}$/;

const pad = (n: number): string => String(n).padStart(2, '0');
/** 브라우저 현지 날짜(YYYY-MM-DD). toISOString 은 UTC 라 오전 9시 전에는 하루 전 날짜가 된다 */
export const isoDay = (d: Date): string => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function saved(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** 형식이 맞고 실제 오늘보다 뒤인 날짜만 쓴다. 탭을 며칠 열어 둬 오늘이 따라잡으면 실제 날짜로 돌아간다 */
const ahead = (day: string | null, now: Date): string | null => (day && DAY_FORMAT.test(day) && day > isoDay(now) ? day : null);

export const useDemoClock = create<{ day: string | null }>(() => ({ day: saved() }));

/** 기준 날짜를 정한다. null·오늘·과거 날짜를 주면 실제 날짜로 돌아간다 */
export function setDemoDay(day: string | null): void {
  const next = ahead(day, new Date());
  try {
    if (next) sessionStorage.setItem(KEY, next);
    else sessionStorage.removeItem(KEY);
  } catch {
    // 저장소가 막혀 있어도 지금 화면에는 적용한다(새로 고치면 실제 날짜로 돌아간다)
  }
  useDemoClock.setState({ day: next });
}

/** 주차 계산에 쓰는 현재 시각. 기준 날짜가 없거나 시연이 꺼져 있으면 실제 시각이다 */
export function clockNow(): Date {
  const now = new Date();
  const day = ahead(useDemoClock.getState().day, now);
  if (!day || !canUseDemo(useAi.getState().status.demoMode)) return now;
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d);
}

/** 지금 적용 중인 기준 날짜(없으면 null). 서버의 시연 허용 응답이 늦게 와도 그때 다시 그리도록 함께 구독한다 */
export function useDemoDay(): string | null {
  const day = useDemoClock((s) => s.day);
  const allowed = useAi((s) => canUseDemo(s.status.demoMode));
  return allowed ? ahead(day, new Date()) : null;
}

/** 오늘로 주차를 그리는 컴포넌트가 부른다. 기준 날짜가 바뀌면 그 컴포넌트만 다시 그린다.
    페이지를 통째로 다시 띄우면 알림 읽음 처리 같은 진입 동작이 되풀이되어 서버에 기록이 남는다 */
export function useClockRefresh(): void {
  useDemoDay();
}

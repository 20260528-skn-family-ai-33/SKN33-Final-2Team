/* 새 알림 하단 플로팅(#96) — 알림 목록을 새로 받을 때마다(30초마다·화면 이동·창 열 때·읽음 응답) 처음 보는 읽지 않은 알림을
   화면 아래에 띄운다. 누르면 알림 창에서 누른 것과 같이 읽음으로 바꾸고 그 화면으로 간다(NotificationBell).
   - 로그인마다 첫 목록은 기준으로만 삼고 띄우지 않는다(로그인하자마자 쌓여 있던 알림이 한꺼번에 뜨지 않게)
   - 알림 창이 열려 있거나 그 알림의 화면을 이미 보고 있으면 띄우지 않는다
   - FLOAT_MS 뒤 내린다. 마우스를 올리거나 초점이 들어와 있는 동안은 내리지 않는다. 어디서든 읽음이 되면 바로 내린다
   React 상태가 아니라 이 모듈의 작은 저장소에 둔다(목록을 받은 effect 안에서 넣어야 해서. 화면 아래 문구 toast 와 같은 방식) */
import { create } from 'zustand';
import type { AppNotification } from '@/api/types/notification';

export const FLOAT_MS = 8000;
/** 한 번에 보이는 수. 더 있으면 '새 알림 N건 더'로 알림 창을 연다 */
export const FLOAT_MAX = 3;

/** 이 로그인에서 지금까지 본 알림 id 와 가장 최근 알림 시각(ms) */
export interface Arrivals {
  known: ReadonlySet<string>;
  latest: number | null;
}

const timeOf = (n: AppNotification): number => {
  const v = Date.parse(n.createdAt);
  return Number.isNaN(v) ? 0 : v;
};

/** 받은 목록에서 새로 온 알림을 고른다. prev 가 없으면(이 로그인의 첫 목록) 기준만 만들고 고르지 않는다.
 *  처음 보는 id 라도 이미 본 가장 최근 알림보다 오래된 것은 고르지 않는다. 읽지 않은 알림이 50건을 넘을 때 앞의 것을 읽으면
 *  뒤에 밀려 있던 옛 알림이 목록에 새로 들어오기 때문 */
export function takeArrivals(prev: Arrivals | null, items: AppNotification[]): { next: Arrivals; fresh: AppNotification[] } {
  const known = new Set(prev?.known);
  let latest = prev?.latest ?? null;
  const fresh: AppNotification[] = [];
  for (const n of items) {
    const at = timeOf(n);
    if (prev && !n.read && !prev.known.has(n.id) && (prev.latest === null || at >= prev.latest)) fresh.push(n);
    known.add(n.id);
    latest = latest === null ? at : Math.max(latest, at);
  }
  return { next: { known, latest }, fresh };
}

interface FloatState {
  /** 오래된 것 먼저. 화면에서는 가장 최근 알림이 맨 아래(화면 가장자리 쪽)에 온다 */
  items: AppNotification[];
}

export const useFloats = create<FloatState>(() => ({ items: [] }));

const timers = new Map<string, ReturnType<typeof setTimeout>>();
let held = false;
let seen: { who: string; arrivals: Arrivals } | null = null;

function arm(id: string): void {
  clearTimeout(timers.get(id));
  timers.set(
    id,
    setTimeout(() => dismissFloat(id), FLOAT_MS),
  );
}

function stopTimers(): void {
  timers.forEach((t) => clearTimeout(t));
  timers.clear();
}

/** 띄운 알림 하나를 내린다(닫기·누름·시간 지남) */
export function dismissFloat(id: string): void {
  clearTimeout(timers.get(id));
  timers.delete(id);
  const items = useFloats.getState().items.filter((n) => n.id !== id);
  useFloats.setState({ items });
  // 누른 알림이 사라지면 마우스가 그 자리에 있어도 mouseleave 가 오지 않을 수 있어, 다 내리면 멈춤도 푼다
  if (!items.length) held = false;
}

/** 모두 내린다(알림 창을 열 때·로그인이 바뀔 때) */
export function clearFloats(): void {
  stopTimers();
  held = false;
  useFloats.setState({ items: [] });
}

/** 마우스·초점이 들어와 있는 동안 내리지 않고, 나가면 남은 알림을 처음부터 다시 잰다 */
export function holdFloats(on: boolean): void {
  if (held === on) return;
  held = on;
  if (on) stopTimers();
  else useFloats.getState().items.forEach((n) => arm(n.id));
}

/** 새로 받은 목록을 넘긴다. who: 로그인(직원 id·로그인 회차), skip: 띄우지 않을 알림(창이 열림·이미 그 화면).
 *  목록에 없어진(읽음이 된) 알림은 내리고, 새로 온 알림은 띄운다 */
export function noteInbox(who: string, items: AppNotification[], skip: (n: AppNotification) => boolean): void {
  if (seen?.who !== who) {
    clearFloats();
    seen = null;
  }
  const { next, fresh } = takeArrivals(seen?.arrivals ?? null, items);
  seen = { who, arrivals: next };
  const unread = new Set(items.filter((n) => !n.read).map((n) => n.id));
  for (const n of useFloats.getState().items) if (!unread.has(n.id)) dismissFloat(n.id);
  const show = fresh.filter((n) => !skip(n));
  if (!show.length) return;
  const ids = new Set(show.map((n) => n.id));
  // 서버는 최근 것 먼저 보낸다 → 뒤집어 오래된 것부터 쌓는다
  useFloats.setState((s) => ({ items: [...s.items.filter((n) => !ids.has(n.id)), ...[...show].reverse()] }));
  if (!held) show.forEach((n) => arm(n.id));
}

/** 알림 버튼이 사라질 때(로그아웃 등) 기준과 띄운 알림을 모두 버린다 */
export function resetFloats(): void {
  seen = null;
  clearFloats();
}

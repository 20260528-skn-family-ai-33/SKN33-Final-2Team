/* 입력 칸 ↔ 작업 공간 상태 연결 (5차 data-bind 경로 방식을 옮김).
   경로는 작업 공간(WsState) 기준 'draft.prefs.hours' · 'plans.<id>.rev.v.hours' 같은 점 경로다.
   값을 바꾼 뒤 기능별 뒤처리(세부 사항을 바꾸면 확인 화면 다시 거치기 등)는 onBound 로 등록한다 */
import { updateWs, useWs, type WsState } from './workspace';

export function getAt<T = unknown>(o: unknown, path: string): T {
  return path.split('.').reduce<unknown>((x, k) => (x == null ? undefined : (x as Record<string, unknown>)[k]), o) as T;
}

function setIn(o: Record<string, unknown>, path: string, val: unknown): void {
  const ks = path.split('.');
  let x = o;
  ks.slice(0, -1).forEach((k) => {
    if (x[k] == null || typeof x[k] !== 'object') x[k] = {};
    x = x[k] as Record<string, unknown>;
  });
  x[ks[ks.length - 1]] = val;
}

type After = (s: WsState, path: string, evt?: 'input' | 'change') => void;
const afters = new Set<After>();
export function onBound(fn: After): () => void {
  afters.add(fn);
  return () => afters.delete(fn);
}

export function setAt(path: string, val: unknown, evt: 'input' | 'change' = 'change'): void {
  updateWs((s) => {
    setIn(s as unknown as Record<string, unknown>, path, val);
    afters.forEach((f) => f(s, path, evt));
  });
}

/** 체크 상자 묶음(값 배열)에 넣거나 뺀다 */
export function toggleIn(path: string, v: string, on: boolean): void {
  updateWs((s) => {
    const arr = ((getAt<string[]>(s, path) || []) as string[]).slice();
    const i = arr.indexOf(v);
    if (on && i < 0) arr.push(v);
    if (!on && i >= 0) arr.splice(i, 1);
    setIn(s as unknown as Record<string, unknown>, path, arr);
    afters.forEach((f) => f(s, path, 'change'));
  });
}

export const useAt = <T = unknown>(path: string): T => useWs((s) => getAt<T>(s, path));

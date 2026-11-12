import { useLayoutEffect, useRef } from 'react';
import { create } from 'zustand';

export type ConsoleAction = { name: string; alias: string; description: string; run: () => string | Promise<string> };
export const useConsoleActions = create<{ actions: ConsoleAction[] }>(() => ({ actions: [] }));

/** 화면을 떠나면 명령을 제거하고 실행 시점의 현재 초안과 스킬을 사용한다. */
export function useConsoleAction(name: string, alias: string, description: string, enabled: boolean, run: ConsoleAction['run'], first = false) {
  const handler = useRef(run);
  useLayoutEffect(() => { handler.current = run; });
  useLayoutEffect(() => {
    if (!enabled) return;
    const action = { name, alias, description, run: () => handler.current() };
    useConsoleActions.setState(s => ({ actions: first ? [action, ...s.actions] : [...s.actions, action] }));
    return () => useConsoleActions.setState(s => ({ actions: s.actions.filter(a => a !== action) }));
  }, [alias, description, enabled, first, name]);
}

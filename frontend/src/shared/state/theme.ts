/* 테마 색상 (브라우저에만 저장 · 5차 gp-core.js THEMES) */
import { create } from 'zustand';
import { store } from './workspace';

export const THEMES: [string, string, string][] = [
  ['green', '그린', '#0E7C66'],
  ['blue', '블루', '#2F5BEA'],
  ['purple', '퍼플', '#6B4FD8'],
  ['coral', '코랄', '#CF5136'],
  ['charcoal', '차콜', '#35383E'],
];
const KEY = 'growpath.theme';

function apply(key: string): string {
  const t = THEMES.find((x) => x[0] === key) || THEMES[0];
  document.documentElement.style.setProperty('--accent', t[2]);
  return t[0];
}

export const useTheme = create<{ theme: string }>(() => ({ theme: apply(store.get(KEY) || 'green') }));

export function setTheme(key: string): void {
  useTheme.setState({ theme: apply(key) });
  store.set(KEY, key);
}

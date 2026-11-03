/* 좌측 메뉴 접기 (브라우저에만 저장) — 접으면 <html data-side="collapsed"> 로 아이콘만 남긴다(styles/gp.css '좌측 메뉴 접기') */
import { create } from 'zustand';
import { store } from './workspace';

const KEY = 'growpath.side';

function apply(collapsed: boolean): boolean {
  if (collapsed) document.documentElement.dataset.side = 'collapsed';
  else delete document.documentElement.dataset.side;
  return collapsed;
}

export const useSideMenu = create<{ collapsed: boolean }>(() => ({ collapsed: apply(store.get(KEY) === 'collapsed') }));

export function toggleSideMenu(): void {
  const collapsed = apply(!useSideMenu.getState().collapsed);
  useSideMenu.setState({ collapsed });
  store.set(KEY, collapsed ? 'collapsed' : 'open');
}

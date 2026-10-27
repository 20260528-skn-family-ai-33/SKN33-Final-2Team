/* 화면 공통: 알림(토스트)·가운데 창(시트). 내용은 함수로 받아 열린 동안 상태가 바뀌면 다시 그린다 */
import type { ReactNode } from 'react';
import { create } from 'zustand';

export interface SheetSpec {
  title?: ReactNode;
  sub?: ReactNode;
  wide?: boolean;
  /** 열린 동안 매번 다시 부른다(최신 상태로 그리기) */
  body: () => ReactNode;
  foot?: () => ReactNode;
  onClose?: () => void;
}

interface UiState {
  toast: { msg: string; at: number } | null;
  sheet: SheetSpec | null;
}

export const useUi = create<UiState>(() => ({ toast: null, sheet: null }));

let toastTimer: ReturnType<typeof setTimeout> | undefined;

export function toast(msg: string): void {
  useUi.setState({ toast: { msg, at: Date.now() } });
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => useUi.setState({ toast: null }), 2600);
}

export function openSheet(spec: SheetSpec): void {
  closeSheet();
  useUi.setState({ sheet: spec });
}

export function closeSheet(): void {
  const s = useUi.getState().sheet;
  if (!s) return;
  useUi.setState({ sheet: null });
  s.onClose?.();
}

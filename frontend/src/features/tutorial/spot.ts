/* 비출 자리(구멍)와 안내 글 자리 계산 — 화면 크기와 대상의 위치만 받는 순수 함수 */

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** below·above·right·left: 구멍의 그쪽에 놓고 화살표로 가리킨다 · under·over: 화살표 놓을 틈은 없어 바로 아래·위에 붙여 쓴다
    dock: 놓을 곳이 없어 비춘 자리 위 아래 가운데에 겹친다
    up·down: 대상이 화면 밖(위·아래)에 있어 가운데에 두고 그쪽을 가리킨다 */
export type Side = 'below' | 'above' | 'right' | 'left' | 'under' | 'over' | 'dock' | 'up' | 'down';

export interface NotePlace {
  side: Side;
  /** 위·아래에 놓을 때 비춘 자리의 오른쪽 끝에 맞췄는지(화살표도 오른쪽에 둔다) */
  end?: boolean;
  x: number;
  y: number;
}

const PAD = 8; // 대상과 테두리 사이
export const GAP = 60; // 테두리와 안내 글 사이(화살표 길이)
const EDGE = 16; // 화면 가장자리 여백

const clamp = (v: number, lo: number, hi: number): number => Math.min(Math.max(v, lo), Math.max(lo, hi));

/** 대상 둘레에 여백을 주고 보이는 띠(위 top ~ 아래 floor) 안으로 자른다. 띠 밖에 있으면 null.
    top 은 화면 위에 붙어 있는 띠·상단 메뉴의 아래 끝, floor 는 화면 아래에 붙어 있는 요약 줄의 위 끝이다 —
    스크롤로 대상이 그 밑으로 들어가도 상단 메뉴가 비춘 자리 안에 들어와 밝게 보이지 않게 한다 */
export function holeOf(rect: Box, vw: number, floor: number, top = 0): Box | null {
  const x = Math.max(0, Math.round(rect.x - PAD));
  const y = Math.max(top, Math.round(rect.y - PAD));
  const r = Math.min(vw, Math.round(rect.x + rect.w + PAD));
  const b = Math.min(floor, Math.round(rect.y + rect.h + PAD));
  return r - x < 8 || b - y < 8 ? null : { x, y, w: r - x, h: b - y };
}

/** 비춘 자리가 대상보다 위·아래에서 잘렸는지(잘린 쪽은 모서리를 둥글리지 않아 이어진다는 것을 보인다) */
export function cutOf(rect: Box, hole: Box): string {
  const cut: string[] = [];
  if (hole.y > Math.round(rect.y - PAD)) cut.push('top');
  if (hole.y + hole.h < Math.round(rect.y + rect.h + PAD)) cut.push('bottom');
  return cut.join(' ');
}

/** 안내 글 자리: 아래 → 위 → 오른쪽 → 왼쪽 순으로 들어가는 곳. 어디에도 안 들어가면(대상이 화면을 채움) 아래 가운데에 붙인다
    (왼쪽 아래는 테마 고르기, 오른쪽 아래는 도우미 버튼 자리). top 위(상단 메뉴 자리)에는 놓지 않는다 */
export function placeNote(hole: Box, vw: number, vh: number, noteW: number, noteH: number, end = false, top = 0): NotePlace {
  const x = clamp(end ? hole.x + hole.w - noteW : hole.x, EDGE, vw - noteW - EDGE);
  const y = clamp(hole.y, Math.max(EDGE, top), vh - noteH - EDGE);
  if (vh - (hole.y + hole.h) >= noteH + GAP + EDGE) return { side: 'below', end, x, y: hole.y + hole.h + GAP };
  if (hole.y - top >= noteH + GAP + EDGE) return { side: 'above', end, x, y: hole.y - GAP - noteH };
  if (vw - (hole.x + hole.w) >= noteW + GAP + EDGE) return { side: 'right', x: hole.x + hole.w + GAP, y };
  if (hole.x >= noteW + GAP + EDGE) return { side: 'left', x: hole.x - GAP - noteW, y };
  if (vh - (hole.y + hole.h) >= noteH + EDGE * 2) return { side: 'under', x, y: hole.y + hole.h + EDGE };
  if (hole.y - top >= noteH + EDGE * 2) return { side: 'over', x, y: hole.y - EDGE - noteH };
  return { side: 'dock', x: Math.max(EDGE, Math.round((vw - noteW) / 2)), y: Math.max(EDGE, vh - noteH - EDGE) };
}

/** 대상이 화면 밖으로 나갔을 때: 화면 가운데에 두고 대상이 있는 쪽을 가리킨다 */
export function placeAway(above: boolean, vw: number, vh: number, noteW: number, noteH: number): NotePlace {
  return { side: above ? 'up' : 'down', x: Math.max(EDGE, Math.round((vw - noteW) / 2)), y: Math.max(EDGE, Math.round((vh - noteH) / 2)) };
}

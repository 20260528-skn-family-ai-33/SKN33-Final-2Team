/* 처음 열 때 쓸 화면 값 정하기 — 주소의 ?skin= 이 먼저, 없거나 모르는 테마면 브라우저에 기억한 값, 그것도 아니면 기본(다크 모드 612).
   값은 '<테마 id>' 뒤에 꼬리표를 붙인 글자 하나: ':narrow'(이전 본문 폭). 예: tm464, tm612:narrow.
   예전 꼬리표 ':side'(좌측 메뉴 · 2026-11-17 앱에서 뺐다)는 읽을 때 버린다. 지운 테마(486 · 503 · 557 · 590 · 606)나 예전 '원래 화면'(base)을
   기억해 둔 브라우저는 모르는 테마로 보고 기본으로 연다 */

export type Mode = 'light' | 'dark';

/** 화면 모드마다 쓰는 테마 폴더: 라이트 = templatemo 464 Ultra Profile · 다크 = templatemo 612 Parallax Starter */
export const MODE_SKIN: Record<Mode, string> = { light: 'tm464', dark: 'tm612' };

/** 기본 테마: 다크 모드(612 · 2026-11-12 #211에서 정한 기본을 그대로 둔다).
    열기만 한 브라우저는 고른 값을 기억하지 않으므로(choiceToRemember), 기본값을 바꾸면 직접 고르지 않은 브라우저는 다음에 열 때 따라간다 */
export const DEFAULT_SKIN = MODE_SKIN.dark;

export interface Choice {
  /** 테마 id(skins/<id>/) */
  skin: string;
  /** 이전 본문 폭(5차 원래 폭: 580 · 760 · 980px) */
  narrow: boolean;
}

export function modeOf(skin: string): Mode {
  return skin === MODE_SKIN.light ? 'light' : 'dark';
}

export function parseChoice(v: string): Choice {
  const [skin, ...tags] = v.split(':');
  return { skin, narrow: tags.includes('narrow') };
}

export function formatChoice(c: Choice): string {
  return c.skin + (c.narrow ? ':narrow' : '');
}

export function pickChoice(query: string | null, saved: string | null, ids: readonly string[]): Choice {
  for (const v of [query, saved]) {
    if (!v) continue;
    const c = parseChoice(v);
    if (ids.includes(c.skin)) return c;
  }
  // 기본 테마 폴더를 지웠으면 남은 테마 중 첫 번째
  return { skin: ids.includes(DEFAULT_SKIN) ? DEFAULT_SKIN : ids[0] ?? DEFAULT_SKIN, narrow: false };
}

/** 처음 열 때 기억할 값 — 주소의 ?skin= 으로 아는 테마를 연 때만 그 값을 돌려준다(새로 고치거나 주소 없이 다시 열어도 유지되게).
    아무것도 고르지 않고 열기만 한 때는 null: 기억하지 않아야 기본 테마가 바뀌었을 때 따라간다. 버튼으로 바꾼 값은 setChoice 가 기억한다 */
export function choiceToRemember(query: string | null, ids: readonly string[]): string | null {
  if (!query) return null;
  const c = parseChoice(query);
  return ids.includes(c.skin) ? formatChoice(c) : null;
}

/* 처음 열 때 쓸 화면 고르기 값 정하기 — 주소의 ?skin= 이 먼저, 없거나 모르는 테마면 브라우저에 기억한 값, 그것도 아니면 기본 테마(612 · 상단 메뉴).
   값은 '<테마 id>' 뒤에 꼬리표를 붙인 글자 하나: ':side'(좌측 메뉴 버전) · ':narrow'(이전 본문 폭). 예: tm464, tm464:side, tm590:narrow.
   꼬리표만 덧붙이는 형식이라 예전에 공유한 주소(?skin=tm464:side)도 그대로 열린다.
   예전의 '원래 화면'(base)은 고르기에서 뺐다. 기억해 둔 base 나 ?skin=base 는 모르는 테마로 보고 기본 테마로 연다 */

/** 기본 테마: templatemo 612 Parallax Starter · 상단 메뉴(2026-11-12 #211에서 464 Ultra Profile → 612).
    열기만 한 브라우저는 고른 값을 기억하지 않으므로(choiceToRemember), 기본값을 바꾸면 직접 고르지 않은 브라우저는 다음에 열 때 따라간다 */
export const DEFAULT_SKIN = 'tm612';

/** 좌측 메뉴를 그리는 가장 좁은 화면 폭(px). 본문에 상단 메뉴 버전의 960px 만큼은 남긴다(메뉴 248px 포함) */
export const SIDE_NAV_MIN_WIDTH = 1200;

export interface Choice {
  /** 테마 id(skins/<id>/) */
  skin: string;
  /** 좌측 메뉴 버전 */
  side: boolean;
  /** 이전 본문 폭(5차 원래 폭: 580 · 760 · 980px) */
  narrow: boolean;
}

export function parseChoice(v: string): Choice {
  const [skin, ...tags] = v.split(':');
  return { skin, side: tags.includes('side'), narrow: tags.includes('narrow') };
}

export function formatChoice(c: Choice): string {
  return c.skin + (c.side ? ':side' : '') + (c.narrow ? ':narrow' : '');
}

export function pickChoice(query: string | null, saved: string | null, ids: readonly string[]): Choice {
  for (const v of [query, saved]) {
    if (!v) continue;
    const c = parseChoice(v);
    if (ids.includes(c.skin)) return c;
  }
  // 기본 테마 폴더를 지웠으면 남은 테마 중 첫 번째
  return { skin: ids.includes(DEFAULT_SKIN) ? DEFAULT_SKIN : ids[0] ?? DEFAULT_SKIN, side: false, narrow: false };
}

/** 처음 열 때 기억할 값 — 주소의 ?skin= 으로 아는 테마를 연 때만 그 값을 돌려준다(새로 고치거나 주소 없이 다시 열어도 유지되게).
    아무것도 고르지 않고 열기만 한 때는 null: 기억하지 않아야 기본 테마가 바뀌었을 때 따라간다. 테마 상자에서 고른 값은 setChoice 가 기억한다 */
export function choiceToRemember(query: string | null, ids: readonly string[]): string | null {
  if (!query) return null;
  const c = parseChoice(query);
  return ids.includes(c.skin) ? formatChoice(c) : null;
}

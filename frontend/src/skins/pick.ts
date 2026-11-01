/* 처음 열 때 쓸 화면 고르기 값 정하기 — 주소의 ?skin= 이 먼저, 없거나 모르는 테마면 브라우저에 기억한 값, 그것도 아니면 원래 화면.
   값은 '<테마 id>' 뒤에 꼬리표를 붙인 글자 하나: ':side'(좌측 메뉴 버전) · ':narrow'(이전 본문 폭). 예: tm464, tm464:side, base:narrow.
   꼬리표만 덧붙이는 형식이라 예전에 공유한 주소(?skin=tm464:side)도 그대로 열린다 */

/** 원래 화면(테마를 덧씌우지 않음) */
export const BASE = 'base';

export interface Choice {
  /** 테마 id 또는 BASE */
  skin: string;
  /** 좌측 메뉴 버전. 원래 화면은 늘 좌측 메뉴라 화면에는 쓰지 않고, 다음에 고를 테마를 위해 기억만 한다 */
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
    if (c.skin === BASE || ids.includes(c.skin)) return c;
  }
  return { skin: BASE, side: false, narrow: false };
}

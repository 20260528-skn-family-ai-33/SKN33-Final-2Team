/* 처음 열 때 쓸 화면 고르기 값 정하기 — 주소의 ?skin= 이 먼저, 없거나 모르는 테마면 브라우저에 기억한 값, 그것도 아니면 기본 테마(612 · 상단 메뉴).
   값은 '<테마 id>' 뒤에 꼬리표를 붙인 글자 하나: ':side'(좌측 메뉴 버전) · ':narrow'(이전 본문 폭). 예: tm464, tm464:side, tm590:narrow.
   꼬리표만 덧붙이는 형식이라 예전에 공유한 주소(?skin=tm464:side)도 그대로 열린다.
   예전의 '원래 화면'(base)은 고르기에서 뺐다. 기억해 둔 base 나 ?skin=base 는 모르는 테마로 보고 기본 테마로 연다 */

/** 기본 테마: templatemo 612 Parallax Starter · 상단 메뉴(2026-11-12 #211에서 464 Ultra Profile → 612).
    처음 열 때 고른 값을 브라우저에 기억하므로(skins/index.ts), 예전 기본값(464)을 기억한 브라우저는 그대로 464로 열린다 */
export const DEFAULT_SKIN = 'tm612';

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

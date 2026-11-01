/* 처음 열 때 쓸 화면 테마 정하기 — 주소의 ?skin= 이 먼저, 없거나 모르는 이름이면 브라우저에 기억한 값, 그것도 아니면 원래 화면.
   고른 값은 '<테마 id>'(상단 메뉴 버전) 또는 '<테마 id>:side'(좌측 메뉴 버전) */

/** 원래 화면(테마를 덧씌우지 않음) */
export const BASE = 'base';
/** 좌측 메뉴 버전을 뜻하는 꼬리표 */
export const SIDE = ':side';

/** 고른 값 → 테마 id 와 좌측 메뉴 여부 */
export function splitChoice(v: string): { skin: string; side: boolean } {
  const side = v.endsWith(SIDE);
  return { skin: side ? v.slice(0, -SIDE.length) : v, side };
}

export function pickSkin(query: string | null, saved: string | null, ids: readonly string[]): string {
  for (const v of [query, saved]) {
    if (v && (v === BASE || ids.includes(splitChoice(v).skin))) return v;
  }
  return BASE;
}

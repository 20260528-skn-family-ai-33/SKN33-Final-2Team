/* 처음 열 때 쓸 화면 테마 정하기 — 주소의 ?skin= 이 먼저, 없거나 모르는 이름이면 브라우저에 기억한 값, 그것도 아니면 원래 화면 */

/** 원래 화면(테마를 덧씌우지 않음) */
export const BASE = 'base';

export function pickSkin(query: string | null, saved: string | null, ids: readonly string[]): string {
  for (const v of [query, saved]) {
    if (v && (v === BASE || ids.includes(v))) return v;
  }
  return BASE;
}

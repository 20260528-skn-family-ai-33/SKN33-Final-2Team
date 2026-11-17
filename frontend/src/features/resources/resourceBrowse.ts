import type { ResourceSort } from '@/api/types/catalog';

/** 응답과 같은 조건의 목록 주소. 새 결과를 기다리는 동안 보이는 카드도 그 카드를 받은 조건으로 돌아가게 한다 */
export function listSearchOf(c: { kind: string; q: string; platform: string; sort: ResourceSort; page: number }): string {
  const s = new URLSearchParams();
  if (c.kind !== '전체') s.set('kind', c.kind);
  if (c.q) s.set('q', c.q);
  if (c.platform) s.set('platform', c.platform);
  if (c.sort !== 'default') s.set('sort', c.sort);
  if (c.page > 1) s.set('page', String(c.page));
  return s.toString();
}

/** 현재 페이지 양옆 radius개와 첫·마지막 번호 */
export function pageNumbers(page: number, pages: number, radius: number): number[] {
  const span = Math.min(radius * 2 + 1, pages);
  const first = Math.max(1, Math.min(page - radius, pages - span + 1));
  const numbers = Array.from({ length: span }, (_, i) => first + i);
  if (first > 1) numbers.unshift(1);
  if (numbers[numbers.length - 1] < pages) numbers.push(pages);
  return numbers;
}

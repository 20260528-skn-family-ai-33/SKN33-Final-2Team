/* 화면 표시용 형식 (5차 gp-core.js won·hrs, gp-app.js kb·sameJ 그대로) */

export const won = (n: number | null | undefined): string => (n ? Number(n).toLocaleString('ko-KR') + '원' : '0원');

export const hrs = (n: number | string | null | undefined): string => {
  const v = Number(n);
  return (Number.isInteger(v) ? v : v.toFixed(1)) + '시간';
};

export const kb = (n: number): string => `${Math.max(1, Math.round(n / 1024))}KB`;

export const clone = <T>(o: T): T => JSON.parse(JSON.stringify(o)) as T;

/** 객체 열쇠 순서가 달라도 같은 값이면 같다고 본다(서버를 거친 세부 사항 비교용) */
export const sortKeys = (o: unknown): unknown =>
  Array.isArray(o)
    ? o.map(sortKeys)
    : o && typeof o === 'object'
      ? Object.fromEntries(
          Object.keys(o as object)
            .sort()
            .map((k) => [k, sortKeys((o as Record<string, unknown>)[k])]),
        )
      : o;

export const sameJ = (a: unknown, b: unknown): boolean => JSON.stringify(sortKeys(a)) === JSON.stringify(sortKeys(b));

export const blank = (v: unknown): boolean => v === '' || v == null;

/** 이름 앞 한 글자(성)를 뺀 아바타 글자 */
export const avatarText = (name: string): string => name.slice(1);

/* 화면 표시용 형식 (5차 gp-core.js won·hrs, gp-app.js kb·sameJ 그대로) */

export const won = (n: number | null | undefined): string => (n ? Number(n).toLocaleString('ko-KR') + '원' : '0원');

export const hrs = (n: number | string | null | undefined): string => {
  if (n == null || n === '') return '시간 미확인';
  const v = Number(n);
  if (!Number.isFinite(v) || v < 0) return '시간 미확인';
  if (v === 0) return '0시간';
  if (v < 5 / 60) return '10분 미만';
  const minutes = Math.max(10, Math.round(v * 6) * 10);
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return [h ? `${h}시간` : '', m ? `${m}분` : ''].filter(Boolean).join(' ');
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

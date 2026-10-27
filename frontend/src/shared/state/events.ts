/* 초기화·단계 이동·로그아웃 뒤: 화면에만 둔 값을 비우라고 알린다 (5차 GP.onDataReset 사슬) */
type Fn = () => void;
const fns = new Set<Fn>();

export function onDataReset(fn: Fn): () => void {
  fns.add(fn);
  return () => fns.delete(fn);
}

export function dataReset(): void {
  fns.forEach((f) => f());
}

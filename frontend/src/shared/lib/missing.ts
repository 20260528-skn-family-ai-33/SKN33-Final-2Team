/* 빠뜨린 문항 알리기(역량 테스트·사후 점검 공통): 문구 없이 빨간 테두리(.is-missing)만 두고,
   다음 그림 때 화면 순서상 가장 위의 빠진 문항으로 옮겨 첫 보기에 커서를 둔다(#298) */
export function revealFirstMissing(selector = '.is-missing'): void {
  requestAnimationFrame(() => {
    const first = document.querySelector<HTMLElement>(selector);
    if (!first) return;
    first.scrollIntoView({ behavior: 'smooth', block: 'start' });
    first.querySelector<HTMLInputElement>('input[type="radio"]')?.focus({ preventScroll: true });
  });
}

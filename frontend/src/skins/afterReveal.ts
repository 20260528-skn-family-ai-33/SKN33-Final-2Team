/* 나타나기(reveal.ts)가 끝나기를 기다리는 도구 — 덩어리 안에서 따로 움직이는 것(예: 스킬 지도의 퍼져 나가기)이
   나타나기와 겹쳐 묻히지 않게, 그 덩어리가 거의 다 떠오른 뒤에 알려 준다.
   reveal.ts 는 불러오기만 해도 화면을 지켜보기 시작하므로, 화면 코드가 가져다 쓰는 이 부분은 따로 두었다(여기서는 붙어 있는 표시만 읽는다).
   나타나기를 쓰지 않는 테마이거나 이미 끝난 덩어리면 바로 알린다. 돌려주는 함수는 기다리기를 그만둔다 */

const SETTLED_AT_MS = 800; // 떠오르기(0.8초)가 끝난 뒤에 알린다

export function afterReveal(el: Element, done: () => void): () => void {
  const unit = el.closest<HTMLElement>('[data-rv]');
  let timer = 0;
  let mo: MutationObserver | null = null;
  const stop = (): void => {
    window.clearTimeout(timer);
    mo?.disconnect();
    mo = null;
  };
  const check = (): boolean => {
    const state = unit?.dataset.rv;
    if (!unit || !document.documentElement.hasAttribute('data-reveal') || !state || state === 'done') {
      stop();
      done();
      return true;
    }
    if (state === 'in' && !timer) {
      const delay = parseFloat(unit.style.getPropertyValue('--rv-d')) || 0;
      timer = window.setTimeout(() => {
        stop();
        done();
      }, delay + SETTLED_AT_MS);
    }
    return false;
  };
  if (check() || !unit) return stop;
  mo = new MutationObserver(() => void check());
  mo.observe(unit, { attributes: true, attributeFilter: ['data-rv'] });
  return stop;
}

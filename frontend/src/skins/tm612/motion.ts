/* 화면 테마 tm612 의 움직임 — 원본 템플릿 스크립트(templatemo-parallax-script.js)가 하던 일을 이 화면 구조에 맞게 옮긴 것.
   테마 폴더는 모두 한꺼번에 불러오므로(skins/index.ts 의 glob), 이 테마를 고른 때(<html data-skin="tm612">)만 움직인다.
   화면 코드(React)는 건드리지 않고, 바깥에서 CSS 변수와 data- 속성만 붙인다. 모양은 전부 skin.css 에 있다.

   1) 시차 배경: 스크롤 위치를 --tm612-py 로 넘긴다. 사진 층이 그 값만큼 느리게 따라오고, 원본과 같은 감속 곡선으로 미끄러진다.
   2) 메뉴: 80px 넘게 내려가면 <html data-tm612-scrolled> (원본의 .scrolled)
   원본의 세 번째 움직임인 나타나기(.reveal → .visible)는 다른 테마도 함께 쓰도록 skins/reveal.ts 로 옮겼다(index.ts 의 reveal: true).
   '움직임 줄이기' 설정이면 시차를 끈다(원본처럼 768px 이하에서도 끈다). */

const SKIN = 'tm612';
const root = document.documentElement;
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
const on = (): boolean => root.dataset.skin === SKIN;

/* ── 1) 시차 배경 · 2) 메뉴 ── */
const PARALLAX = 0.45; // 사진은 본문의 45% 속도로 올라간다
let ticking = false;

function update(): void {
  ticking = false;
  if (!on()) return;
  const y = window.scrollY;
  root.toggleAttribute('data-tm612-scrolled', y > 80);
  const still = reduce.matches || window.innerWidth <= 768;
  const shift = still ? 0 : -Math.min(y, window.innerHeight * 1.5) * PARALLAX;
  root.style.setProperty('--tm612-py', `${shift.toFixed(1)}px`);
  // 화면 높이의 20%~95% 를 내려가는 동안 머리 사진을 서서히 거둔다
  const fade = 1 - (y / window.innerHeight - 0.2) / 0.75;
  root.style.setProperty('--tm612-o', Math.max(0, Math.min(1, fade)).toFixed(3));
}

function onScroll(): void {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(update);
}

function leave(): void {
  root.removeAttribute('data-tm612-scrolled');
  root.style.removeProperty('--tm612-py');
  root.style.removeProperty('--tm612-o');
}

/* 테마를 바꾸면 바로 켜고 끈다 */
new MutationObserver(() => {
  if (on()) update();
  else leave();
}).observe(root, { attributes: true, attributeFilter: ['data-skin'] });

window.addEventListener('scroll', onScroll, { passive: true });
window.addEventListener('resize', onScroll, { passive: true });

update();

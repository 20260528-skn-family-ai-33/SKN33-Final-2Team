/* 나타나기 — 여러 테마가 함께 쓰는 움직임. 612 Parallax Starter 원본 스크립트의 .reveal → .visible 을 이 화면 구조에 맞게 옮긴 것.
   테마 index.ts 의 meta 에 reveal: true 를 두면, 그 테마를 고른 때 skins/index.ts 가 <html data-reveal> 을 붙이고 이 스크립트가 움직인다.
   화면 코드(React)는 건드리지 않고, 바깥에서 data-rv 속성과 --rv-d 변수만 붙인다. 모양은 reveal.css 에 있다.

   본문의 큰 덩어리(제목·카드·목록)가 화면에 들어올 때 한 번만 30px 아래에서 0.8초 동안 떠오른다.
   - 화면 아래쪽에 있는 덩어리: 스크롤해서 들어올 때
   - 화면을 연 직후 이미 보이는 덩어리: 위에서부터 조금씩 차례로
   - 사용자가 누르거나 입력한 뒤에 새로 생긴 내용은 기다리게 하지 않고 바로 보여 준다
   '움직임 줄이기' 설정이면 움직이지 않는다. */

const root = document.documentElement;
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
const on = (): boolean => root.hasAttribute('data-reveal');

const RV = 'rv'; // data-rv: wait(숨김) → in(떠오르는 중) → done
/* 자기 상자가 없는 묶음: 통째로가 아니라 안의 덩어리를 하나씩 나타낸다 */
const WRAPPERS = '.sec, .hp, .ls, .ls-grid, .me-page, .check-plan-groups';
/* 떠 있는 것·잠깐 보이는 것은 나타내기 대상에서 뺀다 */
const SKIP = '.ov, .sheet, .regp, .adm-panel, .toast, .fab, .chatbar, .gt-tip, .loading, [hidden]';
const FRESH_MS = 8000;
const STEP_MS = 70;
const DURATION_MS = 800;

let path = window.location.pathname;
let freshUntil = performance.now() + FRESH_MS;
let touched = false;

function enter(el: HTMLElement, order: number): void {
  const delay = Math.min(order, 6) * STEP_MS;
  el.style.setProperty('--rv-d', `${delay}ms`);
  // 숨긴 모양이 먼저 그려진 다음에 바꿔야 떠오르는 움직임이 생긴다
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      el.dataset[RV] = 'in';
      window.setTimeout(() => {
        el.dataset[RV] = 'done';
        el.style.removeProperty('--rv-d');
      }, DURATION_MS + delay + 80);
    }),
  );
}

const waiting = new Set<HTMLElement>();

const io = new IntersectionObserver(
  (entries) => {
    const seen = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
    seen.forEach((e, i) => {
      const el = e.target as HTMLElement;
      io.unobserve(el);
      waiting.delete(el);
      enter(el, i);
    });
  },
  { rootMargin: '0px 0px -60px 0px' },
);

function settle(el: HTMLElement): void {
  io.unobserve(el);
  waiting.delete(el);
  el.dataset[RV] = 'done';
}

/* 맨 아래로 한 번에 건너뛰면 화면에 들어온 적 없이 위로 지나간 덩어리가 생긴다 → 숨긴 채 두지 않고 바로 보이게 한다 */
function passed(): void {
  for (const el of waiting) {
    if (el.isConnected && el.getBoundingClientRect().bottom >= 0) continue;
    settle(el);
  }
}

function units(parent: Element, depth: number, out: HTMLElement[]): void {
  for (const el of parent.children) {
    if (!(el instanceof HTMLElement)) continue;
    const wrapper = el.matches(WRAPPERS) || (!el.className && (el.tagName === 'DIV' || el.tagName === 'SECTION'));
    if (wrapper && depth < 3 && el.children.length > 0) units(el, depth + 1, out);
    else out.push(el);
  }
}

function scan(): void {
  if (!on() || reduce.matches) return;
  const view = document.getElementById('view');
  if (!view) return;
  if (window.location.pathname !== path) {
    path = window.location.pathname;
    freshUntil = performance.now() + FRESH_MS;
    touched = false;
  }
  const list: HTMLElement[] = [];
  units(view, 0, list);
  const fresh = !touched && performance.now() < freshUntil;
  const edge = window.innerHeight - 60;
  let order = 0;
  for (const el of list) {
    if (el.dataset[RV]) continue;
    if (el.matches(SKIP)) {
      el.dataset[RV] = 'done';
      continue;
    }
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue; // 아직 그려지지 않은 것은 다음에 본다
    if (r.top >= edge) {
      el.dataset[RV] = 'wait';
      waiting.add(el);
      io.observe(el);
    } else if (fresh && r.bottom > 0) {
      el.dataset[RV] = 'wait';
      enter(el, order++);
    } else {
      el.dataset[RV] = 'done';
    }
  }
}

/* 나타나기를 쓰지 않는 테마로 바꾸면 기다리던 덩어리를 모두 끝난 것으로 둔다(다시 켜도 숨은 채 남지 않게) */
function leave(): void {
  for (const el of [...waiting]) settle(el);
}

let ticking = false;
function onScroll(): void {
  if (ticking || !on()) return;
  ticking = true;
  requestAnimationFrame(() => {
    ticking = false;
    passed();
  });
}

/* 화면 내용이 바뀔 때(그리기 전)마다 새 덩어리를 찾는다. 테마를 바꾸면 바로 켜고 끈다 */
new MutationObserver((records) => {
  if (records.some((m) => m.type === 'attributes' && m.target === root) && !on()) leave();
  scan();
}).observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-reveal'] });

window.addEventListener('scroll', onScroll, { passive: true });
window.addEventListener('pointerdown', () => { touched = true; }, { passive: true, capture: true });
window.addEventListener('keydown', () => { touched = true; }, { passive: true, capture: true });

scan();

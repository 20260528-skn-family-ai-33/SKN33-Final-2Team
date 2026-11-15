/* 화면 테마(스킨) 비교 — 템플릿 후보를 같은 화면·같은 데이터에서 바꿔 보며 비교하는 비교 브랜치 전용 장치
   규칙
   - 테마 하나 = 폴더 하나(skins/<id>/): index.ts(이름·출처·글꼴) + skin.css + 사진. 테마 때문에 다른 곳의 화면 코드는 고치지 않는다.
     움직임이 필요한 테마는 같은 폴더에 스크립트를 둘 수 있다(예: tm612/motion.ts). 폴더를 모두 한꺼번에 불러오므로 스크립트는
     그 테마를 고른 때만 동작하고, 화면 코드를 고치지 않고 바깥에서 CSS 변수·data- 속성만 붙여야 한다.
   - 여러 테마가 함께 쓰는 움직임은 나타나기 하나다(reveal.ts · reveal.css · 612 원본에서 옮김). meta 에 reveal: true 를 둔 테마를
     고르면 <html data-reveal> 이 붙고 그때만 움직인다. 최종 결정 때 고른 테마가 이것을 쓰면 두 파일도 함께 가져간다.
   - 폴더 이름은 templatemo 템플릿 번호를 따라 tm<번호>. 고르기 상자에는 폴더 이름 순서로 나온다.
     후보는 2026-11-11에 7종(464 · 486 · 503 · 557 · 590 · 606 · 612)으로 줄였고(#197), 묶음(education · 그 외) 구분도 그때 뺐다.
   - skin.css 는 전부 :root[data-skin="<id>"] { … } 안에 적는다 → 고르지 않은 테마는 화면에 영향이 없다.
   - 기본 테마는 612 Parallax Starter · 상단 메뉴(pick.ts DEFAULT_SKIN · 2026-11-12 #211에서 464 → 612). 테마를 덧씌우지 않은 '원래 화면'은 고르기에서 뺐지만,
     원래 화면의 CSS(styles/gp*.css)는 모든 테마가 그 위에 얹히므로 그대로 둔다.
   - 테마마다 메뉴 위치가 다른 두 버전: 상단 메뉴(기본) · 좌측 메뉴(<html data-nav="side">, 예전 원래 화면과 같은 배치).
     좌측 메뉴는 화면 폭이 1200px 이상일 때만 그린다(pick.ts SIDE_NAV_MIN_WIDTH · 좁으면 상단 메뉴로).
     skin.css 에서 상단 메뉴 규칙은 &:not([data-nav="side"]) { … }, 좌측 메뉴 규칙은 &[data-nav="side"] { … } 안에 둔다.
   - 본문 폭도 두 가지: 넓은 본문 폭(기본 · gp.css) · 이전 본문 폭(<html data-width="narrow"> · width.css). 테마와 상관없이 고른다.
   - 테마 추가 = 폴더 추가, 빼기 = 폴더 삭제. 이 파일이 폴더를 알아서 찾는다.
   - 고를 때: 왼쪽 아래 '화면 테마' 상자(접힌 채 시작, 펼치면 테마 → 메뉴 위치 → 본문 폭 · 로그인 화면은 테마만), 또는 주소 뒤 ?skin=<id>[:side][:narrow]
     (형식은 pick.ts). 상자에서 고른 값과 ?skin= 으로 연 값만 이 브라우저에 기억한다. 열기만 해서는 기억하지 않으므로
     아무것도 고르지 않은 브라우저는 기본 테마가 바뀌면 따라간다(2026-11-12 #211).
   - 최종 결정 뒤에는 최신 main 에서 새 브랜치를 만들고 고른 폴더만 가져가 정식으로 적용한다. 이 고르기 장치(width.css 포함)는 가져가지 않는다. */
import { type Choice, choiceToRemember, formatChoice, pickChoice, SIDE_NAV_MIN_WIDTH } from './pick';
import './width.css';
import './reveal.css';
import './reveal';

export interface SkinMeta {
  name: string;
  /** 원본 템플릿 주소 */
  source: string;
  /** 이 테마를 고른 때만 불러올 글꼴 CSS 주소 */
  fonts?: string[];
  /** 본문 덩어리가 화면에 들어올 때 한 번 떠오르는 나타나기(reveal.ts)를 쓴다 */
  reveal?: boolean;
}
export interface Skin extends SkinMeta {
  id: string;
}

/* 기억하는 키. 2026-11-12 #211에서 예전 키(growpath.skin)를 바꿨다 — 예전에는 열기만 해도 고른 값을 저장해서, 예전 기본값(464)이
   직접 고른 값과 구분 없이 남아 있었다. 키를 바꿔 모든 브라우저가 한 번은 기본 테마(612)로 열리게 하고, 예전 키는 지운다 */
const KEY = 'growpath.skin.v2';
const OLD_KEY = 'growpath.skin';
const mods = import.meta.glob<{ default: SkinMeta }>('./*/index.ts', { eager: true });

export const SKINS: Skin[] = Object.entries(mods)
  .map(([path, m]) => ({ ...m.default, id: path.split('/')[1] }))
  .sort((a, b) => a.id.localeCompare(b.id));
const IDS = SKINS.map((s) => s.id);

/* 저장소를 못 쓰는 브라우저(사생활 보호 모드 등)에서는 기억만 못 하고, 지금 화면에는 그대로 적용한다 */
function load(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}
function save(v: string): void {
  try {
    localStorage.setItem(KEY, v);
  } catch {
    /* 위 설명대로 기억만 건너뜀 */
  }
}
function forgetOld(): void {
  try {
    localStorage.removeItem(OLD_KEY);
  } catch {
    /* 위 설명대로 건너뜀 */
  }
}

/* 좌측 메뉴는 넓은 화면에서만 쓴다(#227): 메뉴 248px 를 빼면 본문이 좁아져 작성 단계 줄이 잘렸다.
   이 폭보다 좁으면 고른 값은 그대로 기억한 채 상단 메뉴로 그리고, 다시 넓히면 좌측 메뉴로 돌아온다 */
const sideFits = window.matchMedia(`(min-width: ${SIDE_NAV_MIN_WIDTH}px)`);

const query = new URLSearchParams(window.location.search).get('skin');
let current: Choice = pickChoice(query, load(), IDS);

function apply(c: Choice): void {
  const skin = SKINS.find((s) => s.id === c.skin);
  const root = document.documentElement;
  const skinChanged = root.dataset.skin !== skin?.id;
  if (skin) root.dataset.skin = skin.id;
  else delete root.dataset.skin;
  if (skin?.reveal) root.dataset.reveal = '';
  else delete root.dataset.reveal;
  if (skin && c.side && sideFits.matches) root.dataset.nav = 'side';
  else delete root.dataset.nav;
  if (c.narrow) root.dataset.width = 'narrow';
  else delete root.dataset.width;
  current = c;
  // 메뉴 위치·본문 폭만 바꿀 때는 글꼴을 다시 불러오지 않는다(글자가 깜빡이지 않게)
  if (!skinChanged) return;
  document.querySelectorAll('link[data-skin-font]').forEach((el) => el.remove());
  for (const href of skin?.fonts || []) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.skinFont = '';
    document.head.append(link);
  }
}

export function currentChoice(): Choice {
  return current;
}

/** 고르기 상자에서 바꿀 때: 바로 적용하고 기억한다. 주소에 ?skin= 이 남아 있으면 새로 고칠 때 되돌아가지 않게 지운다 */
export function setChoice(c: Choice): void {
  apply(c);
  save(formatChoice(c));
  const url = new URL(window.location.href);
  if (url.searchParams.has('skin')) {
    url.searchParams.delete('skin');
    window.history.replaceState(window.history.state, '', url);
  }
}

apply(current);
sideFits.addEventListener('change', () => apply(current));
forgetOld();
// 열기만 한 때는 기억하지 않는다(?skin= 으로 연 때만 · pick.ts choiceToRemember)
const remember = choiceToRemember(query, IDS);
if (remember) save(remember);

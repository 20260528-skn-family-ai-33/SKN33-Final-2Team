/* 화면 테마 — 라이트 모드(464 Ultra Profile)와 다크 모드(612 Parallax Starter) 두 가지(2026-11-17 · 나머지 5종은 지웠다)
   규칙
   - 테마 하나 = 폴더 하나(skins/<id>/): index.ts(이름·출처·글꼴) + skin.css + 사진. 모드와 폴더의 짝은 pick.ts MODE_SKIN.
     움직임이 필요한 테마는 같은 폴더에 스크립트를 둘 수 있다(예: tm612/motion.ts). 폴더를 모두 한꺼번에 불러오므로 스크립트는
     그 테마를 고른 때만 동작하고, 화면 코드를 고치지 않고 바깥에서 CSS 변수·data- 속성만 붙여야 한다.
   - 두 테마가 함께 쓰는 움직임은 나타나기 하나다(reveal.ts · reveal.css · 612 원본에서 옮김). meta 에 reveal: true 를 둔 테마를
     고르면 <html data-reveal> 이 붙고 그때만 움직인다.
   - skin.css 는 전부 :root[data-skin="<id>"] { … } 안에 적는다 → 고르지 않은 테마는 화면에 영향이 없다.
     원래 화면의 CSS(styles/gp*.css)는 두 테마가 그 위에 얹히므로 그대로 둔다.
   - 메뉴는 상단 메뉴 하나다. 좌측 메뉴 버전(data-nav="side")과 메뉴 접기는 2026-11-17 앱에서 뺐다.
   - 본문 폭은 두 가지: 넓은 본문 폭(기본 · gp.css) · 이전 본문 폭(<html data-width="narrow"> · width.css). 테마와 상관없이 고른다.
   - 저대비(#322)는 켜고 끄는 값 하나다(<html data-contrast="low">). 라이트·다크 두 모드가 함께 쓴다.
     색은 테마마다 달라 각 skin.css 맨 끝의 '저대비' 묶음이 정한다.
   - 바꾸는 곳: 상단 메뉴와 로그인 화면 우측 블록의 해·달 버튼(라이트·다크), 상단 메뉴의 본문 폭 · 저대비 버튼(ThemeControls.tsx).
     주소 뒤 ?skin=<id>[:narrow][:low] 로도 연다(형식은 pick.ts · 로그인 화면 그림 찍기 스크립트가 쓴다).
     버튼으로 바꾼 값과 ?skin= 으로 연 값만 이 브라우저에 기억한다. 열기만 해서는 기억하지 않으므로
     아무것도 고르지 않은 브라우저는 기본 테마가 바뀌면 따라간다(2026-11-12 #211). */
import { create } from 'zustand';
import { type Choice, choiceToRemember, formatChoice, MODE_SKIN, type Mode, pickChoice } from './pick';
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
   직접 고른 값과 구분 없이 남아 있었다. 키를 바꿔 모든 브라우저가 한 번은 기본 테마(612)로 열리게 하고, 예전 키는 지운다.
   좌측 메뉴 접기 값(growpath.side)도 메뉴를 빼면서 함께 지운다 */
const KEY = 'growpath.skin.v2';
const OLD_KEYS = ['growpath.skin', 'growpath.side'];
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
    for (const k of OLD_KEYS) localStorage.removeItem(k);
  } catch {
    /* 위 설명대로 건너뜀 */
  }
}

const query = new URLSearchParams(window.location.search).get('skin');

function apply(c: Choice): void {
  const skin = SKINS.find((s) => s.id === c.skin);
  const root = document.documentElement;
  const skinChanged = root.dataset.skin !== skin?.id;
  if (skin) root.dataset.skin = skin.id;
  else delete root.dataset.skin;
  if (skin?.reveal) root.dataset.reveal = '';
  else delete root.dataset.reveal;
  if (c.narrow) root.dataset.width = 'narrow';
  else delete root.dataset.width;
  if (c.lowContrast) root.dataset.contrast = 'low';
  else delete root.dataset.contrast;
  // 본문 폭 · 저대비만 바꿀 때는 글꼴을 다시 불러오지 않는다(글자가 깜빡이지 않게)
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

/** 지금 고른 값. 버튼들이 이것을 읽어 눌린 모양을 맞춘다(로그인 화면 · 상단 메뉴 · 관리자 메뉴가 함께 본다) */
export const useChoice = create<Choice>(() => pickChoice(query, load(), IDS));

/** 버튼으로 바꿀 때: 바로 적용하고 기억한다. 주소에 ?skin= 이 남아 있으면 새로 고칠 때 되돌아가지 않게 지운다 */
export function setChoice(next: Partial<Choice>): void {
  const c = { ...useChoice.getState(), ...next };
  apply(c);
  useChoice.setState(c, true);
  save(formatChoice(c));
  const url = new URL(window.location.href);
  if (url.searchParams.has('skin')) {
    url.searchParams.delete('skin');
    window.history.replaceState(window.history.state, '', url);
  }
}

export function setMode(mode: Mode): void {
  setChoice({ skin: MODE_SKIN[mode] });
}

apply(useChoice.getState());
forgetOld();
// 열기만 한 때는 기억하지 않는다(?skin= 으로 연 때만 · pick.ts choiceToRemember)
const remember = choiceToRemember(query, IDS);
if (remember) save(remember);

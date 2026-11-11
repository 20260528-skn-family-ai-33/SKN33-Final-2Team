/* 화면 테마(스킨) 비교 — 템플릿 후보를 같은 화면·같은 데이터에서 바꿔 보며 비교하는 비교 브랜치 전용 장치
   규칙
   - 테마 하나 = 폴더 하나(skins/<id>/): index.ts(이름·묶음·출처·글꼴) + skin.css + 사진. 테마 때문에 다른 곳의 화면 코드는 고치지 않는다.
     움직임이 필요한 테마는 같은 폴더에 스크립트를 둘 수 있다(예: tm612/motion.ts). 폴더를 모두 한꺼번에 불러오므로 스크립트는
     그 테마를 고른 때만 동작하고, 화면 코드를 고치지 않고 바깥에서 CSS 변수·data- 속성만 붙여야 한다.
   - 묶음(group): templatemo 에서 education 태그가 붙은 템플릿은 'education', 나머지(자매 사이트 Tooplate 템플릿 포함)는 'other'.
     고르기 상자의 첫 칸이 이 묶음이다. 폴더 이름은 templatemo 는 tm<번호>, Tooplate 는 tp<번호>.
   - skin.css 는 전부 :root[data-skin="<id>"] { … } 안에 적는다 → 고르지 않은 테마는 화면에 영향이 없다.
   - 기본 테마는 464 Ultra Profile · 상단 메뉴(pick.ts DEFAULT_SKIN). 테마를 덧씌우지 않은 '원래 화면'은 고르기에서 뺐지만,
     원래 화면의 CSS(styles/gp*.css)는 모든 테마가 그 위에 얹히므로 그대로 둔다.
   - 테마마다 메뉴 위치가 다른 두 버전: 상단 메뉴(기본) · 좌측 메뉴(<html data-nav="side">, 예전 원래 화면과 같은 배치).
     skin.css 에서 상단 메뉴 규칙은 &:not([data-nav="side"]) { … }, 좌측 메뉴 규칙은 &[data-nav="side"] { … } 안에 둔다.
   - 본문 폭도 두 가지: 넓은 본문 폭(기본 · gp.css) · 이전 본문 폭(<html data-width="narrow"> · width.css). 테마와 상관없이 고른다.
   - 테마 추가 = 폴더 추가, 빼기 = 폴더 삭제. 이 파일이 폴더를 알아서 찾는다.
   - 고를 때: 왼쪽 아래 '화면 테마' 상자(묶음 → 테마 → 메뉴 위치 → 본문 폭), 또는 주소 뒤 ?skin=<id>[:side][:narrow]
     (형식은 pick.ts). 고른 값은 이 브라우저에 기억한다.
   - 최종 결정 뒤에는 최신 main 에서 새 브랜치를 만들고 고른 폴더만 가져가 정식으로 적용한다. 이 고르기 장치(width.css 포함)는 가져가지 않는다. */
import { type Choice, formatChoice, pickChoice } from './pick';
import './width.css';

export type SkinGroup = 'education' | 'other';
export const GROUPS: { id: SkinGroup; name: string }[] = [
  { id: 'education', name: 'education 템플릿' },
  { id: 'other', name: '그 외 템플릿' },
];

export interface SkinMeta {
  name: string;
  /** templatemo 의 education 태그가 붙은 템플릿이면 'education', 아니면(Tooplate 포함) 'other' */
  group: SkinGroup;
  /** 원본 템플릿 주소 */
  source: string;
  /** 이 테마를 고른 때만 불러올 글꼴 CSS 주소 */
  fonts?: string[];
}
export interface Skin extends SkinMeta {
  id: string;
}

const KEY = 'growpath.skin';
const mods = import.meta.glob<{ default: SkinMeta }>('./*/index.ts', { eager: true });

export const SKINS: Skin[] = Object.entries(mods)
  .map(([path, m]) => ({ ...m.default, id: path.split('/')[1] }))
  .sort((a, b) => a.id.localeCompare(b.id));

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

let current: Choice = pickChoice(new URLSearchParams(window.location.search).get('skin'), load(), SKINS.map((s) => s.id));

function apply(c: Choice): void {
  const skin = SKINS.find((s) => s.id === c.skin);
  const root = document.documentElement;
  const skinChanged = root.dataset.skin !== skin?.id;
  if (skin) root.dataset.skin = skin.id;
  else delete root.dataset.skin;
  if (skin && c.side) root.dataset.nav = 'side';
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
save(formatChoice(current));

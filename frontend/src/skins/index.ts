/* 화면 테마(스킨) 비교 — 템플릿 후보를 같은 화면·같은 데이터에서 바꿔 보며 비교하는 비교 브랜치 전용 장치
   규칙
   - 테마 하나 = 폴더 하나(skins/<id>/): index.ts(이름·출처·글꼴) + skin.css + 사진. 테마 때문에 다른 곳의 화면 코드는 고치지 않는다.
   - skin.css 는 전부 :root[data-skin="<id>"] { … } 안에 적는다 → 고르지 않은 테마는 화면에 영향이 없다.
   - 테마마다 메뉴 위치가 다른 두 버전: 상단 메뉴(기본) · 좌측 메뉴(<html data-nav="side">, 원래 화면과 같은 배치).
     skin.css 에서 상단 메뉴 규칙은 &:not([data-nav="side"]) { … }, 좌측 메뉴 규칙은 &[data-nav="side"] { … } 안에 둔다.
   - 테마 추가 = 폴더 추가, 빼기 = 폴더 삭제. 이 파일이 폴더를 알아서 찾는다.
   - 고를 때: 왼쪽 아래 '화면 테마' 상자, 또는 주소 뒤 ?skin=<id> · ?skin=<id>:side (?skin=base 는 원래 화면). 고른 값은 이 브라우저에 기억한다.
   - 최종 결정 뒤에는 최신 main 에서 새 브랜치를 만들고 고른 폴더만 가져가 정식으로 적용한다. 이 고르기 장치는 가져가지 않는다. */
import { BASE, pickSkin, SIDE, splitChoice } from './pick';

export interface SkinMeta {
  name: string;
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
function save(id: string): void {
  try {
    localStorage.setItem(KEY, id);
  } catch {
    /* 위 설명대로 기억만 건너뜀 */
  }
}

function apply(choice: string): void {
  const { skin: id, side } = splitChoice(choice);
  const skin = SKINS.find((s) => s.id === id);
  const root = document.documentElement;
  if (skin) root.dataset.skin = skin.id;
  else delete root.dataset.skin;
  if (skin && side) root.dataset.nav = 'side';
  else delete root.dataset.nav;
  document.querySelectorAll('link[data-skin-font]').forEach((el) => el.remove());
  for (const href of skin?.fonts || []) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.skinFont = '';
    document.head.append(link);
  }
}

export function currentSkin(): string {
  const { skin, nav } = document.documentElement.dataset;
  return skin ? skin + (nav === 'side' ? SIDE : '') : BASE;
}

/** 고르기 상자에서 바꿀 때: 바로 적용하고 기억한다. 주소에 ?skin= 이 남아 있으면 새로 고칠 때 되돌아가지 않게 지운다 */
export function setSkin(id: string): void {
  apply(id);
  save(id);
  const url = new URL(window.location.href);
  if (url.searchParams.has('skin')) {
    url.searchParams.delete('skin');
    window.history.replaceState(window.history.state, '', url);
  }
}

const first = pickSkin(new URLSearchParams(window.location.search).get('skin'), load(), SKINS.map((s) => s.id));
apply(first);
save(first);

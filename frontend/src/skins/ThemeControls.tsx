/* 화면 모드·본문 폭 버튼 — 예전 왼쪽 아래 '화면 테마' 고르기 상자를 대신한다(2026-11-17).
   - ThemeToggle: 라이트(464) ↔ 다크(612)를 오가는 버튼 하나. 바꿀 모드의 아이콘(라이트에서는 달 · 다크에서는 해)을 보인다.
     로그인 화면 우측 블록과 상단 메뉴에 둔다.
   - WidthToggle: 넓은 본문 폭 ↔ 이전 본문 폭. 로그인한 화면의 상단 메뉴에만 둔다(로그인 화면은 본문 폭이 따로 정해져 있다).
   색은 놓인 자리의 글자색(currentColor)을 따라 밝은 메뉴 · 어두운 메뉴 어디서나 읽힌다(controls.css) */
import { Icon } from '@/shared/ui/Icon';
import { setChoice, setMode, useChoice } from '@/skins';
import { modeOf, type Mode } from './pick';
import './controls.css';

/* 버튼 하나: 지금과 반대 모드의 아이콘을 보여 주고, 누르면 그 모드로 바꾼다(라이트에서는 달 · 다크에서는 해) */
const NEXT: Record<Mode, { mode: Mode; icon: string; label: string }> = {
  light: { mode: 'dark', icon: 'moon', label: '다크 모드로 바꾸기' },
  dark: { mode: 'light', icon: 'sun', label: '라이트 모드로 바꾸기' },
};

export function ThemeToggle() {
  const next = NEXT[useChoice((c) => modeOf(c.skin))];
  return (
    <button type="button" className="theme-tg" aria-label={next.label} title={next.label} onClick={() => setMode(next.mode)}>
      <Icon name={next.icon} />
    </button>
  );
}

export function WidthToggle() {
  const narrow = useChoice((c) => c.narrow);
  const label = narrow ? '본문 넓게 보기' : '본문 좁게 보기';
  return (
    <button type="button" className="width-tg" aria-label={label} title={label} onClick={() => setChoice({ narrow: !narrow })}>
      <Icon name={narrow ? 'widen' : 'narrow'} />
    </button>
  );
}

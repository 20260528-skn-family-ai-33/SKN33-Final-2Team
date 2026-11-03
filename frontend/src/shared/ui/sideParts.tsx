/* 좌측 메뉴 조각 — 직원 메뉴(app/layout/Sidebar)와 관리자 메뉴(features/admin/AdminSide)가 함께 쓴다 */
import type { ReactNode } from 'react';
import { useGo } from '@/shared/hooks/useGo';
import { setTheme, THEMES, useTheme } from '@/shared/state/theme';
import { Icon } from './Icon';
import { paths } from '@/app/paths';


export function NavLink({ to, active, icon, label, dot }: { to: string; active: boolean; icon: string; label: ReactNode; dot?: boolean }) {
  const go = useGo();
  return (
    <a
      href={to}
      className={active ? 'on' : ''}
      onClick={(e) => {
        e.preventDefault();
        go(to);
      }}
    >
      <Icon name={icon} />
      {label}
      {dot ? <span className="dot" aria-label="알림" /> : null}
    </a>
  );
}

export function Brand() {
  const go = useGo();

  return (
    <a
      className="brand"
      href={paths.home}
      aria-label="GrowPath 홈으로 이동"
      style={{ color: 'inherit', textDecoration: 'none' }}
      onClick={(e) => {
        e.preventDefault();
        go(paths.home);
      }}
    >
      <span className="logo">
        <Icon name="logo" />
      </span>
      GrowPath
    </a>
  );
}

export function ThemePicker({ compact = false }: { compact?: boolean }) {
  const theme = useTheme((s) => s.theme);
  return (
    <div className={compact ? 'theme-compact' : undefined}>
      <div className="foot-lbl">{compact ? '테마' : '테마 색상'}</div>
      <div className="theme" role="group" aria-label="테마 색상">
        {THEMES.map(([k, n, c]) => (
          <button type="button" key={k} style={{ background: c }} className={theme === k ? 'on' : ''} title={n} aria-label={n} aria-pressed={theme === k} onClick={() => setTheme(k)} />
        ))}
      </div>
    </div>
  );
}

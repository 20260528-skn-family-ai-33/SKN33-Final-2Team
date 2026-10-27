/* 좌측 메뉴 조각 — 직원 메뉴(app/layout/Sidebar)와 관리자 메뉴(features/admin/AdminSide)가 함께 쓴다 */
import type { ReactNode } from 'react';
import { useGo } from '@/shared/hooks/useGo';
import { setTheme, THEMES, useTheme } from '@/shared/state/theme';
import { Icon } from './Icon';

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

export const Brand = () => (
  <div className="brand">
    <span className="logo">
      <Icon name="logo" />
    </span>
    GrowPath
  </div>
);

export function ThemePicker() {
  const theme = useTheme((s) => s.theme);
  return (
    <div>
      <div className="foot-lbl">테마 색상</div>
      <div className="theme" role="group" aria-label="테마 색상">
        {THEMES.map(([k, n, c]) => (
          <button key={k} style={{ background: c }} className={theme === k ? 'on' : ''} title={n} aria-label={n} onClick={() => setTheme(k)} />
        ))}
      </div>
    </div>
  );
}

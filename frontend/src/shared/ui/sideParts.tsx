/* 좌측 메뉴 조각 — 직원 메뉴(app/layout/Sidebar)와 관리자 메뉴(features/admin/AdminSide)가 함께 쓴다 */
import type { ReactNode } from 'react';
import { useGo } from '@/shared/hooks/useGo';
import { toggleSideMenu, useSideMenu } from '@/shared/state/sideMenu';
import { Icon } from './Icon';
import { paths } from '@/app/paths';


export function NavLink({ to, active, icon, label, dot }: { to: string; active: boolean; icon: string; label: ReactNode; dot?: boolean }) {
  const go = useGo();
  // 메뉴를 접으면 글자는 화면에서만 숨기므로(읽기 프로그램은 그대로 읽음), 마우스를 올리면 이름이 보이게 한다
  const collapsed = useSideMenu((s) => s.collapsed);
  return (
    <a
      href={to}
      className={active ? 'on' : ''}
      title={collapsed && typeof label === 'string' ? label : undefined}
      onClick={(e) => {
        e.preventDefault();
        go(to);
      }}
    >
      <Icon name={icon} />
      <span className="nav-l">{label}</span>
      {dot ? <span className="dot" aria-label="알림" /> : null}
    </a>
  );
}

/** 좌측 메뉴 접기·펼치기. 넓은 화면의 좌측 메뉴에서만 보인다(상단 메뉴 테마·좁은 화면에서는 숨김 · styles/gp.css) */
export function SideToggle() {
  const collapsed = useSideMenu((s) => s.collapsed);
  const label = collapsed ? '메뉴 펼치기' : '메뉴 접기';
  return (
    <button
      type="button"
      className="side-toggle"
      aria-label={label}
      aria-expanded={!collapsed}
      aria-controls="side"
      title={collapsed ? label : undefined}
      onClick={toggleSideMenu}
    >
      <Icon name={collapsed ? 'right' : 'left'} />
      <span className="lbl">{label}</span>
    </button>
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
      <span className="brand-t">GrowPath</span>
    </a>
  );
}

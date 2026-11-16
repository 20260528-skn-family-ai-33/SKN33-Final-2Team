/* 메뉴 조각 — 직원 메뉴(app/layout/Sidebar)와 관리자 메뉴(features/admin/AdminSide)가 함께 쓴다.
   상단 메뉴 한 가지다(2026-11-17 좌측 메뉴 · 메뉴 접기를 뺐다). 세 칸으로 나눈다(배치는 topNav.css):
   .nav-l 로고·버전 | .nav-c 주 메뉴(가운데) | .nav-r 화면 도구 · 알림 · 계정 · 로그아웃 */
import type { ReactNode } from 'react';
import { useGo } from '@/shared/hooks/useGo';
import { ThemeToggle, WidthToggle } from '@/skins/ThemeControls';
import { logoutAndReset } from '@/features/auth/actions';
import { Icon } from './Icon';
import './topNav.css';
import { paths } from '@/app/paths';


export function NavLink({ to, active, icon, label, dot, tour }: { to: string; active: boolean; icon: string; label: ReactNode; dot?: boolean; tour?: string }) {
  const go = useGo();
  return (
    <a
      href={to}
      className={active ? 'on' : ''}
      data-tour={tour}
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

/** 로그아웃: 메뉴 맨 오른쪽의 아이콘 버튼(이름은 aria-label · title 로) */
export function LogoutButton() {
  const go = useGo();
  return (
    <button type="button" className="logout" aria-label="로그아웃" title="로그아웃" onClick={() => void logoutAndReset(go)}>
      <Icon name="logout" />
    </button>
  );
}

/** 메뉴 오른쪽 끝의 화면 도구: 본문 폭 · 라이트·다크 모드(예전 왼쪽 아래 '화면 테마' 상자를 대신한다 · skins/ThemeControls) */
export function ViewTools() {
  return (
    <div className="view-tools">
      <WidthToggle />
      <ThemeToggle />
    </div>
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

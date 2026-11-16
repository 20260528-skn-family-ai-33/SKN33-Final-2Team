/* 관리자 메뉴 (5차 gp-admin.js sidebar · 테마가 상단 메뉴로 그린다) — 개요 · 데이터 셋 · 변경 이력. 미리보기 화면은 그 데이터 메뉴를 강조한다 */
import { useLocation } from 'react-router';
import { paths } from '@/app/paths';
import { AdminDemoTools } from '@/features/demo/DemoTools';
import { useSession } from '@/shared/state/session';
import { AppVersion } from '@/shared/ui/AppVersion';
import { Brand, LogoutButton, NavLink, ViewTools } from '@/shared/ui/sideParts';
import { useUpload } from './adminData';
import { DS, REG } from './datasets';

function useActive(): string {
  const { pathname } = useLocation();
  const [, , kind, arg] = pathname.split('/');
  /* 미리보기 화면과 같은 캐시를 본다(요청은 한 번만 감) */
  const up = useUpload(kind === 'uploads' ? arg : '');
  if (kind === 'data') return arg || 'admin';
  if (kind === 'regulations') return 'regulations';
  if (kind === 'uploads') return up.data?.dataset || 'admin-history';
  if (kind === 'history') return 'admin-history';
  return 'admin';
}

export function AdminSide() {
  const acct = useSession((s) => s.account);
  const active = useActive();
  const name = acct && acct.accountType === 'admin' ? acct.admin.name : '';
  return (
    <>
      <div className="nav-l">
        <Brand />
        <AppVersion />
      </div>
      <div className="nav-c">
        <nav className="nav" aria-label="관리자 메뉴">
          <NavLink to={paths.admin} active={active === 'admin'} icon="db" label="개요" />
          <NavLink to={paths.adminData('hr')} active={active === 'hr'} icon={DS.hr.icon} label={DS.hr.title} />
          <NavLink to={paths.adminRegulations} active={active === 'regulations'} icon={REG.icon} label={REG.title} />
          <NavLink to={paths.adminData('education')} active={active === 'education'} icon={DS.education.icon} label={DS.education.title} />
          <NavLink to={paths.adminHistory} active={active === 'admin-history'} icon="history" label="변경 이력" />
        </nav>
      </div>
      <div className="nav-r">
        <AdminDemoTools />
        <ViewTools />
        <span className="nav-sep" aria-hidden="true" />
        <div className="me adm">
          <span className="avatar">관</span>
          <div className="grow">
            <b>{name || '관리자'}</b>
            <small>관리자 전용 계정 · 데이터 관리</small>
          </div>
        </div>
        <LogoutButton />
      </div>
    </>
  );
}

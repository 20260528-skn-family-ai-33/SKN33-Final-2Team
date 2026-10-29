/* 앱 틀 (5차 gp-core.js boot·render) — 상단 띠 · 좌측 메뉴 · 본문. 화면마다 정한 메뉴 강조·제목·폭(handle)을 읽어 그린다 */
import { useEffect, useState, type ReactNode } from 'react';
import { Navigate, Outlet, useLocation, useMatches } from 'react-router';
import { paths } from '@/app/paths';
import { AdminSide } from '@/features/admin/AdminSide';
import { AssistantHost } from '@/features/assistant/AssistantHost';
import { DraftNavGuard } from '@/features/draft/stale';
import { connFor, PROV, useAi, useAiMode } from '@/shared/state/ai';
import { isSup, meOf, useSession } from '@/shared/state/session';
import { updateWs } from '@/shared/state/workspace';
import { SheetHost, ToastHost } from '@/shared/ui/SheetHost';
import { Loading } from '@/shared/ui/parts';
import { AiBox, Sidebar } from './Sidebar';

export interface ScreenHandle {
  nav?: string;
  title?: string;
  width?: string;
  role?: 'employee' | 'mgr' | 'admin' | 'public';
}

function ModeChip() {
  const [open, setOpen] = useState(false);
  const acct = useSession((s) => s.account);
  const { mode, choice, checked, conn } = useAiMode();
  const server = useAi((s) => s.status.server);

  if (!acct) return <span className="mode" />;

  if (acct.accountType === 'admin') {
    return <span className="mode api">관리자 화면</span>;
  }

  const connection = connFor('all', conn);
  let color = 'gray';
  let status = '사용 불가';

  if (mode === 'mock') {
    color = 'blue';
    status = '시연용 가데이터';
  } else if (!checked) {
    color = 'orange';
    status = '연결 확인 중';
  } else if (server === false) {
    color = 'red';
    status = '연결 안 됨';
  } else if (mode !== 'off') {
    switch (connection.state) {
      case 'ok':
        color = 'green';
        status = '연결됨';
        break;
      case 'error':
        color = 'red';
        status = '연결 안 됨';
        break;
      case 'cold':
        color = 'orange';
        status = '모델 준비 중';
        break;
      default:
        color = 'orange';
        status = '연결 확인 중';
    }
  }

  const label = mode === 'mock' ? '시연용 가데이터' : PROV[choice];

  return (
    <div className="api-picker">
      <button
        type="button"
        className={`api-picker-button ${color}`}
        aria-label={`${label} · ${status}. AI 모델 선택`}
        aria-expanded={open}
        aria-controls="api-picker-panel"
        title={status}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setOpen(false);
        }}
      >
        <span className="api-picker-dot" />
        {label}
        <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>

      {open ? (
        <div
          id="api-picker-panel"
          className="api-picker-panel"
          onKeyDown={(event) => {
            if (event.key === 'Escape') setOpen(false);
          }}
        >
          <AiBox />
        </div>
      ) : null}
    </div>
  );
}

function useHandle(): ScreenHandle {
  const matches = useMatches();
  const h = [...matches].reverse().find((m) => m.handle)?.handle as ScreenHandle | undefined;
  return h || {};
}

export function AppShell() {
  const booted = useSession((s) => s.booted);
  const acct = useSession((s) => s.account);
  const h = useHandle();
  const loc = useLocation();
  const admin = acct?.accountType === 'admin';

  useEffect(() => {
    document.body.classList.toggle('auth', !acct);
    document.body.classList.toggle('admin', !!admin);
  }, [acct, admin]);
  useEffect(() => {
    document.title = 'GrowPath · ' + (acct ? h.title || '' : '로그인');
  }, [acct, h.title]);
  /* 다시 로그인하면 마지막으로 보던 화면으로(직원별 브라우저 저장) */
  useEffect(() => {
    if (acct?.accountType === 'employee' && loc.pathname !== paths.login) updateWs((s) => void (s.lastRoute = loc.pathname));
  }, [acct, loc.pathname]);

  let body: ReactNode;
  let width = h.width || '';
  if (!booted) body = <Loading text="서버에서 불러오는 중…" style={{ margin: '60px auto' }} />;
  else if (!acct && h.role !== 'public') body = <Navigate to={paths.login} replace />;
  else if (acct && h.role === 'public') body = <Navigate to={admin ? paths.admin : paths.home} replace />;
  else if (admin && h.role !== 'admin') body = <Navigate to={paths.admin} replace />;
  else if (!admin && acct && h.role === 'admin') body = <Navigate to={paths.home} replace />;
  else if (h.role === 'mgr' && !isSup(meOf(acct))) body = <Navigate to={paths.home} replace />;
  else body = <Outlet />;
  if (!acct) width = 'login';

  return (
    <>
      <header className="ribbon">
        <ModeChip />
      </header>
      <div className="app">
        <aside className="side" id="side">
          {booted && acct ? admin ? <AdminSide /> : <Sidebar active={h.nav || ''} /> : null}
        </aside>
        <main className="main">
          <div id="view" className={`view ${width}`}>
            {body}
          </div>
        </main>
      </div>
      {booted && acct && !admin ? (
        <>
          <AssistantHost />
          <DraftNavGuard />
        </>
      ) : null}
      <SheetHost />
      <ToastHost />
    </>
  );
}

/* 앱 틀 (5차 gp-core.js boot·render) — 상단 띠 · 좌측 메뉴 · 본문. 화면마다 정한 메뉴 강조·제목·폭(handle)을 읽어 그린다 */
import { useEffect, type ReactNode } from 'react';
import { Navigate, Outlet, useLocation, useMatches } from 'react-router';
import { paths } from '@/app/paths';
import { AdminSide } from '@/features/admin/AdminSide';
import { AssistantHost } from '@/features/assistant/AssistantHost';
import { DraftNavGuard } from '@/features/draft/stale';
import { ai, PROV, useAiMode } from '@/shared/state/ai';
import { isSup, meOf, useSession } from '@/shared/state/session';
import { updateWs } from '@/shared/state/workspace';
import { SheetHost, ToastHost } from '@/shared/ui/SheetHost';
import { Loading } from '@/shared/ui/parts';
import { Sidebar } from './Sidebar';

export interface ScreenHandle {
  nav?: string;
  title?: string;
  width?: string;
  role?: 'employee' | 'mgr' | 'admin' | 'public';
}

function ModeChip() {
  const acct = useSession((s) => s.account);
  const { mode, choice } = useAiMode();
  if (!acct) return <span className="mode" />;
  if (acct.accountType === 'admin') return <span className="mode api">관리자 화면</span>;
  if (mode === 'off') return <span className="mode mock">{PROV[choice]} · 지금 쓸 수 없어요</span>;
  return <span className={`mode ${mode === 'mock' ? 'mock' : 'api'}`}>{mode === 'mock' ? '시연용 가데이터' : `${PROV[mode]} · ${ai.modelName('default')}`}</span>;
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
        <b>GrowPath 5차 목업 · Claude</b>
        <span className="vlabel">팀 DB(PostgreSQL) · FastAPI · RunPod-Ollama·OpenAI API 시연</span>
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

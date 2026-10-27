/* 계정 (서버 로그인 · 직원/관리자) — 5차 gp-core.js 의 GP.ACCOUNT·setAccount·boot·logout 을 옮김.
   계정은 로그아웃한 뒤 다시 로그인해야만 바뀐다. 부서장 권한·소속 직원은 서버가 부서 계층으로 정한다.
   부서장의 소속 직원 목록은 부서장 화면에 들어갈 때 받는다(features/team/teamData.ts · 5차의 로그인 때 미리 받기는 쓰는 곳이 없어 뺌) */
import { create } from 'zustand';
import { accountApi } from '@/api/endpoints/account';
import type { Account, DemoAccounts, User } from '@/api/types/account';
import { ai, applySettings, checkStatus, ping } from './ai';
import { loadCerts, loadRegSets } from './catalog';
import { freshWs, useWs } from './workspace';

interface SessionState {
  booted: boolean;
  account: Account | null;
  demo: DemoAccounts | null;
}

export const useSession = create<SessionState>(() => ({ booted: false, account: null, demo: null }));

export const meOf = (a: Account | null): User | null => (a && a.accountType === 'employee' ? a.user : null);
export const me = (): User | null => meOf(useSession.getState().account);
export const useMe = (): User | null => useSession((s) => meOf(s.account));
export const isAdmin = (): boolean => useSession.getState().account?.accountType === 'admin';
export const isSup = (e: User | null | undefined): boolean => !!(e && e.supervisor && (e.members || []).length);
export const meLine = (e: Pick<User, 'dept' | 'grade' | 'position'>): string => [e.dept, e.grade, e.position].filter(Boolean).join(' · ');

/** 로그인한 직원의 작업 공간을 서버에서 읽는다(features/draft 가 작성 문서 받는 법을 넣어 준다) */
let loadWorkspace: () => Promise<void> = async () => {};
export const setWorkspaceLoader = (fn: () => Promise<void>): void => {
  loadWorkspace = fn;
};

/** 로그인한 뒤에만 읽을 수 있는 값(모델 설정·자격증 목록·규정 묶음)은 계정이 정해질 때 읽는다 */
export async function setAccount(acct: Account | null): Promise<void> {
  useSession.setState({ account: acct });
  if (acct) await Promise.all([checkStatus(), loadCerts(), loadRegSets()]);
  if (acct && acct.accountType === 'employee') {
    applySettings(acct);
    await loadWorkspace();
  } else {
    useWs.setState(freshWs(acct && acct.accountType === 'admin' ? 'admin-' + acct.admin.id : null), true);
  }
}

async function loadDemoAccounts(): Promise<void> {
  if (useSession.getState().demo) return;
  try {
    useSession.setState({ demo: await accountApi.demoAccounts() });
  } catch {
    useSession.setState({ demo: { accounts: [] } });
  }
}

export async function boot(): Promise<void> {
  const acct: Account | null = await accountApi.me().catch(() => null);
  try {
    await setAccount(acct);
  } catch {
    await setAccount(null);
  }
  if (!acct) await loadDemoAccounts();
  useSession.setState({ booted: true });
  // 로그인한 채 새로 고치면 로그인 화면을 거치지 않으므로 여기서 한 번 연결을 확인한다(5차 GP.boot 와 같음)
  if (me() && ai.live()) void ping();
}

export async function login(employeeNo: string, password: string, keep: boolean): Promise<void> {
  const acct = await accountApi.login(employeeNo, password, keep);
  await setAccount(acct);
}

/** 로그아웃: 쓰던 입력은 먼저 서버에 저장한다(flush 는 작성 흐름이 넣어 준다) */
export async function logout(flush: () => Promise<void>): Promise<void> {
  try {
    await flush();
    await accountApi.logout();
  } catch {
    /* 이미 끊긴 세션이어도 화면은 로그아웃 */
  }
  useSession.setState({ account: null });
  useWs.setState(freshWs(null), true);
  await loadDemoAccounts();
}

/** 내 정보 저장 응답(서버가 다시 만든 직원 보기)으로 계정 정보를 바꾼다 */
export function setMeView(view: User): void {
  const a = useSession.getState().account;
  if (a && a.accountType === 'employee') useSession.setState({ account: { ...a, user: view } });
}

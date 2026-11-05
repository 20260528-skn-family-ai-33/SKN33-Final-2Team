import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { LoginPage } from './LoginPage';

const state = vi.hoisted(() => ({ demo: { accounts: [] as Array<{ code: string; name: string; dept: string }> } }));
vi.mock('@/shared/state/session', () => ({
  useSession: (selector: (s: typeof state) => unknown) => selector(state),
  isSup: vi.fn(), me: vi.fn(), setAccount: vi.fn(),
}));
vi.mock('@/shared/hooks/useGo', () => ({ useGo: () => vi.fn() }));
vi.mock('@/shared/state/ai', () => ({ ai: {}, cause: vi.fn(), ping: vi.fn() }));
vi.mock('@/shared/state/ui', () => ({ toast: vi.fn() }));
vi.mock('@/shared/state/workspace', () => ({ ws: vi.fn() }));

describe('로그인 시연 목록', () => {
  it('시연 API가 꺼져도 사번 직접 입력과 비밀번호 안내를 제공한다', () => {
    state.demo = { accounts: [] };
    const html = renderToStaticMarkup(<LoginPage />);
    expect(html).not.toContain('직원 고르기');
    expect(html).not.toContain('직원 목록을 불러오지 못했어요');
    expect(html).toContain('사번 또는 관리자 아이디');
    expect(html).toContain('관리자에게 받은 초기 비밀번호');
  });
  it('시연 목록을 받으면 직원 선택을 제공한다', () => {
    state.demo = { accounts: [{ code: 'TEST001', name: '테스트 직원', dept: '테스트 부서' }] };
    const html = renderToStaticMarkup(<LoginPage />);
    expect(html).toContain('직원 고르기');
    expect(html).toContain('TEST001');
  });
});

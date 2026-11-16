import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { LoginPage } from './LoginPage';

const state = vi.hoisted(() => ({ demo: { accounts: [] as Array<{ code: string; name: string; dept: string }> } }));
vi.mock('@/shared/state/session', () => ({
  useSession: (selector: (s: typeof state) => unknown) => selector(state),
  me: vi.fn(), setAccount: vi.fn(),
}));
vi.mock('@/shared/hooks/useGo', () => ({ useGo: () => vi.fn() }));
vi.mock('@/shared/state/ai', () => ({ ai: {}, cause: vi.fn(), ping: vi.fn() }));
vi.mock('@/shared/state/ui', () => ({ toast: vi.fn() }));
// 화면 모드 버튼은 불러오기만 해도 <html> 에 테마를 붙여(skins/index.ts) 브라우저가 없는 검사에서는 빈 버튼으로 바꾼다
vi.mock('@/skins/ThemeControls', () => ({ ThemeToggle: () => null }));

describe('로그인 베타 직원 목록', () => {
  it('베타 직원 선택이 꺼져도 사번 직접 입력과 비밀번호 찾기를 제공한다', () => {
    state.demo = { accounts: [] };
    const html = renderToStaticMarkup(<LoginPage />);
    expect(html).not.toContain('직원 고르기');
    expect(html).not.toContain('직원 목록을 불러오지 못했어요');
    expect(html).toContain('사번 또는 관리자 아이디');
    // 로그인 버튼 아래 안내 문단은 뺐다(2026-11-17). 비밀번호 안내는 '비밀번호 찾기' 버튼이 알림으로 보여 준다
    expect(html).not.toContain('관리자 화면은 관리자 전용 계정으로 들어가요');
    expect(html).toContain('비밀번호 찾기');
    // 서비스 라벨은 로그인 상자로 옮기고, 예전 꼬리표와 제목 아래 안내 문구는 뺐다
    expect(html).toContain('개발·운영 직원 AI 역량 성장지원');
    expect(html).not.toContain('한국수자원공사 임직원 로그인');
    expect(html).not.toContain('이어서 만들어 보세요');
  });
  it('베타 목록을 받으면 직원 선택을 제공하고 비밀번호는 비워 둔다', () => {
    state.demo = { accounts: [{ code: 'TEST001', name: '테스트 직원', dept: '테스트 부서' }] };
    const html = renderToStaticMarkup(<LoginPage />);
    expect(html).toContain('직원 고르기');
    expect(html).toContain('베타용 · 고르면 사번을 채워요');
    expect(html).toContain('TEST001');
    expect(html).toMatch(/<input[^>]*id="lgPw"[^>]*value=""/);
  });
});

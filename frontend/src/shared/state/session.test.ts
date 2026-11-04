/* 로그인 회차(signInSeq): 같은 직원이 로그아웃 뒤 다시 로그인해도 값이 달라야 이전 로그인의 늦은 응답을 가릴 수 있다(#82 PR #84 리뷰 P3) */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Account, User } from '@/api/types/account';

vi.mock('@/api/endpoints/account', () => ({ accountApi: { logout: vi.fn(async () => null), demoAccounts: vi.fn(async () => ({ accounts: [] })) } }));
vi.mock('@/shared/state/ai', () => ({ ai: { live: () => false }, applySettings: vi.fn(), checkStatus: vi.fn(async () => {}), ping: vi.fn() }));
vi.mock('@/shared/state/catalog', () => ({ loadCerts: vi.fn(async () => {}), loadRegSets: vi.fn(async () => {}) }));

type Session = typeof import('./session');
let s: Session;
const employee = (id: string): Account => ({ accountType: 'employee', user: { id, name: '직원' } as User }) as Account;

beforeEach(async () => {
  vi.resetModules();
  s = await import('./session');
});

describe('signInSeq', () => {
  it('같은 직원이 로그아웃 뒤 다시 로그인하면 회차가 달라진다', async () => {
    await s.setAccount(employee('A'));
    const first = s.signInSeq();
    await s.logout(async () => {});
    expect(s.signInSeq()).toBeGreaterThan(first);
    await s.setAccount(employee('A'));
    expect(s.me()?.id).toBe('A');
    expect(s.signInSeq()).toBeGreaterThan(first + 1);
  });

  it('내 정보 저장(setMeView)은 같은 로그인이라 회차를 바꾸지 않는다', async () => {
    await s.setAccount(employee('A'));
    const seq = s.signInSeq();
    s.setMeView({ id: 'A', name: '이름 바꿈' } as User);
    expect(s.signInSeq()).toBe(seq);
    expect(s.me()?.name).toBe('이름 바꿈');
  });
});

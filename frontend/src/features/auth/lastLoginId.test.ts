import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadLastLoginId, saveLastLoginId } from './lastLoginId';

function memoryStorage(): Storage {
  const m = new Map<string, string>();
  return {
    get length() { return m.size; },
    clear: () => m.clear(),
    getItem: (k) => m.get(k) ?? null,
    key: (i) => [...m.keys()][i] ?? null,
    removeItem: (k) => void m.delete(k),
    setItem: (k, v) => void m.set(k, String(v)),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('마지막 로그인 아이디', () => {
  it('저장한 사번을 다음에 그대로 돌려준다', () => {
    vi.stubGlobal('localStorage', memoryStorage());
    expect(loadLastLoginId()).toBe('');
    saveLastLoginId('20200001');
    expect(loadLastLoginId()).toBe('20200001');
    saveLastLoginId('admin');
    expect(loadLastLoginId()).toBe('admin');
  });
  it('아이디 칸 길이(40자)를 넘는 값은 채우지 않는다', () => {
    const s = memoryStorage();
    vi.stubGlobal('localStorage', s);
    s.setItem('growpath.login.last-id', 'x'.repeat(41));
    expect(loadLastLoginId()).toBe('');
    s.setItem('growpath.login.last-id', 'x'.repeat(40));
    expect(loadLastLoginId()).toBe('x'.repeat(40));
  });
  it('저장소를 못 쓰는 브라우저에서는 빈 값으로 두고 오류를 내지 않는다', () => {
    const fail = () => {
      throw new Error('SecurityError');
    };
    vi.stubGlobal('localStorage', { getItem: fail, setItem: fail });
    expect(() => saveLastLoginId('20200001')).not.toThrow();
    expect(loadLastLoginId()).toBe('');
  });
});

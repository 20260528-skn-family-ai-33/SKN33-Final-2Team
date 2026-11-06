import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ status: { checked: true, server: true, demoMode: undefined as boolean | undefined }, settings: { failSim: {} } }));
vi.mock('@/shared/state/ai', () => ({
  useAi: (selector: (s: typeof state) => unknown) => selector(state),
  useAiMode: () => ({ demo: false }),
  ai: { available: () => false, failSim: () => ({}) },
}));
vi.mock('@/shared/state/session', () => ({ useMe: () => ({ name: '검증직원', mySupervisor: null }), isSup: () => false }));
vi.mock('@/shared/hooks/useGo', () => ({ useGo: () => vi.fn() }));
vi.mock('@/features/draft/draftSync', () => ({ reloadWorkspace: vi.fn() }));
vi.mock('@/shared/state/workspace', () => ({ useWs: (selector: (s: { demoOpen: boolean }) => unknown) => selector({ demoOpen: false }), updateWs: vi.fn() }));

afterEach(() => vi.unstubAllEnvs());

describe('직원·관리자 시연 도구 공개 범위', () => {
  it.each([
    ['on', true, true],
    ['ON', true, true],
    [' on ', true, true],
    ['on', false, false],
    ['on', undefined, false],
    ['off', true, false],
    ['OFF', true, false],
    [' off ', true, false],
    ['', true, false],
    ['   ', true, false],
    ['unknown', true, false],
    [undefined, true, false],
    [undefined, false, false],
    [undefined, undefined, false],
  ] as const)('빌드=%s 서버=%s이면 시연 도구 표시=%s', async (build, server, visible) => {
    vi.stubEnv('VITE_DEMO_TOOLS', build);
    vi.resetModules();
    state.status.demoMode = server;
    const { DemoTools, AdminDemoTools } = await import('./DemoTools');
    expect(renderToStaticMarkup(<DemoTools />).includes('시연 도구')).toBe(visible);
    expect(renderToStaticMarkup(<AdminDemoTools />).includes('시연 도구')).toBe(visible);
  });
});

import { afterEach, expect, it, vi } from 'vitest';
import { applyConsoleDefaults, browserHeaders, consoleEnabled, useBrowserOptions } from './browserOptions';

afterEach(() => {
  applyConsoleDefaults();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it('두 기본값이 off여도 콘솔에서 켠 항목만 해당 요청에 반영한다', () => {
  vi.stubEnv('VITE_DEMO_TOOLS', 'off');
  const defaults = { picker: false, demo: false, browserOverrides: true };
  for (const picker of [false, true]) {
    for (const demo of [false, true]) {
      const options = { picker, demo, timeout: 180 };
      useBrowserOptions.setState({ options });
      expect(consoleEnabled('picker', options, defaults)).toBe(picker);
      expect(consoleEnabled('demo', options, defaults)).toBe(demo);
      expect(browserHeaders()).toEqual({
        'X-GrowPath-picker': picker ? 'on' : 'off',
        'X-GrowPath-demo': demo ? 'on' : 'off',
        ...(demo ? { 'X-GrowPath-timeout': '180' } : {}),
      });
    }
  }
});

it('콘솔을 명시적으로 허용한 환경에서만 이전 브라우저 설정을 읽는다', () => {
  const getItem = vi.fn(() => JSON.stringify({ demo: true, picker: true, timeout: 180, ollamaKey: 'test-key' }));
  vi.stubGlobal('localStorage', { getItem });
  vi.stubEnv('VITE_DEMO_TOOLS', 'off');
  const defaults = { demo: false, picker: false, browserOverrides: false };
  applyConsoleDefaults(defaults);
  expect(getItem).not.toHaveBeenCalled();
  expect(browserHeaders()).toEqual({ 'X-GrowPath-demo': 'off' });
  applyConsoleDefaults({ ...defaults, browserOverrides: true });
  expect(browserHeaders()['X-GrowPath-Ollama-Key']).toBe('test-key');
  applyConsoleDefaults();
  expect(browserHeaders()).toEqual({ 'X-GrowPath-demo': 'off' });
});

it('콘솔 설정을 지우면 빌드 및 서버 기본값을 다시 사용한다', () => {
  vi.stubEnv('VITE_DEMO_TOOLS', 'on');
  const defaults = { picker: true, demo: false, browserOverrides: true };
  expect(browserHeaders()).toEqual({});
  expect(consoleEnabled('demo', {}, defaults)).toBe(false);
  expect(consoleEnabled('picker', {}, defaults)).toBe(true);
  expect(consoleEnabled('demo', { demo: true }, { ...defaults, browserOverrides: false })).toBe(false);
});

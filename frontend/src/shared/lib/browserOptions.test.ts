import { afterEach, expect, it, vi } from 'vitest';
import { browserHeaders, consoleEnabled, useBrowserOptions } from './browserOptions';

afterEach(() => {
  useBrowserOptions.setState({ options: {} });
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

it('콘솔 설정을 지우면 빌드 및 서버 기본값을 다시 사용한다', () => {
  vi.stubEnv('VITE_DEMO_TOOLS', 'on');
  const defaults = { picker: true, demo: false, browserOverrides: true };
  expect(browserHeaders()).toEqual({});
  expect(consoleEnabled('demo', {}, defaults)).toBe(false);
  expect(consoleEnabled('picker', {}, defaults)).toBe(true);
  expect(consoleEnabled('demo', { demo: true }, { ...defaults, browserOverrides: false })).toBe(false);
});

import { browserDemoEnabled, useBrowserOptions } from './browserOptions';

/** 브라우저별 표시 설정이 없으면 기존 빌드 기본값을 따른다. */
export const canUseDemo = (serverDemoMode: boolean | undefined): boolean =>
  serverDemoMode === true && browserDemoEnabled(useBrowserOptions.getState().options);

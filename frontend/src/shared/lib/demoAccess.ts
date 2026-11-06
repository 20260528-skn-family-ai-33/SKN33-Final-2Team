/** 화면 빌드는 기존 기본값을 유지하되, 서버가 시연을 허용할 때만 노출한다. 명시적 off는 숨긴다. */
export const canUseDemo = (serverDemoMode: boolean | undefined): boolean =>
  import.meta.env.VITE_DEMO_TOOLS !== 'off' && serverDemoMode === true;

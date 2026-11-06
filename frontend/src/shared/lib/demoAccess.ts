/** 시연 기능은 화면 빌드와 서버가 모두 명시적으로 허용할 때만 노출한다. */
export const canUseDemo = (serverDemoMode: boolean | undefined): boolean =>
  import.meta.env.VITE_DEMO_TOOLS === 'on' && serverDemoMode === true;

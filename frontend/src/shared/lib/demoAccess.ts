/** 화면 빌드는 명시적 on만 허용하며, 서버도 시연을 허용할 때 노출한다. 대소문자와 앞뒤 공백은 무시한다. */
export const canUseDemo = (serverDemoMode: boolean | undefined): boolean =>
  (import.meta.env.VITE_DEMO_TOOLS ?? '').trim().toLowerCase() === 'on' && serverDemoMode === true;

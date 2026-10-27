/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// 개발 서버: 화면은 Vite 가 내고, /api 요청은 백엔드로 넘긴다(같은 주소라 로그인 쿠키가 그대로 동작).
// 백엔드 주소는 frontend/.env.local 의 API_PROXY_TARGET 한 줄로 바꾼다 → 팀원 백엔드로 갈아 끼울 때 화면 코드는 그대로.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.API_PROXY_TARGET || 'http://localhost:8815';
  const port = Number(env.DEV_PORT || 5185);
  return {
    plugins: [react()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: {
      port,
      strictPort: true,
      proxy: { '/api': { target, changeOrigin: false } },
    },
    preview: { port: port + 1, strictPort: true, proxy: { '/api': { target, changeOrigin: false } } },
    build: {
      outDir: 'dist',
      sourcemap: true,
      // 라이브러리(React 등)는 따로 묶는다: 화면 코드만 바뀐 배포에서는 브라우저가 라이브러리 파일을 캐시에서 그대로 쓴다
      rolldownOptions: { output: { codeSplitting: { groups: [{ name: 'vendor', test: /node_modules/ }] } } },
    },
    test: { environment: 'node', include: ['src/**/*.test.ts'] },
  };
});

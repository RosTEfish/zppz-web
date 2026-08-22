import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig(() => ({
    base: '/',
    cacheDir: '.vite-cache',
    plugins: [react()],
    server: {
      hmr: process.env.DISABLE_HMR !== 'true',
      proxy: {
        '/api': 'http://127.0.0.1:8000',
      },
    },
    build: {
      manifest: true,
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        output: {
          // 稳定 vendor 分组：业务代码迭代时框架缓存继续命中。
          // 注意：@mui/x-* 必须保持独立懒加载，不得并入 vendor-mui。
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined;
            if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'vendor-react';
            if (/node_modules\/(@mui\/material|@mui\/system|@mui\/private-theming|@mui\/styled-engine|@mui\/utils|@emotion)\//.test(id)) return 'vendor-mui';
            if (/node_modules\/(react-router|swr|openapi-fetch)\//.test(id)) return 'vendor-app';
            return undefined;
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/vitest.setup.ts',
    },
}));

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
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/vitest.setup.ts',
    },
}));

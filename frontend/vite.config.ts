import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    css: true,
    // Explicit imports (import { describe, it, expect } from 'vitest') are
    // used throughout the test files rather than relying on globals=true --
    // avoids needing to touch tsconfig.json's `types` array at all, which
    // keeps this change fully additive and lower-risk.
    globals: false,
  },
});
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  base: '/static/showcase/',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../web/showcase', emptyOutDir: true, sourcemap: false,
    rollupOptions: { output: { manualChunks(id: string) {
      if (id.includes('/node_modules/three/')) return 'three-engine';
      if (/\/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react-runtime';
      if (/\/node_modules\/(gsap|motion|framer-motion|motion-dom|motion-utils)\//.test(id)) return 'motion-engine';
    } } },
  },
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/workspace': 'http://127.0.0.1:8000', '/docs': 'http://127.0.0.1:8000', '^/static/(?!showcase/)': 'http://127.0.0.1:8000' } },
});

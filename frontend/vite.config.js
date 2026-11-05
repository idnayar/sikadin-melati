import { defineConfig } from 'vite';

// Pengembangan: UI di :5173, API Python (FastAPI) di :8000 lewat proxy /api.
// Produksi: `npm run build` → dist/ disajikan oleh FastAPI (satu alamat, tanpa CORS).
export default defineConfig({
  server: { port: 5173, proxy: { '/api': { target: process.env.SIKADIN_API || 'http://127.0.0.1:8000', changeOrigin: false } } },
  build: { outDir: 'dist', sourcemap: false },
});

import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  build: { outDir: 'dist', emptyOutDir: true },
  // En `npm run dev`, les appels /api partent vers l'API lancee par Compose.
  server: { proxy: { '/api': 'http://localhost:8000' } },
});

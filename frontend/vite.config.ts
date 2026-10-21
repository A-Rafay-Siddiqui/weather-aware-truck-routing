import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // Mapbox GL (what Spotter's TMS uses) when a token is configured; MapLibre (the open-source
  // fork with the same API) otherwise, so the app still runs with no map account at all.
  // react-map-gl exposes both through identical components, so only these two aliases change.
  const engine = env.VITE_MAPBOX_TOKEN ? 'mapbox' : 'maplibre';

  return {
    plugins: [react()],
    define: { __MAP_ENGINE__: JSON.stringify(engine) },
    resolve: {
      alias: {
        'map-engine.css': engine === 'mapbox' ? 'mapbox-gl/dist/mapbox-gl.css' : 'maplibre-gl/dist/maplibre-gl.css',
        'map-engine': `react-map-gl/${engine}`,
      },
    },
    server: {
      // In dev the API runs on :8000. Proxying avoids CORS and keeps VITE_API_BASE_URL empty.
      proxy: { '/api': process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000' },
    },
    build: {
      chunkSizeWarningLimit: 2000,
      rollupOptions: {
        output: {
          // The GL library is large; a separate chunk caches independently of app code.
          manualChunks: { 'map-gl': [engine === 'mapbox' ? 'mapbox-gl' : 'maplibre-gl'] },
        },
      },
    },
    test: { environment: 'node' },
  };
});

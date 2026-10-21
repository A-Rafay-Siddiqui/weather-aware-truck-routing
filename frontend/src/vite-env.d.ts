/// <reference types="vite/client" />

/** Which GL engine the build aliased `map-engine` to (see vite.config.ts). */
declare const __MAP_ENGINE__: 'mapbox' | 'maplibre';

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_MAPBOX_TOKEN?: string;
}

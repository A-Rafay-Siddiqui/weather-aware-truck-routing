import type { Heatmap } from '../api/types';
import { RISK_COLOR, RISK_ORDER, hexToRgb } from './risk';

export type HeatmapLayer = 'risk' | 'wind' | 'rain' | 'snow';

type Rgba = [number, number, number, number];
type Stop = [value: number, color: Rgba];

const rgba = (hex: string, a: number): Rgba => [...hexToRgb(hex), a] as Rgba;

// Color stops sit on the risk thresholds, so a cell's color tells you its risk level
// whichever variable is showing.
const SCALES: Record<Exclude<HeatmapLayer, 'risk'>, Stop[]> = {
  wind: [
    [0, rgba('#8ecae6', 0)],
    [15, rgba('#8ecae6', 0.18)],
    [25, rgba(RISK_COLOR.moderate, 0.42)],
    [35, rgba(RISK_COLOR.high, 0.52)],
    [45, rgba(RISK_COLOR.severe, 0.6)],
    [55, rgba(RISK_COLOR.no_travel, 0.7)],
  ],
  rain: [
    [0, rgba('#4ea8de', 0)],
    [0.02, rgba('#4ea8de', 0.2)],
    [0.1, rgba('#3a86ff', 0.42)],
    [0.25, rgba('#1d4ed8', 0.55)],
    [0.5, rgba('#d93a3a', 0.6)],
    [1.0, rgba(RISK_COLOR.no_travel, 0.72)],
  ],
  snow: [
    [0, rgba('#bde0fe', 0)],
    [0.1, rgba('#bde0fe', 0.3)],
    [0.5, rgba('#7fb8f0', 0.48)],
    [1.0, rgba('#4361ee', 0.58)],
    [2.0, rgba('#d93a3a', 0.62)],
    [3.0, rgba(RISK_COLOR.no_travel, 0.75)],
  ],
};

const RISK_ALPHA = [0.1, 0.42, 0.52, 0.6, 0.7];
const RISK_RGBA: Rgba[] = RISK_ORDER.map((k, i) => rgba(RISK_COLOR[k], RISK_ALPHA[i]));

export function colorFor(layer: HeatmapLayer, value: number): Rgba {
  if (layer === 'risk') return RISK_RGBA[Math.max(0, Math.min(4, value))];
  const stops = SCALES[layer];
  if (value <= stops[0][0]) return stops[0][1];
  for (let i = 1; i < stops.length; i++) {
    const [v1, c1] = stops[i];
    if (value <= v1) {
      const [v0, c0] = stops[i - 1];
      const t = (value - v0) / (v1 - v0);
      return c0.map((c, j) => c + (c1[j] - c) * t) as Rgba;
    }
  }
  return stops[stops.length - 1][1];
}

export function legendStops(layer: HeatmapLayer): { value: number; color: string }[] {
  if (layer === 'risk') return RISK_ORDER.map((k, i) => ({ value: i, color: RISK_COLOR[k] }));
  return SCALES[layer].slice(1).map(([value, [r, g, b]]) => ({ value, color: `rgb(${r},${g},${b})` }));
}

export function valuesFor(heatmap: Heatmap, layer: HeatmapLayer): number[][] {
  switch (layer) {
    case 'risk':
      return heatmap.risk;
    case 'wind':
      return heatmap.wind_mph;
    case 'rain':
      return heatmap.rain_in_hr;
    case 'snow':
      return heatmap.snow_in_hr;
  }
}

const UPSCALE = 8;

/**
 * One bitmap per forecast hour, encoded as a data URL.
 *
 * Each grid cell is painted as one pixel, then the bitmap is upscaled 8× through a blur, so
 * cell edges and the corridor boundary come out as a smooth field rather than blocks. The
 * map stretches the result over the grid's Mercator bounds. Rendering all 49 frames up front
 * takes a few tens of milliseconds. After that, scrubbing only swaps which image is visible.
 */
export function renderFrames(heatmap: Heatmap, layer: HeatmapLayer): string[] {
  const { cols, rows } = heatmap;
  const small = document.createElement('canvas');
  small.width = cols;
  small.height = rows;
  const big = document.createElement('canvas');
  big.width = cols * UPSCALE;
  big.height = rows * UPSCALE;
  const sctx = small.getContext('2d');
  const bctx = big.getContext('2d');
  if (!sctx || !bctx) return [];
  bctx.imageSmoothingEnabled = true;
  bctx.imageSmoothingQuality = 'high';
  bctx.filter = `blur(${UPSCALE * 0.6}px)`;

  const values = valuesFor(heatmap, layer);
  const frames: string[] = [];
  for (let h = 0; h < heatmap.hours; h++) {
    const image = sctx.createImageData(cols, rows);
    heatmap.cells.forEach(([x, y], i) => {
      const [r, g, b, a] = colorFor(layer, values[i][h]);
      const o = (y * cols + x) * 4;
      image.data[o] = r;
      image.data[o + 1] = g;
      image.data[o + 2] = b;
      image.data[o + 3] = Math.round(a * 255);
    });
    sctx.putImageData(image, 0, 0);
    bctx.clearRect(0, 0, big.width, big.height);
    bctx.drawImage(small, 0, 0, big.width, big.height);
    frames.push(big.toDataURL('image/png'));
  }
  return frames;
}

const mercY = (lat: number) => (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));

/** Index into the heatmap's cell arrays for a map position, or -1 outside the corridor. */
export function cellIndexAt(heatmap: Heatmap, lon: number, lat: number, lookup: Map<number, number>): number {
  const x = Math.floor((lon - heatmap.west) / heatmap.cell_deg);
  const y = Math.floor((mercY(heatmap.north) - mercY(lat)) / heatmap.cell_deg);
  if (x < 0 || y < 0 || x >= heatmap.cols || y >= heatmap.rows) return -1;
  return lookup.get(y * heatmap.cols + x) ?? -1;
}

export const cellLookup = (heatmap: Heatmap) =>
  new Map(heatmap.cells.map(([x, y], i) => [y * heatmap.cols + x, i] as const));

import { describe, expect, it } from 'vitest';
import type { PathPoint } from '../api/types';
import { formatDuration } from './format';
import { colorFor } from './heatmapFrames';
import { positionAtMile, positionAtTime, sliceByMiles } from './path';

// 0 → 10 mi in 600 s, parked 10h (HOS rest), then 10 → 20 mi.
const path: PathPoint[] = [
  [0, 0, 0, 0],
  [1, 0, 600, 10],
  [1, 0, 36_600, 10],
  [2, 0, 37_200, 20],
];

describe('path interpolation', () => {
  it('moves linearly in time and stays parked during stops', () => {
    expect(positionAtTime(path, 300)).toEqual([0.5, 0]);
    expect(positionAtTime(path, 20_000)).toEqual([1, 0]);
    expect(positionAtTime(path, 36_900)).toEqual([1.5, 0]);
  });
  it('clamps before departure and after arrival', () => {
    expect(positionAtTime(path, -50)).toEqual([0, 0]);
    expect(positionAtTime(path, 1e9)).toEqual([2, 0]);
  });
  it('slices by mile with interpolated ends', () => {
    expect(positionAtMile(path, 15)).toEqual([1.5, 0]);
    expect(sliceByMiles(path, 5, 15)).toEqual([[0.5, 0], [1, 0], [1, 0], [1.5, 0]]);
  });
});

describe('formatting and color scales', () => {
  it('formats durations', () => {
    expect(formatDuration(45 * 60)).toBe('45m');
    expect(formatDuration(11 * 3600 + 5 * 60)).toBe('11h 05m');
  });
  it('interpolates continuous scales and clamps', () => {
    expect(colorFor('wind', 0)[3]).toBe(0);
    expect(colorFor('wind', 100)).toEqual(colorFor('wind', 55));
    const mid = colorFor('wind', 20);
    expect(mid[3]).toBeGreaterThan(0.18);
    expect(mid[3]).toBeLessThan(0.42);
  });
});

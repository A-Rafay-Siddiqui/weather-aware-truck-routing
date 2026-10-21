import type { PathPoint } from '../api/types';

/** Binary search: index of the last element with key(el) <= x. */
function lastAtOrBelow(path: PathPoint[], x: number, key: 2 | 3): number {
  let lo = 0;
  let hi = path.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (path[mid][key] <= x) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

function lerpAlong(path: PathPoint[], x: number, key: 2 | 3): [number, number] {
  if (x <= path[0][key]) return [path[0][0], path[0][1]];
  const last = path[path.length - 1];
  if (x >= last[key]) return [last[0], last[1]];
  const i = lastAtOrBelow(path, x, key);
  const a = path[i];
  const b = path[i + 1];
  const span = b[key] - a[key];
  const t = span > 0 ? (x - a[key]) / span : 0;
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** Miles driven `seconds` after departure. */
export function mileAtTime(path: PathPoint[], seconds: number): number {
  if (seconds <= path[0][2]) return 0;
  const last = path[path.length - 1];
  if (seconds >= last[2]) return last[3];
  const i = lastAtOrBelow(path, seconds, 2);
  const a = path[i];
  const b = path[i + 1];
  const span = b[2] - a[2];
  return span > 0 ? a[3] + ((seconds - a[2]) / span) * (b[3] - a[3]) : a[3];
}

/** Truck position [lon, lat] `seconds` after departure (parked during HOS stops). */
export const positionAtTime = (path: PathPoint[], seconds: number) => lerpAlong(path, seconds, 2);

export const positionAtMile = (path: PathPoint[], mile: number) => lerpAlong(path, mile, 3);

/** Coordinates of the path between two miles, with interpolated end points. */
export function sliceByMiles(path: PathPoint[], from: number, to: number): [number, number][] {
  const coords: [number, number][] = [positionAtMile(path, from)];
  for (const p of path) {
    if (p[3] > from && p[3] < to) coords.push([p[0], p[1]]);
  }
  coords.push(positionAtMile(path, to));
  return coords;
}

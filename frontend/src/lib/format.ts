import dayjs from 'dayjs';

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  return `${h}h ${String(m).padStart(2, '0')}m`;
}

export const formatMiles = (miles: number, digits = 0) =>
  `${miles.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })} mi`;

export const formatLbs = (lbs: number) => `${lbs.toLocaleString()} lb`;

/** Short local time, adding the date only when it differs from `reference`. */
export function formatEta(iso: string | number, reference?: string | number): string {
  const t = dayjs(iso);
  const sameDay = reference !== undefined && t.isSame(dayjs(reference), 'day');
  return sameDay ? t.format('h:mm A') : t.format('ddd h:mm A');
}

export const formatDateTime = (iso: string | number) => dayjs(iso).format('ddd MMM D, h:mm A');

/** e.g. "CDT". The user sees every time in their own browser time zone. */
export const localTzName = () =>
  new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(new Date()).find((p) => p.type === 'timeZoneName')
    ?.value ?? '';

export const formatRate = (inPerHr: number) => (inPerHr < 0.005 ? '0' : inPerHr.toFixed(2));

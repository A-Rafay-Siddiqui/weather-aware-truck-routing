import type { RiskKey } from '../api/types';

export const RISK_ORDER: RiskKey[] = ['low', 'moderate', 'high', 'severe', 'no_travel'];

export const RISK_LABEL: Record<RiskKey, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
};

/** Ordered green → yellow → orange → red → violet so each step reads as "worse". */
export const RISK_COLOR: Record<RiskKey, string> = {
  low: '#2e9e5b',
  moderate: '#e8b007',
  high: '#f07c1b',
  severe: '#d93a3a',
  no_travel: '#7b2cbf',
};

/** Text color that stays readable on top of each risk color. */
export const RISK_CONTRAST: Record<RiskKey, string> = {
  low: '#fff',
  moderate: '#1f1a00',
  high: '#fff',
  severe: '#fff',
  no_travel: '#fff',
};

export const riskFromScore = (score: number): RiskKey => RISK_ORDER[Math.max(0, Math.min(4, Math.round(score)))];

export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

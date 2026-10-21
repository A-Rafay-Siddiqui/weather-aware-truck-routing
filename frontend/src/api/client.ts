import axios, { AxiosError } from 'axios';
import type { Heatmap, Place, Plan, PlanInput, PlanSummary, RiskRules } from './types';

export const http = axios.create({
  baseURL: `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1`,
  timeout: 90_000,
});

/** Flattens DRF errors ({detail} or {field: [msgs]}) into one readable message. */
export function errorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    if (error.code === 'ECONNABORTED') return 'The server took too long to respond. Please try again.';
    const data = error.response?.data as Record<string, unknown> | undefined;
    if (data && typeof data === 'object') {
      if (typeof data.detail === 'string') return data.detail;
      const parts = Object.entries(data).map(([field, value]) => {
        const text = Array.isArray(value) ? value.join(' ') : typeof value === 'object' ? JSON.stringify(value) : String(value);
        return field === 'non_field_errors' ? text : `${field.replace(/_/g, ' ')}: ${text}`;
      });
      if (parts.length) return parts.join(' ');
    }
    if (!error.response) return 'Could not reach the server. Check your connection.';
  }
  return error instanceof Error ? error.message : 'Something went wrong.';
}

export const api = {
  health: () => http.get<{ status: string; routing_configured: boolean }>('/health/').then((r) => r.data),
  riskRules: () => http.get<RiskRules>('/risk-rules/').then((r) => r.data),
  geocode: (q: string, signal?: AbortSignal) =>
    http.get<{ results: Place[] }>('/geocode/', { params: { q }, signal }).then((r) => r.data.results),
  createPlan: (input: PlanInput) => http.post<Plan>('/trip-plans/', input).then((r) => r.data),
  plan: (id: string) => http.get<Plan>(`/trip-plans/${id}/`).then((r) => r.data),
  recentPlans: () => http.get<PlanSummary[]>('/trip-plans/').then((r) => r.data),
  heatmap: (id: string) => http.get<Heatmap>(`/trip-plans/${id}/heatmap/`).then((r) => r.data),
};

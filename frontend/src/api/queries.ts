import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { PlanInput } from './types';

export const queryKeys = {
  health: ['health'] as const,
  riskRules: ['riskRules'] as const,
  geocode: (q: string) => ['geocode', q] as const,
  plan: (id: string) => ['tripPlan', id] as const,
  recentPlans: ['tripPlans'] as const,
  heatmap: (id: string) => ['tripPlan', id, 'heatmap'] as const,
};

export const useHealth = () =>
  useQuery({ queryKey: queryKeys.health, queryFn: api.health, staleTime: Infinity, retry: 3, retryDelay: 3000 });

export const useRiskRules = () => useQuery({ queryKey: queryKeys.riskRules, queryFn: api.riskRules, staleTime: Infinity });

export const usePlaceSearch = (q: string) =>
  useQuery({
    queryKey: queryKeys.geocode(q.trim().toLowerCase()),
    queryFn: ({ signal }) => api.geocode(q, signal),
    enabled: q.trim().length >= 2,
    staleTime: 60 * 60 * 1000,
    placeholderData: keepPreviousData,
  });

export const usePlan = (id: string | null) =>
  useQuery({ queryKey: queryKeys.plan(id ?? ''), queryFn: () => api.plan(id!), enabled: !!id, staleTime: Infinity });

export const useHeatmap = (id: string | null) =>
  useQuery({
    queryKey: queryKeys.heatmap(id ?? ''),
    queryFn: () => api.heatmap(id!),
    enabled: !!id,
    staleTime: Infinity, // a plan's heatmap never changes once computed
  });

export const useRecentPlans = () => useQuery({ queryKey: queryKeys.recentPlans, queryFn: api.recentPlans });

export function useCreatePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: PlanInput) => api.createPlan(input),
    onSuccess: (plan) => {
      // Seed the detail cache so navigating to the new plan doesn't refetch it.
      client.setQueryData(queryKeys.plan(plan.id), plan);
      client.invalidateQueries({ queryKey: queryKeys.recentPlans });
    },
  });
}

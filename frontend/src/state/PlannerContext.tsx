import { createContext, useContext, useMemo, useReducer, type Dispatch, type ReactNode } from 'react';
import type { HeatmapLayer } from '../lib/heatmapFrames';

/**
 * UI state for the planner screen (server data lives in React Query).
 *
 * The forecast time is kept in its own context. It changes up to 60×/s during playback, and
 * only the map overlays and the slider should re-render for that, not the side panel.
 */

export interface FocusTarget {
  lon: number;
  lat: number;
  zoom?: number;
  key: number; // changes on every request so repeated clicks re-fly
}

interface PlannerState {
  planId: string | null;
  selectedRouteId: string | null;
  showAllRoutes: boolean;
  heatmapLayer: HeatmapLayer;
  showHeatmap: boolean;
  selectedCheckpoint: number | null;
  focus: FocusTarget | null;
}

export type PlannerAction =
  | { type: 'SET_PLAN'; planId: string | null; recommendedRouteId?: string | null }
  | { type: 'SELECT_ROUTE'; routeId: string }
  | { type: 'TOGGLE_ALL_ROUTES' }
  | { type: 'SET_HEATMAP_LAYER'; layer: HeatmapLayer }
  | { type: 'TOGGLE_HEATMAP' }
  | { type: 'SELECT_CHECKPOINT'; index: number | null; lon?: number; lat?: number };

const initialState: PlannerState = {
  planId: new URLSearchParams(window.location.search).get('plan'),
  selectedRouteId: null,
  showAllRoutes: true,
  heatmapLayer: 'risk',
  showHeatmap: true,
  selectedCheckpoint: null,
  focus: null,
};

function reducer(state: PlannerState, action: PlannerAction): PlannerState {
  switch (action.type) {
    case 'SET_PLAN':
      return {
        ...state,
        planId: action.planId,
        selectedRouteId: action.recommendedRouteId ?? null,
        selectedCheckpoint: null,
        focus: null,
      };
    case 'SELECT_ROUTE':
      return { ...state, selectedRouteId: action.routeId, selectedCheckpoint: null };
    case 'TOGGLE_ALL_ROUTES':
      return { ...state, showAllRoutes: !state.showAllRoutes };
    case 'SET_HEATMAP_LAYER':
      return { ...state, heatmapLayer: action.layer, showHeatmap: true };
    case 'TOGGLE_HEATMAP':
      return { ...state, showHeatmap: !state.showHeatmap };
    case 'SELECT_CHECKPOINT':
      return {
        ...state,
        selectedCheckpoint: action.index,
        focus:
          action.lon !== undefined && action.lat !== undefined
            ? { lon: action.lon, lat: action.lat, zoom: 8, key: Date.now() }
            : state.focus,
      };
  }
}

const StateContext = createContext<PlannerState | null>(null);
const DispatchContext = createContext<Dispatch<PlannerAction> | null>(null);

export function PlannerProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <DispatchContext.Provider value={dispatch}>
      <StateContext.Provider value={state}>{children}</StateContext.Provider>
    </DispatchContext.Provider>
  );
}

export function usePlannerState() {
  const ctx = useContext(StateContext);
  if (!ctx) throw new Error('usePlannerState must be used inside PlannerProvider');
  return ctx;
}

export function usePlannerDispatch() {
  const ctx = useContext(DispatchContext);
  if (!ctx) throw new Error('usePlannerDispatch must be used inside PlannerProvider');
  return ctx;
}

// ---- Forecast time ----------------------------------------------------------------------------

interface ForecastTime {
  /** Hours after the forecast start (0–48), fractional during playback. */
  hour: number;
  playing: boolean;
  setHour: (hour: number) => void;
  setPlaying: (playing: boolean) => void;
}

const ForecastTimeContext = createContext<ForecastTime | null>(null);

type TimeAction = { type: 'hour'; hour: number } | { type: 'playing'; playing: boolean };

function timeReducer(state: { hour: number; playing: boolean }, action: TimeAction) {
  switch (action.type) {
    case 'hour':
      return { ...state, hour: Math.max(0, Math.min(48, action.hour)) };
    case 'playing':
      return { ...state, playing: action.playing };
  }
}

export function ForecastTimeProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(timeReducer, { hour: 0, playing: false });
  const value = useMemo<ForecastTime>(
    () => ({
      ...state,
      setHour: (hour) => dispatch({ type: 'hour', hour }),
      setPlaying: (playing) => dispatch({ type: 'playing', playing }),
    }),
    [state],
  );
  return <ForecastTimeContext.Provider value={value}>{children}</ForecastTimeContext.Provider>;
}

export function useForecastTime() {
  const ctx = useContext(ForecastTimeContext);
  if (!ctx) throw new Error('useForecastTime must be used inside ForecastTimeProvider');
  return ctx;
}

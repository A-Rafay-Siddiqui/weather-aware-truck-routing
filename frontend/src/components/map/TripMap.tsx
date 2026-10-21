import { Box, Paper, Stack, Typography } from '@mui/material';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { AttributionControl, Layer, NavigationControl, Popup, ScaleControl, Source, type MapMouseEvent, type MapRef } from 'map-engine';
import type { FeatureCollection } from 'geojson';
import type { Checkpoint, Heatmap, Plan } from '../../api/types';
import { formatEta, formatRate } from '../../lib/format';
import { secondsAfterDeparture } from '../../lib/forecast';
import { cellIndexAt, cellLookup } from '../../lib/heatmapFrames';
import { RISK_LABEL, riskFromScore } from '../../lib/risk';
import { useForecastTime, usePlannerDispatch, usePlannerState } from '../../state/PlannerContext';
import { useColorMode } from '../ColorModeProvider';
import { RiskChip } from '../RiskVisuals';
import { HeatmapLayers, ROUTES_ANCHOR_LAYER } from './HeatmapLayers';
import { StaticMarkers, TruckMarkers } from './MapMarkers';
import { INTERACTIVE_LAYERS, RouteLayers } from './RouteLayers';

const STYLES =
  __MAP_ENGINE__ === 'mapbox'
    ? { light: 'mapbox://styles/mapbox/navigation-day-v1', dark: 'mapbox://styles/mapbox/navigation-night-v1' }
    : { light: 'https://tiles.openfreemap.org/styles/positron', dark: 'https://tiles.openfreemap.org/styles/dark' };

const engineProps = __MAP_ENGINE__ === 'mapbox' ? { mapboxAccessToken: import.meta.env.VITE_MAPBOX_TOKEN } : {};

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
const CONTINENTAL_US = { longitude: -97.5, latitude: 39, zoom: 3.6 };

interface Props {
  plan?: Plan;
  heatmap?: Heatmap;
  /** Pixels covered by overlays, so fitBounds keeps routes visible. */
  padding: { top: number; bottom: number; left: number; right: number };
  /** Small screens: compact attribution, no scale bar. */
  compact?: boolean;
}

type Hover =
  | { kind: 'checkpoint'; routeId: string; checkpoint: Checkpoint }
  | { kind: 'cell'; x: number; y: number; index: number }
  | null;

export function TripMap({ plan, heatmap, padding, compact = false }: Props) {
  const mapRef = useRef<MapRef>(null);
  const { mode } = useColorMode();
  const { selectedRouteId, showAllRoutes, heatmapLayer, showHeatmap, selectedCheckpoint, focus } = usePlannerState();
  const dispatch = usePlannerDispatch();
  const { hour } = useForecastTime();
  const [hover, setHover] = useState<Hover>(null);
  const [cursor, setCursor] = useState('');
  const lookup = useMemo(() => (heatmap ? cellLookup(heatmap) : null), [heatmap]);

  // Fit the whole trip whenever a new plan loads.
  useEffect(() => {
    if (!plan) return;
    const [w, s, e, n] = plan.bbox;
    // The details panel opens in the same render, so wait a frame for layout, then sync the
    // canvas size before fitting (otherwise the fit uses the old, taller map).
    const id = requestAnimationFrame(() => {
      const map = mapRef.current;
      if (!map) return;
      if (import.meta.env.DEV) (window as unknown as { __map: unknown }).__map = map; // e2e checks
      map.resize();
      map.fitBounds(
        [
          [w, s],
          [e, n],
        ],
        { padding, duration: 900 },
      );
    });
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refit only for a new plan, not on padding changes
  }, [plan?.id]);

  useEffect(() => {
    if (focus) mapRef.current?.flyTo({ center: [focus.lon, focus.lat], zoom: focus.zoom ?? 8, duration: 800 });
  }, [focus]);

  const frame = Math.min(48, Math.max(0, Math.round(hour)));
  const seconds = plan ? secondsAfterDeparture(plan, hour, heatmap) : 0;

  const onMove = useCallback(
    (e: MapMouseEvent) => {
      const feature = e.features?.[0];
      if (feature?.layer?.id === 'checkpoints' && plan) {
        const { routeId, index } = feature.properties as { routeId: string; index: number };
        const checkpoint = plan.routes.find((r) => r.id === routeId)?.checkpoints[index];
        setCursor('pointer');
        setHover(checkpoint ? { kind: 'checkpoint', routeId, checkpoint } : null);
        return;
      }
      setCursor(feature ? 'pointer' : '');
      if (heatmap && lookup && showHeatmap) {
        const index = cellIndexAt(heatmap, e.lngLat.lng, e.lngLat.lat, lookup);
        setHover(index >= 0 ? { kind: 'cell', x: e.point.x, y: e.point.y, index } : null);
      } else {
        setHover(null);
      }
    },
    [plan, heatmap, lookup, showHeatmap],
  );

  const onClick = useCallback(
    (e: MapMouseEvent) => {
      const feature = e.features?.[0];
      if (!feature || !plan) return;
      if (feature.layer?.id === 'checkpoints') {
        const { routeId, index } = feature.properties as { routeId: string; index: number };
        dispatch({ type: 'SELECT_ROUTE', routeId });
        dispatch({ type: 'SELECT_CHECKPOINT', index });
      } else if (feature.layer?.id === 'route-hit') {
        dispatch({ type: 'SELECT_ROUTE', routeId: (feature.properties as { id: string }).id });
      }
    },
    [plan, dispatch],
  );

  const selectRoute = useCallback((routeId: string) => dispatch({ type: 'SELECT_ROUTE', routeId }), [dispatch]);

  return (
    <Box sx={{ position: 'absolute', inset: 0 }}>
      <Map
        ref={mapRef}
        {...engineProps}
        initialViewState={CONTINENTAL_US}
        mapStyle={mode === 'dark' ? STYLES.dark : STYLES.light}
        interactiveLayerIds={plan ? INTERACTIVE_LAYERS : []}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onClick={onClick}
        cursor={cursor}
        dragRotate={false}
        style={{ width: '100%', height: '100%' }}
        reuseMaps
        attributionControl={false}
      >
        <AttributionControl compact position="bottom-right" />
        <NavigationControl position="top-right" showCompass={false} />
        {!compact && <ScaleControl position="bottom-right" unit="imperial" />}

        {/* Invisible anchor layer: the heatmap is inserted below it, the routes stack above it. */}
        <Source id="anchor" type="geojson" data={EMPTY}>
          <Layer id={ROUTES_ANCHOR_LAYER} type="line" paint={{ 'line-opacity': 0 }} />
        </Source>

        {heatmap && <HeatmapLayers heatmap={heatmap} layer={heatmapLayer} frame={frame} visible={showHeatmap} />}

        {plan && (
          <>
            <RouteLayers
              routes={plan.routes}
              selectedId={selectedRouteId}
              showAll={showAllRoutes}
              selectedCheckpoint={selectedCheckpoint}
              dark={mode === 'dark'}
            />
            <StaticMarkers plan={plan} selectedId={selectedRouteId} showAll={showAllRoutes} onSelect={selectRoute} />
            <TruckMarkers routes={plan.routes} selectedId={selectedRouteId} showAll={showAllRoutes} seconds={seconds} />
          </>
        )}

        {hover?.kind === 'checkpoint' && plan && (
          <Popup
            longitude={hover.checkpoint.lon}
            latitude={hover.checkpoint.lat}
            closeButton={false}
            closeOnClick={false}
            anchor="bottom"
            offset={12}
            maxWidth="300px"
          >
            <CheckpointPopup routeId={hover.routeId} checkpoint={hover.checkpoint} departure={plan.request.departure_time} />
          </Popup>
        )}
      </Map>

      {hover?.kind === 'cell' && heatmap && (
        <CellTooltip heatmap={heatmap} index={hover.index} frame={frame} x={hover.x} y={hover.y} />
      )}
    </Box>
  );
}

function CheckpointPopup({ routeId, checkpoint: c, departure }: { routeId: string; checkpoint: Checkpoint; departure: string }) {
  const w = c.weather;
  return (
    <Paper elevation={6} sx={{ p: 1.5, minWidth: 220 }}>
      <Stack spacing={0.75}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
          <Typography variant="subtitle2">
            Route {routeId} · mile {c.mile.toFixed(0)}
          </Typography>
          <RiskChip level={c.risk.level} />
        </Box>
        <Typography variant="caption" color="text.secondary">
          ETA {formatEta(c.eta, departure)}
        </Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 1.5, rowGap: 0.25 }}>
          <Typography variant="caption" color="text.secondary">Wind</Typography>
          <Typography variant="caption">
            {w.wind_mph.toFixed(0)} mph{w.gust_mph != null ? ` (gusts ${w.gust_mph.toFixed(0)})` : ''} · {RISK_LABEL[c.risk.wind]}
          </Typography>
          <Typography variant="caption" color="text.secondary">Rain</Typography>
          <Typography variant="caption">{formatRate(w.rain_in_hr)} in/hr · {RISK_LABEL[c.risk.rain]}</Typography>
          <Typography variant="caption" color="text.secondary">Snow</Typography>
          <Typography variant="caption">{formatRate(w.snow_in_hr)} in/hr · {RISK_LABEL[c.risk.snow]}</Typography>
        </Box>
        {c.risk.factors.length > 0 && (
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {c.risk.factors.map((f) => (
              <Typography key={f} component="li" variant="caption" sx={{ fontWeight: f.startsWith('Load rule') ? 700 : 400 }}>
                {f}
              </Typography>
            ))}
          </Box>
        )}
      </Stack>
    </Paper>
  );
}

function CellTooltip({ heatmap, index, frame, x, y }: { heatmap: Heatmap; index: number; frame: number; x: number; y: number }) {
  const level = riskFromScore(heatmap.risk[index][frame]);
  return (
    <Paper
      elevation={4}
      sx={{ position: 'absolute', left: x + 14, top: y + 14, px: 1.25, py: 0.75, pointerEvents: 'none', zIndex: 2 }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <RiskChip level={level} />
        <Typography variant="caption" sx={{ whiteSpace: 'nowrap' }}>
          {heatmap.wind_mph[index][frame]} mph · rain {formatRate(heatmap.rain_in_hr[index][frame])} · snow{' '}
          {formatRate(heatmap.snow_in_hr[index][frame])} in/hr
        </Typography>
      </Stack>
    </Paper>
  );
}

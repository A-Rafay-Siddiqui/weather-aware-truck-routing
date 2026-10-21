import { memo, useMemo } from 'react';
import type { Feature, FeatureCollection, LineString, Point } from 'geojson';
import { Layer, Source } from 'map-engine';
import type { RouteResult } from '../../api/types';
import { sliceByMiles } from '../../lib/path';
import { RISK_COLOR } from '../../lib/risk';
import { ROUTE_COLORS } from '../RouteCards';

export const INTERACTIVE_LAYERS = ['checkpoints', 'route-hit'];

interface Props {
  routes: RouteResult[];
  selectedId: string | null;
  showAll: boolean;
  selectedCheckpoint: number | null;
  dark: boolean;
}

type Line = Feature<LineString>;

/** All routes, plus the selected route drawn segment by segment in its checkpoint risk colors. */
export const RouteLayers = memo(function RouteLayers({ routes, selectedId, showAll, selectedCheckpoint, dark }: Props) {
  const lines = useMemo<FeatureCollection<LineString>>(
    () => ({
      type: 'FeatureCollection',
      features: routes.map<Line>((r) => ({
        type: 'Feature',
        properties: { id: r.id, color: ROUTE_COLORS[r.id] ?? '#64748b', selected: r.id === selectedId },
        geometry: { type: 'LineString', coordinates: r.path.map((p) => [p[0], p[1]]) },
      })),
    }),
    [routes, selectedId],
  );

  const riskSegments = useMemo<FeatureCollection<LineString>>(() => {
    const route = routes.find((r) => r.id === selectedId);
    return {
      type: 'FeatureCollection',
      features: (route?.checkpoints ?? []).map<Line>((c) => ({
        type: 'Feature',
        properties: { color: RISK_COLOR[c.risk.level] },
        geometry: { type: 'LineString', coordinates: sliceByMiles(route!.path, c.segment[0], c.segment[1]) },
      })),
    };
  }, [routes, selectedId]);

  const checkpoints = useMemo<FeatureCollection<Point>>(
    () => ({
      type: 'FeatureCollection',
      features: routes.flatMap((r) =>
        r.checkpoints.map((c) => ({
          type: 'Feature' as const,
          properties: {
            routeId: r.id,
            index: c.index,
            color: RISK_COLOR[c.risk.level],
            selected: r.id === selectedId,
            active: r.id === selectedId && c.index === selectedCheckpoint,
          },
          geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] },
        })),
      ),
    }),
    [routes, selectedId, selectedCheckpoint],
  );

  const casing = dark ? '#0d1116' : '#ffffff';
  const othersFilter = showAll ? ['!=', ['get', 'selected'], true] : ['==', 1, 0];
  const checkpointFilter = showAll ? ['all'] : ['==', ['get', 'selected'], true];

  return (
    <>
      <Source id="routes" type="geojson" data={lines}>
        <Layer
          id="route-others-casing"
          type="line"
          filter={othersFilter as never}
          layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          paint={{ 'line-color': casing, 'line-width': 7, 'line-opacity': 0.8 }}
        />
        <Layer
          id="route-others"
          type="line"
          filter={othersFilter as never}
          layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          paint={{ 'line-color': ['get', 'color'], 'line-width': 4, 'line-opacity': 0.75 }}
        />
        <Layer
          id="route-selected-casing"
          type="line"
          filter={['==', ['get', 'selected'], true]}
          layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          paint={{ 'line-color': casing, 'line-width': 11 }}
        />
        {/* Wide transparent line so routes are easy to hover and click. */}
        <Layer
          id="route-hit"
          type="line"
          filter={showAll ? ['all'] : ['==', ['get', 'selected'], true]}
          paint={{ 'line-color': '#000', 'line-width': 16, 'line-opacity': 0 }}
        />
      </Source>
      <Source id="route-risk" type="geojson" data={riskSegments}>
        <Layer
          id="route-risk-line"
          type="line"
          layout={{ 'line-join': 'round', 'line-cap': 'round' }}
          paint={{ 'line-color': ['get', 'color'], 'line-width': 6 }}
        />
      </Source>
      <Source id="checkpoints" type="geojson" data={checkpoints}>
        <Layer
          id="checkpoints"
          type="circle"
          filter={checkpointFilter as never}
          paint={{
            'circle-color': ['get', 'color'],
            'circle-radius': [
              'interpolate',
              ['linear'],
              ['zoom'],
              4,
              ['case', ['get', 'active'], 8, ['get', 'selected'], 4, 2.5],
              10,
              ['case', ['get', 'active'], 11, ['get', 'selected'], 7, 4.5],
            ],
            'circle-stroke-color': ['case', ['get', 'active'], '#043344', casing],
            'circle-stroke-width': ['case', ['get', 'active'], 3, 1.5],
            'circle-opacity': ['case', ['get', 'selected'], 1, 0.75],
            'circle-stroke-opacity': ['case', ['get', 'selected'], 1, 0.75],
          }}
        />
      </Source>
    </>
  );
});

import { memo, useMemo } from 'react';
import { Marker } from 'map-engine';
import type { Plan, RouteResult } from '../../api/types';
import { formatDuration } from '../../lib/format';
import { positionAtMile, positionAtTime } from '../../lib/path';
import { ROUTE_COLORS } from '../RouteCards';

const TRUCK_SVG = (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
    <path d="M3 5h11v9H3zM14 8h3.5L21 11.5V14h-7zM6.5 15.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4m11 0a2 2 0 1 1 0 4 2 2 0 0 1 0-4" />
  </svg>
);

/** Origin/destination pins, a label per route, and HOS stops on the selected route. */
export const StaticMarkers = memo(function StaticMarkers({
  plan,
  selectedId,
  showAll,
  onSelect,
}: {
  plan: Plan;
  selectedId: string | null;
  showAll: boolean;
  onSelect: (id: string) => void;
}) {
  const labels = useMemo(
    () =>
      plan.routes.map((r) => {
        // Spread labels along the route so overlapping routes don't stack them.
        const at = r.distance_miles * (0.35 + 0.15 * (r.id.charCodeAt(0) - 65));
        return { route: r, pos: positionAtMile(r.path, at) };
      }),
    [plan],
  );
  const selected = plan.routes.find((r) => r.id === selectedId);
  const { origin, destination } = plan.request;

  return (
    <>
      <Marker longitude={origin.lon} latitude={origin.lat}>
        <div className="endpoint-marker" style={{ background: '#2e9e5b' }} title={origin.label} />
      </Marker>
      <Marker longitude={destination.lon} latitude={destination.lat}>
        <div className="endpoint-marker" style={{ background: '#d93a3a' }} title={destination.label} />
      </Marker>

      {selected?.stops.map((s) => (
        <Marker key={`${s.kind}-${s.start_offset_s}`} longitude={s.lon} latitude={s.lat} anchor="bottom" offset={[0, -6]}>
          <div className="stop-marker" title={`${s.kind === 'rest' ? '10h rest' : '30 min break'} at mile ${s.mile.toFixed(0)}`}>
            {s.kind === 'rest' ? 'REST 10h' : 'BREAK'}
          </div>
        </Marker>
      ))}

      {labels
        .filter(({ route }) => showAll || route.id === selectedId)
        .map(({ route, pos }) => (
          <Marker key={route.id} longitude={pos[0]} latitude={pos[1]} anchor="bottom" offset={[0, -10]}>
            <div
              className={`route-label${route.id === selectedId ? ' selected' : ''}`}
              style={{ borderColor: ROUTE_COLORS[route.id] }}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(route.id);
              }}
            >
              {route.recommended && <span className="star">★</span>}
              {route.id} · {formatDuration(route.travel_time_s)}
            </div>
          </Marker>
        ))}
    </>
  );
});

/** Where each truck would be at the slider's time; parked during HOS stops, hidden before/after the trip. */
export function TruckMarkers({
  routes,
  selectedId,
  showAll,
  seconds,
}: {
  routes: RouteResult[];
  selectedId: string | null;
  showAll: boolean;
  seconds: number;
}) {
  return (
    <>
      {routes
        .filter((r) => showAll || r.id === selectedId)
        .map((r) => {
          const [lon, lat] = positionAtTime(r.path, seconds);
          const arrived = seconds >= r.travel_time_s;
          const isSelected = r.id === selectedId;
          return (
            <Marker key={r.id} longitude={lon} latitude={lat} style={{ zIndex: isSelected ? 3 : 2 }}>
              <div
                className="truck-marker"
                title={`Route ${r.id}${arrived ? ' – arrived' : ''}`}
                style={{
                  background: ROUTE_COLORS[r.id],
                  opacity: arrived ? 0.45 : isSelected ? 1 : 0.8,
                  transform: isSelected ? 'scale(1.1)' : 'scale(0.85)',
                }}
              >
                {TRUCK_SVG}
              </div>
            </Marker>
          );
        })}
    </>
  );
}

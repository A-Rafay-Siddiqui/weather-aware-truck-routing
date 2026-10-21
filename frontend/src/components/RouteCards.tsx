import StarIcon from '@mui/icons-material/Star';
import { Box, Card, CardActionArea, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { memo } from 'react';
import type { RouteResult } from '../api/types';
import { formatDuration, formatEta, formatMiles } from '../lib/format';
import { usePlannerDispatch } from '../state/PlannerContext';
import { MilesAtRisk, RiskChip, RiskStrip } from './RiskVisuals';

export const ROUTE_COLORS: Record<string, string> = { A: '#2563eb', B: '#0891b2', C: '#64748b' };

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Tooltip title={hint ?? ''} disableHoverListener={!hint}>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" noWrap component="div">
          {label}
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
          {value}
        </Typography>
      </Box>
    </Tooltip>
  );
}

const RouteCard = memo(function RouteCard({ route, selected }: { route: RouteResult; selected: boolean }) {
  const dispatch = usePlannerDispatch();
  const stopTime = route.travel_time_s - route.drive_time_s;
  return (
    <Card
      sx={{
        borderColor: selected ? 'primary.main' : undefined,
        borderWidth: selected ? 2 : 1,
        transition: 'border-color .15s',
      }}
    >
      <CardActionArea onClick={() => dispatch({ type: 'SELECT_ROUTE', routeId: route.id })} sx={{ p: 1.5 }}>
        <Stack spacing={1.25}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box
              sx={{
                width: 26,
                height: 26,
                borderRadius: 1,
                bgcolor: ROUTE_COLORS[route.id] ?? 'grey.600',
                color: '#fff',
                display: 'grid',
                placeItems: 'center',
                fontWeight: 700,
                fontSize: 14,
                flexShrink: 0,
              }}
            >
              {route.id}
            </Box>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="subtitle2" noWrap>
                {route.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Rank #{route.rank} · {route.strategy}
              </Typography>
            </Box>
            {route.recommended ? (
              <Chip icon={<StarIcon />} label="Best route" size="small" color="primary" />
            ) : (
              <RiskChip level={route.risk.max_level} />
            )}
          </Box>

          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 1 }}>
            <Stat label="Distance" value={formatMiles(route.distance_miles)} />
            <Stat
              label="Travel time"
              value={formatDuration(route.travel_time_s)}
              hint={
                stopTime > 0
                  ? `${formatDuration(route.drive_time_s)} driving + ${formatDuration(stopTime)} HOS stops`
                  : `Includes ${formatDuration(route.traffic_delay_s)} predicted traffic delay`
              }
            />
            <Stat label="Arrives" value={formatEta(route.arrival_time, route.departure_time)} />
            <Stat
              label="Avg risk"
              value={route.risk.average_score.toFixed(2)}
              hint="Mile-weighted average of checkpoint risk (Low 0 … No Travel 4)"
            />
          </Box>

          <RiskStrip checkpoints={route.checkpoints} totalMiles={route.distance_miles} departure={route.departure_time} />
          <MilesAtRisk miles={route.risk.miles_by_level} />
        </Stack>
      </CardActionArea>
    </Card>
  );
});

export function RouteCards({ routes, selectedId }: { routes: RouteResult[]; selectedId: string | null }) {
  const ordered = [...routes].sort((a, b) => a.rank - b.rank);
  return (
    <Stack spacing={1.25}>
      {ordered.map((r) => (
        <RouteCard key={r.id} route={r} selected={r.id === selectedId} />
      ))}
    </Stack>
  );
}

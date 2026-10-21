import { Box, Stack, Tab, Tabs, Typography, useTheme } from '@mui/material';
import { LineChart } from '@mui/x-charts/LineChart';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { useMemo, useState } from 'react';
import type { Checkpoint, RouteResult } from '../api/types';
import { formatEta, formatRate } from '../lib/format';
import { RISK_COLOR, RISK_LABEL, RISK_ORDER } from '../lib/risk';
import { usePlannerDispatch, usePlannerState } from '../state/PlannerContext';
import { RiskChip } from './RiskVisuals';

export function RouteDetails({ route }: { route: RouteResult }) {
  const [tab, setTab] = useState<'checkpoints' | 'profile'>('checkpoints');
  return (
    <Stack sx={{ height: '100%', minHeight: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant="subtitle2" sx={{ mr: 2 }} noWrap>
          Route {route.id} · {route.name}
        </Typography>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ minHeight: 40, '& .MuiTab-root': { minHeight: 40, py: 0 } }}>
          <Tab value="checkpoints" label={`Checkpoints (${route.checkpoints.length})`} />
          <Tab value="profile" label="Risk profile" />
        </Tabs>
      </Box>
      <Box sx={{ flex: 1, minHeight: 0 }}>
        {tab === 'checkpoints' ? <CheckpointGrid route={route} /> : <RiskProfile route={route} />}
      </Box>
    </Stack>
  );
}

function CheckpointGrid({ route }: { route: RouteResult }) {
  const dispatch = usePlannerDispatch();
  const { selectedCheckpoint } = usePlannerState();

  const columns = useMemo<GridColDef<Checkpoint>[]>(
    () => [
      { field: 'mile', headerName: 'Mile', width: 70, type: 'number', valueFormatter: (v: number) => v.toFixed(0) },
      {
        field: 'eta',
        headerName: 'ETA',
        width: 120,
        valueGetter: (_, row) => Date.parse(row.eta),
        renderCell: ({ row }) => formatEta(row.eta, route.departure_time),
      },
      {
        field: 'wind',
        headerName: 'Wind (gust)',
        width: 105,
        type: 'number',
        valueGetter: (_, row) => row.weather.wind_mph,
        renderCell: ({ row }) =>
          `${row.weather.wind_mph.toFixed(0)}${row.weather.gust_mph != null ? ` (${row.weather.gust_mph.toFixed(0)})` : ''} mph`,
      },
      {
        field: 'rain',
        headerName: 'Rain in/hr',
        width: 95,
        type: 'number',
        valueGetter: (_, row) => row.weather.rain_in_hr,
        valueFormatter: (v: number) => formatRate(v),
      },
      {
        field: 'snow',
        headerName: 'Snow in/hr',
        width: 95,
        type: 'number',
        valueGetter: (_, row) => row.weather.snow_in_hr,
        valueFormatter: (v: number) => formatRate(v),
      },
      {
        field: 'risk',
        headerName: 'Risk',
        width: 110,
        valueGetter: (_, row) => row.risk.score,
        renderCell: ({ row }) => <RiskChip level={row.risk.level} />,
      },
      {
        field: 'factors',
        headerName: 'Why',
        flex: 1,
        minWidth: 220,
        sortable: false,
        valueGetter: (_, row) => row.risk.factors.join(' · ') || '—',
      },
    ],
    [route.departure_time],
  );

  return (
    <DataGrid
      rows={route.checkpoints}
      columns={columns}
      getRowId={(r) => r.index}
      density="compact"
      hideFooter={route.checkpoints.length <= 100}
      disableColumnMenu
      rowSelectionModel={{ type: 'include', ids: new Set(selectedCheckpoint != null ? [selectedCheckpoint] : []) }}
      onRowClick={({ row }) => dispatch({ type: 'SELECT_CHECKPOINT', index: row.index, lon: row.lon, lat: row.lat })}
      sx={{ '& .MuiDataGrid-row': { cursor: 'pointer' }, '& .MuiDataGrid-cell:focus': { outline: 'none' } }}
    />
  );
}

const CHART_MARGIN = 8;
const AXIS_WIDTH = 56;

/** Wind and precipitation along the route at each checkpoint's ETA, with the risk band underneath. */
function RiskProfile({ route }: { route: RouteResult }) {
  const theme = useTheme();
  const cps = route.checkpoints;
  const miles = cps.map((c) => c.mile);
  return (
    <Stack sx={{ height: '100%', px: 1, pb: 1 }}>
      <Box sx={{ flex: 1, minHeight: 0 }}>
        <LineChart
          xAxis={[
            {
              data: miles,
              label: 'Mile',
              valueFormatter: (v: number) => v.toFixed(0),
            },
          ]}
          yAxis={[
            { id: 'wind', label: 'Wind mph', width: AXIS_WIDTH, min: 0, max: Math.max(60, ...cps.map((c) => c.weather.wind_mph)) },
            { id: 'precip', label: 'in/hr', position: 'right', width: AXIS_WIDTH, min: 0, max: Math.max(0.5, ...cps.map((c) => Math.max(c.weather.rain_in_hr, c.weather.snow_in_hr))) },
          ]}
          series={[
            {
              data: cps.map((c) => c.weather.wind_mph),
              label: 'Wind',
              yAxisId: 'wind',
              color: theme.palette.primary.main,
              showMark: false,
              valueFormatter: (v) => `${v?.toFixed(0)} mph`,
            },
            {
              data: cps.map((c) => c.weather.gust_mph ?? null),
              label: 'Gusts',
              yAxisId: 'wind',
              color: theme.palette.text.disabled,
              showMark: false,
              valueFormatter: (v) => (v == null ? '–' : `${v.toFixed(0)} mph`),
            },
            {
              data: cps.map((c) => c.weather.rain_in_hr),
              label: 'Rain',
              yAxisId: 'precip',
              color: '#3a86ff',
              area: true,
              showMark: false,
              valueFormatter: (v) => `${v?.toFixed(2)} in/hr`,
            },
            {
              data: cps.map((c) => c.weather.snow_in_hr),
              label: 'Snow',
              yAxisId: 'precip',
              color: '#8e9fc8',
              area: true,
              showMark: false,
              valueFormatter: (v) => `${v?.toFixed(2)} in/hr`,
            },
          ]}
          margin={{ top: 8, bottom: 4, left: CHART_MARGIN, right: CHART_MARGIN }}
          slotProps={{ legend: { position: { vertical: 'top', horizontal: 'end' } } }}
          sx={{ '& .MuiAreaElement-root': { fillOpacity: 0.25 } }}
        />
      </Box>
      {/* Inset by margin + axis width so the band lines up with the plot area above. */}
      <Box sx={{ display: 'flex', alignItems: 'center', px: `${CHART_MARGIN + AXIS_WIDTH}px`, position: 'relative' }}>
        <Typography variant="caption" color="text.secondary" sx={{ position: 'absolute', left: 8 }}>
          Risk
        </Typography>
        <Box sx={{ flex: 1, display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden' }}>
          {cps.map((c) => (
            <Box
              key={c.index}
              sx={{ width: `${((c.segment[1] - c.segment[0]) / route.distance_miles) * 100}%`, bgcolor: RISK_COLOR[c.risk.level] }}
            />
          ))}
        </Box>
      </Box>
      <Box sx={{ display: 'flex', gap: 1.5, justifyContent: 'center', mt: 0.75, flexWrap: 'wrap' }}>
        {RISK_ORDER.map((k) => (
          <Box key={k} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 10, height: 10, borderRadius: '2px', bgcolor: RISK_COLOR[k] }} />
            <Typography variant="caption">{RISK_LABEL[k]}</Typography>
          </Box>
        ))}
      </Box>
    </Stack>
  );
}

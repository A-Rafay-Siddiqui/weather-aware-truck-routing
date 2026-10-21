import { Box, FormControlLabel, Paper, Stack, Switch, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { legendStops, type HeatmapLayer } from '../../lib/heatmapFrames';
import type { RiskKey } from '../../api/types';
import { RISK_ORDER } from '../../lib/risk';
import { usePlannerDispatch, usePlannerState } from '../../state/PlannerContext';

const SHORT_LABEL: Record<RiskKey, string> = {
  low: 'Low',
  moderate: 'Mod.',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
};

const LAYERS: { value: HeatmapLayer; label: string; unit: string }[] = [
  { value: 'risk', label: 'Risk', unit: '' },
  { value: 'wind', label: 'Wind', unit: 'mph' },
  { value: 'rain', label: 'Rain', unit: 'in/hr' },
  { value: 'snow', label: 'Snow', unit: 'in/hr' },
];

export function MapControls({ hasHeatmap }: { hasHeatmap: boolean }) {
  const { heatmapLayer, showHeatmap, showAllRoutes } = usePlannerState();
  const dispatch = usePlannerDispatch();
  const layer = LAYERS.find((l) => l.value === heatmapLayer)!;
  const stops = legendStops(heatmapLayer);

  return (
    <Paper elevation={3} sx={{ p: 1.25, width: { xs: '100%', md: 256 } }}>
      <Stack spacing={1}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="overline" color="text.secondary">
            Weather heatmap
          </Typography>
          <Switch
            size="small"
            checked={showHeatmap}
            disabled={!hasHeatmap}
            onChange={() => dispatch({ type: 'TOGGLE_HEATMAP' })}
            slotProps={{ input: { 'aria-label': 'Show weather heatmap' } }}
          />
        </Box>
        <ToggleButtonGroup
          exclusive
          size="small"
          fullWidth
          color="primary"
          value={heatmapLayer}
          disabled={!hasHeatmap}
          onChange={(_, v) => v && dispatch({ type: 'SET_HEATMAP_LAYER', layer: v })}
        >
          {LAYERS.map((l) => (
            <ToggleButton key={l.value} value={l.value} sx={{ px: 0.5, fontSize: 12 }}>
              {l.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        <Box>
          <Box sx={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden' }}>
            {stops.map((s) => (
              <Box key={s.value} sx={{ flex: 1, bgcolor: s.color }} />
            ))}
          </Box>
          <Box sx={{ display: 'flex', mt: 0.25 }}>
            {stops.map((s) => (
              <Typography key={s.value} variant="caption" sx={{ flex: 1, fontSize: 10, color: 'text.secondary' }} noWrap>
                {heatmapLayer === 'risk' ? SHORT_LABEL[RISK_ORDER[s.value]] : `${s.value}`}
              </Typography>
            ))}
          </Box>
          {layer.unit && (
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10 }}>
              {layer.label} ({layer.unit}). Colors match the risk thresholds.
            </Typography>
          )}
        </Box>

        <FormControlLabel
          sx={{ ml: 0 }}
          control={<Switch size="small" checked={showAllRoutes} onChange={() => dispatch({ type: 'TOGGLE_ALL_ROUTES' })} />}
          label={<Typography variant="body2">Display all routes</Typography>}
        />
      </Stack>
    </Paper>
  );
}

import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { Box, CircularProgress, IconButton, Paper, Slider, Stack, Tooltip, Typography } from '@mui/material';
import dayjs from 'dayjs';
import { useEffect, useMemo, useRef } from 'react';
import type { Heatmap, Plan } from '../../api/types';
import { FORECAST_HOURS, forecastStartMs, secondsAfterDeparture } from '../../lib/forecast';
import { mileAtTime } from '../../lib/path';
import { useForecastTime, usePlannerState } from '../../state/PlannerContext';

const HOURS_PER_SECOND = 2.5; // playback speed

/** 0–48 h forecast scrubber. Playback runs on requestAnimationFrame, so trucks glide and frames crossfade. */
export function ForecastSlider({ plan, heatmap, loading }: { plan: Plan; heatmap?: Heatmap; loading: boolean }) {
  const { hour, playing, setHour, setPlaying } = useForecastTime();
  const { selectedRouteId } = usePlannerState();
  const hourRef = useRef(hour);
  hourRef.current = hour;

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    // Restart from the beginning if play is pressed at the end.
    if (hourRef.current >= FORECAST_HOURS) setHour(0);
    const tick = (now: number) => {
      const next = hourRef.current + ((now - last) / 1000) * HOURS_PER_SECOND;
      last = now;
      if (next >= FORECAST_HOURS) {
        setHour(FORECAST_HOURS);
        setPlaying(false);
        return;
      }
      setHour(next);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the loop reads hour through a ref
  }, [playing]);

  const start = forecastStartMs(plan, heatmap);
  const marks = useMemo(
    () =>
      [0, 12, 24, 36, 48].map((h) => ({
        value: h,
        label: dayjs(start + h * 3_600_000).format('ddd h A'),
      })),
    [start],
  );

  const route = plan.routes.find((r) => r.id === selectedRouteId);
  const seconds = secondsAfterDeparture(plan, hour, heatmap);
  const status = route ? truckStatus(route, seconds) : '';

  return (
    <Paper elevation={4} sx={{ px: 2, pt: 1, pb: 0.5, width: '100%' }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
        <Tooltip title={playing ? 'Pause' : 'Play forecast'}>
          <span>
            <IconButton
              color="primary"
              onClick={() => setPlaying(!playing)}
              disabled={!heatmap}
              aria-label={playing ? 'Pause forecast' : 'Play forecast'}
            >
              {playing ? <PauseIcon /> : <PlayArrowIcon />}
            </IconButton>
          </span>
        </Tooltip>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 1 }}>
            <Typography variant="subtitle2" noWrap>
              {dayjs(start + hour * 3_600_000).format('ddd MMM D, h:mm A')}
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                +{Math.floor(hour)}h forecast
              </Typography>
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: { xs: 'none', sm: 'block' } }}>
              {loading ? (
                <>
                  <CircularProgress size={10} sx={{ mr: 0.75 }} />
                  Loading weather grid…
                </>
              ) : (
                status
              )}
            </Typography>
          </Box>
          <Slider
            size="small"
            min={0}
            max={FORECAST_HOURS}
            step={1}
            value={hour}
            marks={marks}
            onChange={(_, v) => {
              setPlaying(false);
              setHour(v as number);
            }}
            getAriaValueText={(v) => dayjs(start + v * 3_600_000).format('ddd MMM D, h A')}
            aria-label="Forecast hour"
            sx={{ '& .MuiSlider-markLabel': { fontSize: 11 }, mb: 1.5 }}
          />
        </Box>
      </Stack>
    </Paper>
  );
}

function truckStatus(route: Plan['routes'][number], seconds: number): string {
  if (seconds < 0) return `Route ${route.id}: not departed`;
  if (seconds >= route.travel_time_s) return `Route ${route.id}: arrived`;
  const stop = route.stops.find((s) => seconds >= s.start_offset_s && seconds < s.start_offset_s + s.duration_s);
  if (stop) return `Route ${route.id}: ${stop.kind === 'rest' ? '10h rest' : '30 min break'} at mile ${stop.mile.toFixed(0)}`;
  return `Route ${route.id}: truck at mile ${mileAtTime(route.path, seconds).toFixed(0)} of ${route.distance_miles.toFixed(0)}`;
}

import DarkModeIcon from '@mui/icons-material/DarkModeOutlined';
import HistoryIcon from '@mui/icons-material/History';
import LightModeIcon from '@mui/icons-material/LightModeOutlined';
import RuleIcon from '@mui/icons-material/RuleOutlined';
import ShareIcon from '@mui/icons-material/IosShare';
import {
  Alert,
  AppBar,
  Box,
  Button,
  IconButton,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Skeleton,
  Snackbar,
  Stack,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { errorMessage } from './api/client';
import { useCreatePlan, useHealth, useHeatmap, usePlan, useRecentPlans } from './api/queries';
import type { PlanInput } from './api/types';
import { useColorMode } from './components/ColorModeProvider';
import { ForecastSlider } from './components/map/ForecastSlider';
import { MapControls } from './components/map/MapControls';
import { TripMap } from './components/map/TripMap';
import { RecommendationCard } from './components/RecommendationCard';
import { RouteCards } from './components/RouteCards';
import { TripForm } from './components/TripForm';
import { formatDateTime } from './lib/format';
import { ForecastTimeProvider, PlannerProvider, useForecastTime, usePlannerDispatch, usePlannerState } from './state/PlannerContext';

// Data Grid, Charts and the rules dialog are only needed after a plan exists or on demand.
const RouteDetails = lazy(() => import('./components/RouteDetails').then((m) => ({ default: m.RouteDetails })));
const RiskRulesDialog = lazy(() => import('./components/RiskRulesDialog').then((m) => ({ default: m.RiskRulesDialog })));

const SIDEBAR_WIDTH = 420;
const DETAILS_HEIGHT = 260;

export default function App() {
  return (
    <PlannerProvider>
      <ForecastTimeProvider>
        <Planner />
      </ForecastTimeProvider>
    </PlannerProvider>
  );
}

function Planner() {
  const theme = useTheme();
  const desktop = useMediaQuery(theme.breakpoints.up('md'));
  const { planId, selectedRouteId } = usePlannerState();
  const dispatch = usePlannerDispatch();
  const { setHour, setPlaying } = useForecastTime();
  const [error, setError] = useState<string | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const mobileScroller = useRef<HTMLDivElement>(null);

  const createPlan = useCreatePlan();
  const planQuery = usePlan(planId);
  const plan = planQuery.data;
  const heatmapQuery = useHeatmap(plan?.id ?? null);
  const selected = plan?.routes.find((r) => r.id === selectedRouteId);

  // Keep ?plan=<id> in the URL so a plan can be shared or reloaded.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (planId) url.searchParams.set('plan', planId);
    else url.searchParams.delete('plan');
    window.history.replaceState(null, '', url);
  }, [planId]);

  // Opening a shared link: select the recommended route once the plan arrives.
  useEffect(() => {
    if (plan && !selectedRouteId) dispatch({ type: 'SET_PLAN', planId: plan.id, recommendedRouteId: plan.recommended_route_id });
  }, [plan, selectedRouteId, dispatch]);

  useEffect(() => {
    if (planQuery.error) setError(errorMessage(planQuery.error));
    if (heatmapQuery.error) setError(`Heatmap unavailable: ${errorMessage(heatmapQuery.error)}`);
  }, [planQuery.error, heatmapQuery.error]);

  // On phones the form sits below the map: once a new plan has rendered, scroll the map into view.
  useEffect(() => {
    if (plan?.id) mobileScroller.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [plan?.id]);

  const submit = (input: PlanInput) =>
    createPlan.mutate(input, {
      onSuccess: (p) => {
        setPlaying(false);
        setHour(0);
        dispatch({ type: 'SET_PLAN', planId: p.id, recommendedRouteId: p.recommended_route_id });
      },
      onError: (e) => setError(errorMessage(e)),
    });

  const sidebar = (
    <Stack spacing={2} sx={{ p: 2 }}>
      <WakeNotice />
      <TripForm submitting={createPlan.isPending} onSubmit={submit} initial={plan?.request ?? null} />
      {planQuery.isLoading && <Skeleton variant="rounded" height={220} />}
      {plan && (
        <>
          <RecommendationCard plan={plan} />
          <Typography variant="overline" color="text.secondary" sx={{ pt: 0.5 }}>
            Route options
          </Typography>
          <RouteCards routes={plan.routes} selectedId={selectedRouteId} />
        </>
      )}
    </Stack>
  );

  const overlayPadding = desktop
    ? { top: 70, bottom: 170, left: 300, right: 70 }
    : { top: 30, bottom: 30, left: 30, right: 30 };

  const forecastControls = plan && (
    <ForecastSlider plan={plan} heatmap={heatmapQuery.data} loading={heatmapQuery.isFetching} />
  );

  const mapArea = (
    <Box sx={{ position: 'relative', flex: desktop ? 1 : 'none', height: desktop ? 'auto' : '55vh', minHeight: 0 }}>
      <TripMap plan={plan} heatmap={heatmapQuery.data} padding={overlayPadding} compact={!desktop} />
      {plan && desktop && (
        <>
          <Box sx={{ position: 'absolute', top: 12, left: 12 }}>
            <MapControls hasHeatmap={!!heatmapQuery.data} />
          </Box>
          <Box sx={{ position: 'absolute', left: 12, right: 56, bottom: 28, maxWidth: 820, mx: 'auto' }}>
            {forecastControls}
          </Box>
        </>
      )}
      {!plan && !planQuery.isLoading && <EmptyMapHint />}
    </Box>
  );

  return (
    <Box sx={{ height: '100dvh', display: 'flex', flexDirection: 'column', bgcolor: 'background.default' }}>
      <Header onRules={() => setRulesOpen(true)} canShare={!!plan} />
      {desktop ? (
        <Box sx={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <Paper
            square
            elevation={0}
            sx={{ width: SIDEBAR_WIDTH, flexShrink: 0, overflowY: 'auto', borderRight: 1, borderColor: 'divider' }}
          >
            {sidebar}
          </Paper>
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            {mapArea}
            {selected && (
              <Paper square elevation={0} sx={{ height: DETAILS_HEIGHT, flexShrink: 0, borderTop: 1, borderColor: 'divider' }}>
                <Suspense fallback={<Skeleton variant="rectangular" height="100%" />}>
                  <RouteDetails route={selected} />
                </Suspense>
              </Paper>
            )}
          </Box>
        </Box>
      ) : (
        <Box ref={mobileScroller} sx={{ flex: 1, overflowY: 'auto', overflowAnchor: 'none' }}>
          {mapArea}
          {plan && (
            <Stack spacing={1.5} sx={{ p: 1.5 }}>
              {forecastControls}
              <MapControls hasHeatmap={!!heatmapQuery.data} />
            </Stack>
          )}
          {sidebar}
          {selected && (
            <Paper square elevation={0} sx={{ height: 360, borderTop: 1, borderColor: 'divider' }}>
              <Suspense fallback={<Skeleton variant="rectangular" height="100%" />}>
                <RouteDetails route={selected} />
              </Suspense>
            </Paper>
          )}
        </Box>
      )}

      {rulesOpen && (
        <Suspense fallback={null}>
          <RiskRulesDialog open onClose={() => setRulesOpen(false)} />
        </Suspense>
      )}
      <Snackbar open={!!error} autoHideDuration={8000} onClose={() => setError(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
        <Alert severity="error" variant="filled" onClose={() => setError(null)} sx={{ maxWidth: 520 }}>
          {error}
        </Alert>
      </Snackbar>
    </Box>
  );
}

function Header({ onRules, canShare }: { onRules: () => void; canShare: boolean }) {
  const { mode, toggle } = useColorMode();
  const [copied, setCopied] = useState(false);
  return (
    <AppBar position="static" elevation={0}>
      <Toolbar variant="dense" sx={{ gap: 1 }}>
        <Box component="img" src="/favicon.svg" alt="" sx={{ width: 26, height: 26 }} />
        <Typography variant="h6" sx={{ fontSize: 17, flex: 1 }} noWrap>
          Weather-Aware Truck Routing
        </Typography>
        <Tooltip title="Risk rules">
          <IconButton color="inherit" onClick={onRules} aria-label="Risk rules">
            <RuleIcon />
          </IconButton>
        </Tooltip>
        <RecentPlansMenu />
        {canShare && (
          <Tooltip title={copied ? 'Link copied' : 'Copy link to this plan'}>
            <IconButton
              color="inherit"
              aria-label="Copy link"
              onClick={() => navigator.clipboard?.writeText(window.location.href).then(() => setCopied(true))}
              onMouseLeave={() => setCopied(false)}
            >
              <ShareIcon />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title={mode === 'dark' ? 'Light mode' : 'Dark mode'}>
          <IconButton color="inherit" onClick={toggle} aria-label="Toggle dark mode">
            {mode === 'dark' ? <LightModeIcon /> : <DarkModeIcon />}
          </IconButton>
        </Tooltip>
      </Toolbar>
    </AppBar>
  );
}

function RecentPlansMenu() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const { data } = useRecentPlans();
  const dispatch = usePlannerDispatch();
  return (
    <>
      <Tooltip title="Recent plans">
        <IconButton color="inherit" onClick={(e) => setAnchor(e.currentTarget)} aria-label="Recent plans">
          <HistoryIcon />
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        {!data?.length && <MenuItem disabled>No plans yet</MenuItem>}
        {data?.map((p) => (
          <MenuItem
            key={p.id}
            onClick={() => {
              dispatch({ type: 'SET_PLAN', planId: p.id });
              setAnchor(null);
            }}
          >
            <ListItemText
              primary={`${p.origin} → ${p.destination}`}
              secondary={`${formatDateTime(p.departure_time)}${p.weather_source === 'simulated' ? ' · simulated' : ''}`}
            />
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

/** Render's free tier sleeps when idle; tell the user why the first request is slow. */
function WakeNotice() {
  const { isPending, isError, refetch } = useHealth();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setSlow(true), 2500);
    return () => window.clearTimeout(id);
  }, []);
  if (isError)
    return (
      <Alert severity="error" action={<Button onClick={() => refetch()}>Retry</Button>}>
        Can’t reach the API server.
      </Alert>
    );
  if (isPending && slow) return <Alert severity="info">Waking up the server (free hosting). This takes about 30 seconds…</Alert>;
  return null;
}

function EmptyMapHint() {
  return (
    <Paper
      elevation={3}
      sx={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', p: 2.5, maxWidth: 380, textAlign: 'center' }}
    >
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        Plan a weather-safe trip
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        Enter an origin, destination, departure time and load. You’ll get three truck routes, each scored with the
        forecast at the time the truck reaches every checkpoint.
      </Typography>
    </Paper>
  );
}

import AutoAwesomeIcon from '@mui/icons-material/AutoAwesomeOutlined';
import FlagIcon from '@mui/icons-material/FlagOutlined';
import RouteIcon from '@mui/icons-material/RouteOutlined';
import SwapVertIcon from '@mui/icons-material/SwapVert';
import TripOriginIcon from '@mui/icons-material/TripOrigin';
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import dayjs, { type Dayjs } from 'dayjs';
import { useFormik } from 'formik';
import { useMemo } from 'react';
import * as Yup from 'yup';
import type { Place, PlanInput, SampleInterval, WeatherSource } from '../api/types';
import { localTzName } from '../lib/format';
import { PlaceAutocomplete } from './PlaceAutocomplete';

interface Values {
  origin: Place | null;
  destination: Place | null;
  departure: Dayjs;
  loadWeight: number | '';
  interval: SampleInterval;
  weatherSource: WeatherSource;
  includeHos: boolean;
}

// Kept in sync with backend/planner/serializers.py.
const MAX_LOAD_LBS = 120_000;
const MAX_DAYS_AHEAD = 7;

const placeSchema = Yup.object({ label: Yup.string().required(), lat: Yup.number().required(), lon: Yup.number().required() });

const schema = Yup.object({
  origin: placeSchema.nullable().required('Choose an origin'),
  destination: placeSchema
    .nullable()
    .required('Choose a destination')
    .test('different', 'Destination must differ from origin', function (value) {
      const o = this.parent.origin as Place | null;
      return !o || !value || Math.abs(o.lat - value.lat) > 1e-4 || Math.abs(o.lon - value.lon) > 1e-4;
    }),
  departure: Yup.mixed<Dayjs>()
    .required()
    .test('future', 'Departure can’t be in the past', (v) => !!v && v.isAfter(dayjs().subtract(15, 'minute')))
    .test('horizon', `Departure must be within ${MAX_DAYS_AHEAD} days`, (v) => !!v && v.isBefore(dayjs().add(MAX_DAYS_AHEAD, 'day'))),
  loadWeight: Yup.number()
    .typeError('Enter the load weight')
    .required('Enter the load weight')
    .min(0, 'Must be 0 or more')
    .max(MAX_LOAD_LBS, `Max ${MAX_LOAD_LBS.toLocaleString()} lb`),
});

const PRESETS: { label: string; origin: Place; destination: Place }[] = [
  {
    label: 'Chicago → Denver',
    origin: { label: 'Chicago, IL', lat: 41.8781, lon: -87.6298 },
    destination: { label: 'Denver, CO', lat: 39.7392, lon: -104.9903 },
  },
  {
    label: 'Dallas → Atlanta',
    origin: { label: 'Dallas, TX', lat: 32.7767, lon: -96.797 },
    destination: { label: 'Atlanta, GA', lat: 33.749, lon: -84.388 },
  },
  {
    label: 'Seattle → Salt Lake City',
    origin: { label: 'Seattle, WA', lat: 47.6062, lon: -122.3321 },
    destination: { label: 'Salt Lake City, UT', lat: 40.7608, lon: -111.891 },
  },
];

const nextQuarterHour = () => {
  const now = dayjs().add(15, 'minute');
  return now.minute(Math.ceil(now.minute() / 15) * 15).second(0).millisecond(0);
};

/** Load-rule hint shown under the weight field, so the driver sees why weight matters. */
function loadHint(lbs: number | ''): string {
  if (lbs === '' || lbs <= 30_000) return 'Loads over 30,000 lb face stricter wind rules';
  if (lbs <= 40_000) return 'Over 30,000 lb: 45–54 mph wind → No Travel';
  return 'Over 40,000 lb: 35–44 mph → Severe, 45+ mph → No Travel';
}

interface Props {
  submitting: boolean;
  onSubmit: (input: PlanInput) => void;
  initial?: PlanInput | null;
}

export function TripForm({ submitting, onSubmit, initial }: Props) {
  // Memoized: with enableReinitialize, a new object each render would reset the form.
  const initialValues = useMemo<Values>(
    () => ({
      origin: initial?.origin ?? null,
      destination: initial?.destination ?? null,
      departure: nextQuarterHour(),
      loadWeight: initial?.load_weight_lbs ?? 35_000,
      interval: initial?.sample_interval_miles ?? 25,
      weatherSource: initial?.weather_source ?? 'live',
      includeHos: initial?.include_hos ?? true,
    }),
    [initial],
  );
  const formik = useFormik<Values>({
    initialValues,
    enableReinitialize: true,
    validationSchema: schema,
    onSubmit: (v) =>
      onSubmit({
        origin: v.origin!,
        destination: v.destination!,
        departure_time: v.departure.toISOString(),
        load_weight_lbs: Number(v.loadWeight),
        sample_interval_miles: v.interval,
        weather_source: v.weatherSource,
        include_hos: v.includeHos,
      }),
  });
  const { values, errors, touched, setFieldValue, setFieldTouched } = formik;
  const err = (f: keyof Values) => (touched[f] && typeof errors[f] === 'string' ? (errors[f] as string) : undefined);

  return (
    <Box component="form" onSubmit={formik.handleSubmit} noValidate>
      <Stack spacing={1.5}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Stack spacing={1.5} sx={{ flex: 1, minWidth: 0 }}>
            <PlaceAutocomplete
              label="Origin"
              icon={<TripOriginIcon fontSize="small" sx={{ color: '#2e9e5b' }} />}
              value={values.origin}
              onChange={(p) => setFieldValue('origin', p)}
              onBlur={() => setFieldTouched('origin')}
              error={err('origin')}
            />
            <PlaceAutocomplete
              label="Destination"
              icon={<FlagIcon fontSize="small" sx={{ color: '#d93a3a' }} />}
              value={values.destination}
              onChange={(p) => setFieldValue('destination', p)}
              onBlur={() => setFieldTouched('destination')}
              error={err('destination')}
            />
          </Stack>
          <Tooltip title="Swap origin and destination">
            <IconButton
              aria-label="Swap origin and destination"
              onClick={() => formik.setValues({ ...values, origin: values.destination, destination: values.origin })}
            >
              <SwapVertIcon />
            </IconButton>
          </Tooltip>
        </Box>

        <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap', rowGap: 0.75 }}>
          {PRESETS.map((p) => (
            <Chip
              key={p.label}
              size="small"
              variant="outlined"
              label={p.label}
              onClick={() => formik.setValues({ ...values, origin: p.origin, destination: p.destination })}
            />
          ))}
        </Stack>

        <Stack spacing={1.5}>
          <DateTimePicker
            label={`Departure (${localTzName()})`}
            value={values.departure}
            onChange={(v) => v && setFieldValue('departure', v)}
            disablePast
            maxDateTime={dayjs().add(MAX_DAYS_AHEAD, 'day')}
            minutesStep={5}
            slotProps={{
              textField: {
                size: 'small',
                fullWidth: true,
                error: !!errors.departure,
                helperText: errors.departure as string | undefined,
              },
            }}
          />
          <TextField
            label="Load weight"
            size="small"
            type="number"
            fullWidth
            name="loadWeight"
            value={values.loadWeight}
            onChange={formik.handleChange}
            onBlur={formik.handleBlur}
            error={!!err('loadWeight')}
            helperText={err('loadWeight') ?? loadHint(values.loadWeight)}
            slotProps={{
              input: { endAdornment: <InputAdornment position="end">lb</InputAdornment> },
              htmlInput: { min: 0, max: MAX_LOAD_LBS, step: 1000 },
              formHelperText: { sx: { mx: 0.5 } },
            }}
          />
        </Stack>

        <Box>
          <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 0.5 }}>
            Weather checkpoint every
          </Typography>
          <ToggleButtonGroup
            exclusive
            fullWidth
            size="small"
            color="primary"
            value={values.interval}
            onChange={(_, v) => v && setFieldValue('interval', v)}
          >
            {[10, 25, 50].map((n) => (
              <ToggleButton key={n} value={n}>
                {n} mi
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Box>

        <Box>
          <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 0.5 }}>
            Weather data
          </Typography>
          <ToggleButtonGroup
            exclusive
            fullWidth
            size="small"
            color="primary"
            value={values.weatherSource}
            onChange={(_, v) => v && setFieldValue('weatherSource', v)}
          >
            <ToggleButton value="live">Live forecast</ToggleButton>
            <ToggleButton value="simulated">
              <AutoAwesomeIcon sx={{ fontSize: 16, mr: 0.75 }} />
              Simulation
            </ToggleButton>
          </ToggleButtonGroup>
          {values.weatherSource === 'simulated' && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              Places a severe storm on the fastest route at the time the truck reaches it, to show rerouting.
            </Typography>
          )}
        </Box>

        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={values.includeHos}
              onChange={(e) => setFieldValue('includeHos', e.target.checked)}
            />
          }
          label={
            <Typography variant="body2">
              Include HOS breaks{' '}
              <Typography component="span" variant="caption" color="text.secondary">
                (30 min after 8h, 10h rest after 11h driving)
              </Typography>
            </Typography>
          }
        />

        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={submitting}
          startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : <RouteIcon />}
        >
          {submitting ? 'Checking routes & forecasts…' : 'Find safest route'}
        </Button>
      </Stack>
    </Box>
  );
}

import CheckCircleIcon from '@mui/icons-material/CheckCircleOutline';
import InfoIcon from '@mui/icons-material/InfoOutlined';
import { Alert, Box, Card, CardContent, Chip, Stack, Tooltip, Typography } from '@mui/material';
import type { Plan } from '../api/types';
import { formatDateTime, formatLbs } from '../lib/format';

// Mirrors backend/planner/domain/ranking.py.
const CRITERIA = [
  'Fewest No Travel miles',
  'Fewest Severe miles',
  'Fewest High miles',
  'Lowest average risk (0–4, mile-weighted)',
  'Shortest travel time',
];

export function RecommendationCard({ plan }: { plan: Plan }) {
  const { recommendation, request } = plan;
  return (
    <Card sx={{ borderColor: 'primary.main', bgcolor: (t) => (t.palette.mode === 'dark' ? 'rgba(64,224,208,0.06)' : 'rgba(10,124,124,0.04)') }}>
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        <Stack spacing={1.25}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CheckCircleIcon color="primary" />
            <Typography variant="subtitle1" sx={{ fontWeight: 700, flex: 1 }}>
              {recommendation.headline}
            </Typography>
            <Tooltip
              title={
                <Box>
                  <Typography variant="caption" component="div" sx={{ fontWeight: 600, mb: 0.5 }}>
                    Routes are compared in this order:
                  </Typography>
                  {CRITERIA.map((c, i) => (
                    <Typography key={c} variant="caption" component="div">
                      {i + 1}. {c}
                    </Typography>
                  ))}
                </Box>
              }
            >
              <InfoIcon fontSize="small" color="action" sx={{ cursor: 'help' }} />
            </Tooltip>
          </Box>

          <Stack component="ul" spacing={0.5} sx={{ m: 0, pl: 2.5 }}>
            {recommendation.reasons.map((r) => (
              <Typography component="li" key={r} variant="body2" color="text.secondary">
                {r}
              </Typography>
            ))}
          </Stack>

          {recommendation.warnings.map((w) => (
            <Alert key={w} severity={w.includes('No Travel') ? 'error' : 'warning'} sx={{ py: 0 }}>
              {w}
            </Alert>
          ))}

          <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap', rowGap: 0.75 }}>
            <Chip size="small" variant="outlined" label={`Departs ${formatDateTime(request.departure_time)}`} />
            <Chip size="small" variant="outlined" label={formatLbs(request.load_weight_lbs)} />
            <Chip size="small" variant="outlined" label={`Every ${request.sample_interval_miles} mi`} />
            {request.weather_source === 'simulated' && <Chip size="small" color="warning" label="Simulated storm" />}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

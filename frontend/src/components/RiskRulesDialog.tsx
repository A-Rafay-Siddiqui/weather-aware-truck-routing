import {
  Alert,
  Dialog,
  DialogContent,
  DialogTitle,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useRiskRules } from '../api/queries';
import type { RiskKey, Threshold } from '../api/types';
import { RISK_ORDER } from '../lib/risk';
import { RiskChip } from './RiskVisuals';

/** Range text for one level, derived from the backend's thresholds (single source of truth). */
function rangeText(thresholds: Threshold[], level: RiskKey, unit: string): string {
  const asc = [...thresholds].reverse(); // moderate → no_travel
  const idx = RISK_ORDER.indexOf(level);
  const lower = idx === 0 ? null : asc[idx - 1];
  const upper = asc[idx] ?? null;
  const fmt = (n: number) => (unit === 'mph' ? n.toFixed(0) : n.toFixed(2).replace(/0$/, ''));
  if (!lower) return `< ${fmt(upper!.min)} ${unit}`;
  if (!upper) return `${lower.inclusive ? '≥' : '>'} ${fmt(lower.min)} ${unit}`;
  return `${lower.inclusive ? '≥' : '>'} ${fmt(lower.min)} and ${upper.inclusive ? '<' : '≤'} ${fmt(upper.min)}`;
}

export function RiskRulesDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: rules, isLoading } = useRiskRules();
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>How risk is scored</DialogTitle>
      <DialogContent>
        {isLoading || !rules ? (
          <Skeleton variant="rounded" height={200} />
        ) : (
          <Stack spacing={2.5}>
            <Typography variant="body2" color="text.secondary">
              Each checkpoint is scored with the forecast at the truck’s ETA there. Its level is the worst of wind (after
              load rules), rain and snow. The checkpoint’s level then applies to the miles halfway to its neighbours.
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Condition</TableCell>
                  {RISK_ORDER.map((k) => (
                    <TableCell key={k}>
                      <RiskChip level={k} />
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {(
                  [
                    ['Wind', rules.wind_mph, 'mph'],
                    ['Rain', rules.rain_in_hr, 'in/hr'],
                    ['Snow', rules.snow_in_hr, 'in/hr'],
                  ] as const
                ).map(([name, t, unit]) => (
                  <TableRow key={name}>
                    <TableCell sx={{ fontWeight: 600 }}>{name}</TableCell>
                    {RISK_ORDER.map((k) => (
                      <TableCell key={k} sx={{ whiteSpace: 'nowrap' }}>
                        {rangeText(t as Threshold[], k, unit)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Alert severity="info" variant="outlined">
              Where the spec’s ranges share an endpoint (e.g. rain 0.25), the value goes to the more severe level. Explicit
              operators are followed literally: wind ≥ 55 mph is No Travel, and rain is No Travel only above 1.00 in/hr.
            </Alert>
            <Stack spacing={0.5}>
              <Typography variant="subtitle2">Load rules</Typography>
              <Typography variant="body2">• Wind ≥ 55 mph → No Travel for any load</Typography>
              {rules.load_rules.map((r) => (
                <Typography key={r.description} variant="body2">
                  • {r.description}
                </Typography>
              ))}
            </Stack>
            <Stack spacing={0.5}>
              <Typography variant="subtitle2">Best route</Typography>
              <Typography variant="body2">
                Routes are ranked by fewest No Travel miles, then Severe miles, then High miles, then lowest mile-weighted
                average risk (Low 0 … No Travel 4; routes within 0.1 of the lowest average count as tied), then shortest travel time. No Travel ranks before
                Severe because it is the stricter condition.
              </Typography>
            </Stack>
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  );
}

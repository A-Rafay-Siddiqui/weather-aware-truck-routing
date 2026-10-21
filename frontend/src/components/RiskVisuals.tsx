import { Box, Chip, Tooltip, Typography, type ChipProps } from '@mui/material';
import { memo } from 'react';
import type { Checkpoint, RiskKey } from '../api/types';
import { formatEta, formatMiles } from '../lib/format';
import { RISK_COLOR, RISK_CONTRAST, RISK_LABEL } from '../lib/risk';

export function RiskChip({ level, size = 'small', ...rest }: { level: RiskKey } & Omit<ChipProps, 'color'>) {
  return (
    <Chip
      size={size}
      label={RISK_LABEL[level]}
      sx={{ bgcolor: RISK_COLOR[level], color: RISK_CONTRAST[level], height: size === 'small' ? 22 : undefined }}
      {...rest}
    />
  );
}

export const RiskDot = ({ level, size = 10 }: { level: RiskKey; size?: number }) => (
  <Box
    component="span"
    sx={{ display: 'inline-block', width: size, height: size, borderRadius: '50%', bgcolor: RISK_COLOR[level], flexShrink: 0 }}
  />
);

/**
 * The route as a horizontal bar: each checkpoint's stretch of road, colored by its risk.
 * Widths are proportional to miles, so "how much of the trip is risky" reads at a glance.
 */
export const RiskStrip = memo(function RiskStrip({
  checkpoints,
  totalMiles,
  height = 10,
  departure,
}: {
  checkpoints: Checkpoint[];
  totalMiles: number;
  height?: number;
  departure?: string;
}) {
  return (
    <Box
      role="img"
      aria-label="Risk along the route"
      sx={{ display: 'flex', height, borderRadius: height / 2, overflow: 'hidden', bgcolor: 'action.hover' }}
    >
      {checkpoints.map((c) => {
        const miles = c.segment[1] - c.segment[0];
        if (miles <= 0) return null;
        return (
          <Tooltip
            key={c.index}
            disableInteractive
            title={
              <Typography variant="caption">
                Mile {c.mile.toFixed(0)} · {formatEta(c.eta, departure)} · {RISK_LABEL[c.risk.level]}
              </Typography>
            }
          >
            <Box sx={{ width: `${(miles / totalMiles) * 100}%`, bgcolor: RISK_COLOR[c.risk.level] }} />
          </Tooltip>
        );
      })}
    </Box>
  );
});

export function MilesAtRisk({ miles }: { miles: Record<RiskKey, number> }) {
  const shown = (['no_travel', 'severe', 'high', 'moderate'] as RiskKey[]).filter((k) => miles[k] >= 0.5);
  if (!shown.length) {
    return (
      <Typography variant="caption" color="text.secondary">
        Low risk the whole way
      </Typography>
    );
  }
  return (
    <Box sx={{ display: 'flex', gap: 1.25, flexWrap: 'wrap' }}>
      {shown.map((k) => (
        <Box key={k} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <RiskDot level={k} size={8} />
          <Typography variant="caption" sx={{ fontWeight: k === 'severe' || k === 'no_travel' ? 700 : 500 }}>
            {formatMiles(miles[k])} {RISK_LABEL[k]}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

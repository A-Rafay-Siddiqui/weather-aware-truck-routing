import { createTheme, type PaletteMode } from '@mui/material/styles';
import type {} from '@mui/x-data-grid/themeAugmentation';

// Spotter palette: deep navy + teal/turquoise accents.
const NAVY = '#043344';
const TEAL = '#0a7c7c';
const TURQUOISE = '#40e0d0';

export function buildTheme(mode: PaletteMode) {
  const dark = mode === 'dark';
  return createTheme({
    palette: {
      mode,
      primary: dark ? { main: TURQUOISE, contrastText: '#062a33' } : { main: TEAL },
      secondary: { main: NAVY },
      background: dark ? { default: '#0d1116', paper: '#141b22' } : { default: '#f3f6f8', paper: '#ffffff' },
      divider: dark ? 'rgba(255,255,255,0.09)' : 'rgba(4,51,68,0.12)',
    },
    shape: { borderRadius: 8 },
    typography: {
      fontFamily: 'Roboto, system-ui, -apple-system, "Segoe UI", sans-serif',
      h6: { fontWeight: 600, letterSpacing: 0.1 },
      subtitle2: { fontWeight: 600 },
      overline: { fontWeight: 600, letterSpacing: 0.8, lineHeight: 1.6 },
      button: { textTransform: 'none', fontWeight: 600 },
    },
    components: {
      MuiAppBar: {
        styleOverrides: { root: { backgroundColor: dark ? '#0a141b' : NAVY, backgroundImage: 'none' } },
      },
      MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
      MuiCard: {
        defaultProps: { variant: 'outlined' },
        styleOverrides: { root: { borderRadius: 8 } },
      },
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiToggleButton: { styleOverrides: { root: { paddingTop: 5, paddingBottom: 5 } } },
      MuiTooltip: { defaultProps: { arrow: true } },
      MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
      MuiDataGrid: {
        styleOverrides: {
          root: { border: 0, '--DataGrid-containerBackground': 'transparent' },
          columnHeaderTitle: { fontWeight: 600 },
        },
      },
    },
  });
}

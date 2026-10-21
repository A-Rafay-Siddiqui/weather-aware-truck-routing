import PlaceIcon from '@mui/icons-material/PlaceOutlined';
import { Autocomplete, Box, CircularProgress, TextField, Typography } from '@mui/material';
import { useState, type ReactNode } from 'react';
import { usePlaceSearch } from '../api/queries';
import type { Place } from '../api/types';
import { useDebounced } from '../hooks/useDebounced';

interface Props {
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
  onBlur?: () => void;
  error?: string;
  icon?: ReactNode;
}

export function PlaceAutocomplete({ label, value, onChange, onBlur, error, icon }: Props) {
  const [input, setInput] = useState('');
  const query = useDebounced(input, 250);
  const { data, isFetching, isError } = usePlaceSearch(query);
  // The server geocoder already ranks results, so skip MUI's client-side filtering.
  const options = data ?? [];

  return (
    <Autocomplete
      value={value}
      options={value && !options.some((o) => same(o, value)) ? [value, ...options] : options}
      filterOptions={(x) => x}
      getOptionLabel={(o) => o.label}
      isOptionEqualToValue={same}
      onChange={(_, place) => onChange(place)}
      onInputChange={(_, text, reason) => reason === 'input' && setInput(text)}
      onBlur={onBlur}
      autoHighlight
      noOptionsText={
        isError ? 'Search is unavailable right now' : query.trim().length < 2 ? 'Type a city or address' : 'No matches'
      }
      loading={isFetching}
      renderOption={({ key, ...props }, option) => (
        <Box component="li" key={key} {...props} sx={{ display: 'flex', gap: 1.25, alignItems: 'center' }}>
          <PlaceIcon fontSize="small" color="action" />
          <Typography variant="body2">{option.label}</Typography>
        </Box>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          size="small"
          error={!!error}
          helperText={error}
          slotProps={{
            input: {
              ...params.InputProps,
              startAdornment: icon ? <Box sx={{ display: 'flex', mr: 0.5, color: 'text.secondary' }}>{icon}</Box> : null,
              endAdornment: (
                <>
                  {isFetching ? <CircularProgress color="inherit" size={16} /> : null}
                  {params.InputProps.endAdornment}
                </>
              ),
            },
          }}
        />
      )}
    />
  );
}

const same = (a: Place, b: Place) => a.lat === b.lat && a.lon === b.lon && a.label === b.label;

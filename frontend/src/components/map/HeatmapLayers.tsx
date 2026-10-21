import { memo, useMemo } from 'react';
import { Layer, Source } from 'map-engine';
import type { Heatmap } from '../../api/types';
import { renderFrames, type HeatmapLayer } from '../../lib/heatmapFrames';

export const ROUTES_ANCHOR_LAYER = 'anchor-routes';
const OPACITY = 0.85;

interface Props {
  heatmap: Heatmap;
  layer: HeatmapLayer;
  frame: number;
  visible: boolean;
}

/**
 * One raster layer per forecast hour, stacked, with only the current hour opaque.
 *
 * Scrubbing therefore never uploads or decodes anything. It changes two layers' opacity,
 * and the GL engine's paint transition crossfades between hours. Frames are rebuilt only
 * when the data or the variable (risk / wind / rain / snow) changes.
 */
export const HeatmapLayers = memo(function HeatmapLayers({ heatmap, layer, frame, visible }: Props) {
  const frames = useMemo(() => renderFrames(heatmap, layer), [heatmap, layer]);
  const coordinates = useMemo<[[number, number], [number, number], [number, number], [number, number]]>(
    () => [
      [heatmap.west, heatmap.north],
      [heatmap.east, heatmap.north],
      [heatmap.east, heatmap.south],
      [heatmap.west, heatmap.south],
    ],
    [heatmap],
  );

  return (
    <>
      {frames.map((url, i) => (
        <Source key={i} id={`heatmap-${i}`} type="image" url={url} coordinates={coordinates}>
          <Layer
            id={`heatmap-layer-${i}`}
            type="raster"
            beforeId={ROUTES_ANCHOR_LAYER}
            paint={{
              'raster-opacity': visible && i === frame ? OPACITY : 0,
              'raster-opacity-transition': { duration: 280, delay: 0 },
              'raster-fade-duration': 0,
              'raster-resampling': 'linear',
            }}
          />
        </Source>
      ))}
    </>
  );
});

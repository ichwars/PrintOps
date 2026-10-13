import type { OverlayTemperatures } from '../api/client';

export const overlayFields = ['progress', 'layers', 'eta', 'filename', 'status', 'printer', 'model', 'temperatures'] as const;
export type OverlayField = typeof overlayFields[number];
export type OverlaySize = 'small' | 'medium' | 'large';
export type OverlayArtwork = 'none' | 'portrait' | 'landscape';
export interface OverlayConfig {
  size: OverlaySize;
  fps: number;
  showCamera: boolean;
  fields: OverlayField[];
  artwork: OverlayArtwork;
}
const defaultFields: OverlayField[] = ['progress', 'layers', 'eta', 'filename', 'status'];

export function parseOverlayConfig(params: URLSearchParams): OverlayConfig {
  const show = params.get('show')?.split(',') ?? defaultFields;
  const fps = Number.parseInt(params.get('fps') || '15', 10);
  const size = params.get('size');
  const artwork = params.get('artwork');
  return {
    size: size === 'small' || size === 'large' ? size : 'medium',
    fps: Math.min(30, Math.max(1, Number.isNaN(fps) ? 15 : fps)),
    showCamera: !['false', '0'].includes(params.get('camera') ?? ''),
    fields: overlayFields.filter(field => show.includes(field)),
    artwork: artwork === 'portrait' || artwork === 'landscape' ? artwork : 'none',
  };
}

export function buildOverlayUrl(origin: string, printerId: number, config: OverlayConfig, token = ''): string {
  const url = new URL(`/overlay/${printerId}`, origin);
  const fields = overlayFields.filter(field => config.fields.includes(field));
  if (fields.join(',') !== defaultFields.join(',')) url.searchParams.set('show', fields.join(','));
  if (config.size !== 'medium') url.searchParams.set('size', config.size);
  if (config.fps !== 15) url.searchParams.set('fps', String(config.fps));
  if (!config.showCamera) url.searchParams.set('camera', 'false');
  if (config.artwork !== 'none') url.searchParams.set('artwork', config.artwork);
  if (token.startsWith('bblt_')) url.searchParams.set('token', token);
  return url.toString();
}

/** Session status may contain extra MQTT values; render only valid sensor readings. */
export function overlayReadings(temperatures: OverlayTemperatures | null | undefined, chamberSensor: boolean) {
  return (['bed', 'nozzle', 'nozzle_2', 'chamber'] as const).flatMap(sensor => {
    if (sensor === 'chamber' && !chamberSensor) return [];
    const actual = temperatures?.[sensor];
    if (actual == null || !Number.isFinite(actual)) return [];
    const target = temperatures?.[`${sensor}_target`];
    const heating = (temperatures as Record<string, unknown> | null)?.[`${sensor}_heating`];
    return [{ sensor, actual: Math.round(actual), target: target != null && Number.isFinite(target) && target > actual + 1 && heating !== false ? Math.round(target) : null }];
  });
}

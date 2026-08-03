import { useQueries, useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { api } from '../api/client';
import { useTheme } from '../contexts/ThemeContext';

const FALLBACK_ACCENT = '#00ae42';

const eta = (t: number | null): number => (t != null && t > 0 ? t : Infinity);

export interface ProgressStatus {
  state: string | null;
  progress: number | null;
  remaining_time: number | null;
}

export function pickActivePrint<T extends ProgressStatus>(statuses: (T | undefined)[]): T | null {
  let best: T | null = null;
  for (const s of statuses) {
    if (!s || s.state !== 'RUNNING' || s.progress == null) continue;
    if (best === null) {
      best = s;
      continue;
    }
    const sr = eta(s.remaining_time);
    const br = eta(best.remaining_time);
    if (sr < br || (sr === br && (s.progress ?? 0) > (best.progress ?? 0))) {
      best = s;
    }
  }
  return best;
}

function drawProgressFavicon(pct: number): string | null {
  const canvas = document.createElement('canvas');
  canvas.width = 32;
  canvas.height = 32;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  const accent =
    getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() ||
    FALLBACK_ACCENT;

  const cx = 16;
  const cy = 16;
  const r = 13;
  const frac = Math.max(0, Math.min(100, pct)) / 100;
  const start = -Math.PI / 2;

  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(128,128,128,0.3)';
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(cx, cy, r, start, start + frac * Math.PI * 2);
  ctx.strokeStyle = accent;
  ctx.lineCap = 'round';
  ctx.stroke();

  return canvas.toDataURL('image/png');
}

function setFavicon(dataUrl: string | null, originals: Map<HTMLLinkElement, string>) {
  const links = document.querySelectorAll<HTMLLinkElement>('link[rel~="icon"]');
  links.forEach((link) => {
    if (dataUrl) {
      if (!originals.has(link)) originals.set(link, link.href);
      link.href = dataUrl;
    } else {
      const orig = originals.get(link);
      if (orig !== undefined) link.href = orig;
    }
  });
  if (!dataUrl) originals.clear();
}

export function usePrintProgressTitle() {
  const { progressInTitle, resolvedMode, darkAccent, lightAccent } = useTheme();
  const accent = resolvedMode === 'dark' ? darkAccent : lightAccent;

  const { data: printers } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
    enabled: progressInTitle,
  });

  const statusQueries = useQueries({
    queries: (progressInTitle ? printers ?? [] : []).map((p) => ({
      queryKey: ['printerStatus', p.id],
      queryFn: () => api.getPrinterStatus(p.id),
    })),
  });

  const originalsRef = useRef<Map<HTMLLinkElement, string>>(new Map());
  const defaultTitleRef = useRef(document.title);
  const ownsRef = useRef(false);

  const active = progressInTitle ? pickActivePrint(statusQueries.map((q) => q.data)) : null;
  const pct = active && active.progress != null ? Math.round(active.progress) : null;

  useEffect(() => {
    if (progressInTitle && pct != null) {
      document.title = `${pct}% · ${defaultTitleRef.current}`;
      setFavicon(drawProgressFavicon(pct), originalsRef.current);
      ownsRef.current = true;
    } else if (ownsRef.current) {
      document.title = defaultTitleRef.current;
      setFavicon(null, originalsRef.current);
      ownsRef.current = false;
    }
  }, [progressInTitle, pct, accent]);

  useEffect(() => {
    const originals = originalsRef.current;
    const owns = ownsRef;
    const defaultTitle = defaultTitleRef.current;
    return () => {
      if (owns.current) {
        document.title = defaultTitle;
        setFavicon(null, originals);
      }
    };
  }, []);
}

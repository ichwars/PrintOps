import { describe, expect, it } from 'vitest';

import {
  PRINTER_CONTROL_CAPABILITIES,
  isCloudControlCandidate,
  isCloudControlUncertain,
  isPrintOpsCloudControlImplemented,
} from '../../utils/printerControlCapabilities';

describe('printerControlCapabilities', () => {
  it('marks documented cloud MQTT actions as cloud candidates', () => {
    expect(isCloudControlCandidate('pause')).toBe(true);
    expect(isCloudControlCandidate('resume')).toBe(true);
    expect(isCloudControlCandidate('stop')).toBe(true);
    expect(isCloudControlCandidate('speed')).toBe(true);
  });

  it('separates cloud-capable actions from PrintOps implemented cloud controls', () => {
    expect(isPrintOpsCloudControlImplemented('pause')).toBe(true);
    expect(isPrintOpsCloudControlImplemented('speed')).toBe(true);
    expect(isPrintOpsCloudControlImplemented('temperature')).toBe(true);
    expect(isPrintOpsCloudControlImplemented('fan')).toBe(true);
    expect(isPrintOpsCloudControlImplemented('light')).toBe(true);
    expect(isCloudControlCandidate('startPrint')).toBe(true);
    expect(isPrintOpsCloudControlImplemented('startPrint')).toBe(false);
  });

  it('keeps specialized device controls uncertain until verified', () => {
    expect(isCloudControlUncertain('drying')).toBe(true);
    expect(isCloudControlCandidate('drying')).toBe(false);
    expect(isCloudControlUncertain('movement')).toBe(true);
    expect(isCloudControlUncertain('amsSlot')).toBe(true);
  });

  it('keeps every matrix entry keyed and translatable', () => {
    for (const [key, value] of Object.entries(PRINTER_CONTROL_CAPABILITIES)) {
      expect(value.action).toBe(key);
      expect(typeof value.printOpsCloudImplemented).toBe('boolean');
      expect(value.labelKey).toMatch(/^printers\./);
      expect(value.labelFallback.length).toBeGreaterThan(0);
    }
  });
});

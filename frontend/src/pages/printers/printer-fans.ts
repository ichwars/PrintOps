import type { TFunction } from 'i18next';
import type { PrinterStatus } from '../../api/client';

export function usesExhaustFanLabel(model?: string | null): boolean {
  return ['P2S', 'X2D', 'N6', 'N7'].includes((model || '').toUpperCase().replace(/[ -]/g, ''));
}

export function auxiliaryFanItems(model: string | null | undefined, status: Pick<PrinterStatus, 'big_fan1_speed' | 'left_aux_fan_speed'>, t: TFunction) {
  const leftFirst = ['X2D', 'N6'].includes((model || '').toUpperCase().replace(/[ -]/g, ''));
  const aux = {key: 'aux', label: t(leftFirst ? 'printers.fans.leftAuxiliary' : 'printers.fans.auxiliary'),
    value: status.big_fan1_speed ?? 0, activeClass: 'text-blue-600 dark:text-blue-400'};
  const aux2 = status.left_aux_fan_speed == null ? null : {key: 'aux2',
    label: t(leftFirst ? 'printers.fans.rightAuxiliary' : 'printers.fans.leftAuxiliary'),
    value: status.left_aux_fan_speed, activeClass: 'text-indigo-600 dark:text-indigo-400'};
  return (leftFirst ? [aux, aux2] : [aux2, aux]).filter((item): item is typeof aux => item !== null);
}

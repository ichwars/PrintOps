import { useTranslation } from 'react-i18next';
import i18n, { resolveSupportedLanguage } from '../../i18n';

export function smallPartsText(key: string, options: Record<string, unknown> = {}): string {
  return i18n.t(`orders.runtimeDomain.smallParts.${key}`, options);
}

export function smallPartsLocale(): string {
  return i18n.resolvedLanguage || i18n.language || 'en';
}

export function useSmallPartsText(locale?: string) {
  const { t } = useTranslation(undefined, locale ? { lng: resolveSupportedLanguage(locale) } : undefined);
  return (key: string, options: Record<string, unknown> = {}) => t(`orders.runtimeDomain.smallParts.${key}`, options);
}

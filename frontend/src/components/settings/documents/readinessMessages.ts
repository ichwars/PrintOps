import i18n, { resolveSupportedLanguage } from '../../../i18n';

export function readinessFindingText(language: string | undefined, code: string, fallbackTitle: string, fallbackCorrection: string) {
  const t = i18n.getFixedT(resolveSupportedLanguage(language || i18n.language));
  return {
    title: t(`orders.runtimeDomain.readinessTitles.${code}`, { defaultValue: fallbackTitle }),
    correction: t(`orders.runtimeDomain.readinessCorrections.${code}`, { defaultValue: fallbackCorrection }),
  };
}

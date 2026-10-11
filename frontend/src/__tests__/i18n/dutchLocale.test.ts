import { afterEach, describe, expect, it } from 'vitest';
import { createInstance } from 'i18next';
import i18n, { availableLanguages, resolveSupportedLanguage } from '../../i18n';
import en from '../../i18n/locales/en';
import nl from '../../i18n/locales/nl';
// @ts-expect-error -- .mjs script has no TypeScript declaration
import { compareLocales } from '../../../scripts/check-i18n-parity.mjs';

function leaves(value: object, prefix = ''): Map<string, string> {
  const result = new Map<string, string>();
  for (const [key, item] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof item === 'string') result.set(path, item);
    else for (const [nestedKey, text] of leaves(item, path)) result.set(nestedKey, text);
  }
  return result;
}

describe('Dutch locale', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('has every English key, placeholder and plural form without untranslated fallback', () => {
    expect(compareLocales({ en: leaves(en), nl: leaves(nl) })).toEqual({
      failed: false,
      reports: [],
    });
  });

  it('loads Dutch through the application backend and registers its native language name', async () => {
    expect(availableLanguages).toContainEqual({ code: 'nl', name: 'Dutch', nativeName: 'Nederlands' });
    expect(i18n.options.supportedLngs).toContain('nl');

    await i18n.changeLanguage('nl');

    expect(i18n.resolvedLanguage).toBe('nl');
    expect(i18n.getResource('nl', 'translation', 'orders.customers.title')).toBe('Klanten');
    expect(i18n.t('printops.nav.warehouse')).toBe('Magazijn');
    expect(i18n.t('camera.defaultView')).toBe('Standaard cameraweergave');
    expect(window.localStorage.setItem).toHaveBeenCalledWith('bambutrack_language', 'nl');
  });

  it('resolves a Dutch regional preference to the supported Dutch catalog', async () => {
    await i18n.changeLanguage('nl-NL');

    expect(i18n.resolvedLanguage).toBe('nl');
    expect(i18n.t('orders.businessProfile.title')).toBe('Bedrijfsprofiel');
  });

  it('normalizes formatting locales before loading runtime translation resources', () => {
    expect(resolveSupportedLanguage('nl-NL')).toBe('nl');
    expect(resolveSupportedLanguage('nl-BE')).toBe('nl');
    expect(resolveSupportedLanguage('de-DE')).toBe('de');
    expect(resolveSupportedLanguage('en-US')).toBe('en');
    expect(resolveSupportedLanguage('pt-br')).toBe('pt-BR');
    expect(resolveSupportedLanguage('xx-ZZ')).toBe('en');
  });

  it('renders commerce and document terminology with English fallback disabled', async () => {
    const instance = createInstance();
    await instance.init({ lng: 'nl', fallbackLng: false, resources: { nl: { translation: nl } } });

    expect(instance.t('orders.businessProfile.deleteConfirm', { name: 'Studio' }))
      .toBe('Studio verwijderen? Dit kan niet ongedaan worden gemaakt.');
    expect(instance.t('orders.customerDetails.paymentDays', { count: 30 }))
      .toBe('Betalingstermijn van 30 dagen');
    expect(instance.t('settings.documents.documentTypes.quotation')).toBe('Offerte');
    expect(instance.t('settings.documents.documentTypes.invoice')).toBe('Factuur');
    expect(instance.t('settings.documents.tax.cases.eu_reverse_charge'))
      .toBe('Btw-verlegging binnen de EU');
    expect(instance.t('settings.documentLayout.preview.page', { page: 2, pages: 5 }))
      .toBe('Pagina 2 van 5');
    expect(instance.t('suppliers.actions.save')).toBe('Leverancier opslaan');
  });

  it('selects Dutch singular and plural forms and interpolates their counts', async () => {
    const instance = createInstance();
    await instance.init({ lng: 'nl', fallbackLng: false, resources: { nl: { translation: nl } } });

    expect(instance.t('pipelineRuns.totalCount', { count: 1, n: 1 })).toBe('1 uitvoering');
    expect(instance.t('pipelineRuns.totalCount', { count: 2, n: 2 })).toBe('2 uitvoeringen');
    expect(instance.t('forecast.spoolCount', { count: 1 })).toBe('1 spoel');
    expect(instance.t('forecast.spoolCount', { count: 3 })).toBe('3 spoelen');
  });

  it('rejects copied English in commerce namespaces that allow fallbacks for older locales', () => {
    const keys = [
      'orders.customers.title',
      'settings.documents.description',
      'settings.documentLayout.description',
      'printers.localControlUnavailable',
      'orders.runtimeCalculation.noCustomerAssigned',
      'orders.runtimeDomain.warehouseGoods.location',
      'orders.runtimeDevice.business.noProfileSelected',
      'orders.runtimeBusinessProfile.tradingNameHelp',
    ];
    const reference = leaves(en);
    const copied = new Map(keys.map((key) => [key, reference.get(key)!]));
    const result = compareLocales({ en: copied, nl: copied });

    expect(result.failed).toBe(true);
    expect(result.reports).toHaveLength(1);
    expect(result.reports[0].label).toBe('nl: leaves identical to en (untranslated?)');
    expect(result.reports[0].items).toHaveLength(keys.length);
  });

  it('limits inherited runtime English to the exact older-locale paths', () => {
    const path = 'orders.runtimeCalculation.noCustomerAssigned';
    const inherited = new Map([[path, leaves(en).get(path)!]]);
    expect(compareLocales({ en: inherited, fr: inherited }).failed).toBe(false);
    expect(compareLocales({ en: inherited, de: inherited }).failed).toBe(true);
    expect(compareLocales({ en: inherited, nl: inherited }).failed).toBe(true);

    const unapproved = new Map([['orders.runtimeCalculation.futureKey', 'A future English phrase']]);
    expect(compareLocales({ en: unapproved, fr: unapproved }).failed).toBe(true);
  });

  it('rejects numeric objects that would break an ordered array despite matching leaf keys', () => {
    const reference = Object.assign(new Map([['columns.0', 'Column']]), {
      containerTypes: new Map([['columns', 'array']]),
    });
    const malformed = Object.assign(new Map([['columns.0', 'Kolom']]), {
      containerTypes: new Map([['columns', 'object']]),
    });
    expect(compareLocales({ en: reference, nl: malformed })).toEqual({
      failed: true,
      reports: [{
        label: 'nl: container type mismatch vs en',
        items: ['columns: expected array, got object'],
      }],
    });
  });

  it('allows exact Dutch cognates while still rejecting English phrases', () => {
    const catalog = new Map([
      ['printer', 'Printer'],
      ['stream', 'Stream'],
      ['status', '{{printer}} is offline'],
      ['loading', 'Loading printers...'],
    ]);
    const result = compareLocales({ en: catalog, nl: catalog });

    expect(result.failed).toBe(true);
    expect(result.reports).toEqual([{
      label: 'nl: leaves identical to en (untranslated?)',
      items: ['loading: "Loading printers..."'],
    }]);
  });

  it('does not retain the upstream application name in translated user-facing text', () => {
    const oldBrandKeys = [...leaves(nl)].filter(([, value]) => /BamBuddy/i.test(value)).map(([key]) => key);
    expect(oldBrandKeys).toEqual([]);
  });
});

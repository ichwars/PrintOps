import { useTranslation } from 'react-i18next';
import type { CommercialDocumentLine } from '../../api/documentManagement';
import { formatMoney } from '../../utils/calculationFormatting';
import { warehouseUnit } from '../warehouse/warehouseTableValues';

type Subtotal = string | number | null;
type Amounts = { subtotal: Subtotal; tax?: string; total?: string };

export function DocumentAmounts({ lines, amounts, currency, locale, positionsLabel }: {
  lines: CommercialDocumentLine[];
  amounts: Amounts;
  currency: string | null;
  locale: string;
  positionsLabel: string;
}) {
  const { t } = useTranslation();
  const validCurrency = currency && /^[a-z]{3}$/i.test(currency) ? currency : null;
  const quantity = new Intl.NumberFormat(locale, { maximumFractionDigits: 6 });
  const unitPrice = validCurrency && new Intl.NumberFormat(locale, {
    style: 'currency', currency: validCurrency, minimumFractionDigits: 2, maximumFractionDigits: 6,
  });
  const money = (amount: Subtotal) =>
    validCurrency && amount !== null && String(amount).trim() && Number.isFinite(Number(amount))
      ? formatMoney(amount, locale, validCurrency)
      : '—';
  const totals = [{ label: t('orders.runtimeCalculation.netLabel'), amount: amounts.subtotal, emphasized: amounts.total === undefined }];
  if (amounts.tax !== undefined) totals.push({ label: t('orders.runtimeCalculation.tax'), amount: amounts.tax, emphasized: false });
  if (amounts.total !== undefined) totals.push({ label: t('orders.runtimeCalculation.grossLabel'), amount: amounts.total, emphasized: true });

  return (
    <>
      <section aria-label={positionsLabel} className="space-y-2">
        <h3 className="font-semibold text-white">{positionsLabel}</h3>
        {lines.length > 0 ? (
          <ul className="divide-y divide-bambu-dark-tertiary rounded-md border border-bambu-dark-tertiary">
            {lines.map(line => (
              <li key={line.id} className="grid gap-3 px-3 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
                <div className="flex min-w-0 gap-2">
                  <span className="shrink-0 font-mono">{line.position}.</span>
                  <div className="min-w-0">
                    <p className="whitespace-pre-line wrap-break-word font-medium text-white">{line.description}</p>
                    {line.product_identifier && <p className="wrap-break-word text-xs">{line.product_identifier}</p>}
                  </div>
                </div>
                <dl className="grid grid-cols-3 gap-2 text-xs">
                  <div className="min-w-0"><dt>{t('orders.runtimeDomain.orderDetail.quantity')}</dt>
                    <dd className="wrap-break-word tabular-nums text-white">
                      {quantity.format(Number(line.quantity))} {warehouseUnit(line.unit_code, t('common.unitShortPiece'))}
                    </dd>
                  </div>
                  <div className="min-w-0 text-right"><dt>{t('orders.documentDetails.unitPriceNet')}</dt>
                    <dd className="wrap-break-word tabular-nums text-white">{unitPrice ? unitPrice.format(Number(line.unit_price)) : '—'}</dd>
                  </div>
                  <div className="min-w-0 text-right"><dt>{t('orders.documentDetails.lineTotalNet')}</dt>
                    <dd className="wrap-break-word font-medium tabular-nums text-white">{money(line.net_amount)}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        ) : <p>{t('orders.documentDetails.noPositions')}</p>}
      </section>
      <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-2 rounded-md bg-bambu-dark px-3 py-3 sm:ml-auto sm:max-w-xs">
        {totals.map(({ label, amount, emphasized }) => (
          <div key={label} className="contents">
            <dt className={emphasized ? 'font-semibold text-white' : undefined}>{label}</dt>
            <dd className={`text-right tabular-nums text-white ${emphasized ? 'font-semibold' : ''}`}>{money(amount)}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

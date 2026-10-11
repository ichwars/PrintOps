import { useTranslation } from 'react-i18next';

type WarehouseGoodsCopy = { "title": string; "subtitle": string; "search": string; "all": string; "active": string; "archived": string; "low": string; "create": string; "edit": string; "save": string; "close": string; "cancel": string; "archive": string; "restore": string; "loading": string; "empty": string; "noRead": string; "error": string; "retry": string; "previous": string; "next": string; "sku": string; "name": string; "description": string; "kind": string; "articleDetails": string; "stock": string; "prices": string; "projectLinks": string; "finished": string; "trade": string; "service": string; "unit": string; "sale": string; "cost": string; "tax": string; "minimum": string; "source": string; "own": string; "material": string; "none": string; "choose": string; "materialSearch": string; "materialLink": string; "materialNote": string; "serviceNote": string; "frozen": string; "project": string; "revision": string; "physical": string; "reserved": string; "available": string; "location": string; "destination": string; "history": string; "noHistory": string; "booking": string; "quantity": string; "reason": string; "opening": string; "receipt": string; "issue": string; "transfer": string; "correction": string; "reservation": string; "release": string; "reserved_issue": string; "counter": string; "book": string; "order": string; "reservationSelect": string; "uncertainMovement": string; "counterNote": string; "quantityNote": string; "noLocations": string; "noUnits": string; "updated": string; "actor": string; "localActor": string; "archiveNote": string; };

export function useWarehouseCopy() {
  const { t } = useTranslation();
  return t('orders.runtimeDomain.warehouseGoods', { returnObjects: true }) as unknown as WarehouseGoodsCopy;
}

export function warehouseQuantity(value: string, locale?: string) {
  const match = value.trim().match(/^([+-]?)(\d+)(?:\.(\d+))?$/);
  if (!match) return value;

  const [, sign, rawInteger, rawFraction = ''] = match;
  const integer = rawInteger.replace(/^0+(?=\d)/, '');
  const fraction = rawFraction.replace(/0+$/, '');
  const integerFormatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const digitFormatter = new Intl.NumberFormat(locale, { useGrouping: false, maximumFractionDigits: 0 });
  const localizedInteger = integerFormatter.format(BigInt(integer));
  const localizedSign = sign === '-'
    ? new Intl.NumberFormat(locale).formatToParts(-1).find((part) => part.type === 'minusSign')?.value ?? '-'
    : sign;
  if (!fraction) return `${localizedSign}${localizedInteger}`;
  const decimal = new Intl.NumberFormat(locale).formatToParts(1.1).find((part) => part.type === 'decimal')?.value ?? '.';
  const localizedFraction = [...fraction].map((digit) => digitFormatter.format(BigInt(digit))).join('');
  return `${localizedSign}${localizedInteger}${decimal}${localizedFraction}`;
}

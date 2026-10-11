import { useTranslation } from 'react-i18next';

type LexwareConnectionMessages = { "connected": string; "readonly": string; "profile": string; "actions": string; "manageKey": string; "setup": string; "setupHelp": string; "keyHelp": string; "close": string; "cancel": string; "disconnectTitle": string; "disconnectAction": string; "disconnectConfirm": string; "disconnectFailed": string; "verified": string; "secure": string; "savedRefreshFailed": string; };

export function useLexwareConnectionMessages() {
  const { t } = useTranslation();
  return t('orders.runtimeDomain.lexwareConnection', { returnObjects: true }) as unknown as LexwareConnectionMessages;
}

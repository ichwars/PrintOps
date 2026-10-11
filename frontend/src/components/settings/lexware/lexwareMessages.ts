import { useTranslation } from 'react-i18next';
import { ApiError } from '../../../api/client/core';

export type LexwareMessages = { "title": string; "readonly": string; "setupConnection": string; "previewAction": string; "recordName": string; "actions": string; "selectPage": string; "clearSelection": string; "approvalNote": string; "cancel": string; "previewHelp": string; "selectedFieldsOnly": string; "intro": string; "permission": string; "profilePermission": string; "loading": string; "retry": string; "emptyProfiles": string; "profile": string; "selectProfile": string; "key": string; "keyHelp": string; "test": string; "testing": string; "save": string; "saved": string; "organization": string; "expectedOrganization": string; "wrongOrganization": string; "connectedProfiles": string; "noConnections": string; "replaceKey": string; "pause": string; "resume": string; "disconnect": string; "sync": string; "disconnected": string; "paused": string; "queued": string; "running": string; "idle": string; "success": string; "failed": string; "unknown": string; "lastSuccess": string; "lastAttempt": string; "never": string; "stale": string; "disconnectHelp": string; "inactive": string; "changed": string; "queuedMessage": string; "disconnectedMessage": string; "contacts": string; "articles": string; "resourcePermission": string; "search": string; "filter": string; "all": string; "new": string; "linked": string; "archived": string; "noResources": string; "noMatches": string; "sourceNumber": string; "externalId": string; "updated": string; "review": string; "select": string; "selected": string; "reviewSelected": string; "batchHelp": string; "close": string; "preview": string; "original": string; "local": string; "field": string; "accept": string; "import": string; "importing": string; "link": string; "imported": string; "partial": string; "noChanges": string; "chooseFields": string; "shared": string; "preserve": string; "customer_number": string; "customerNumberConflict": string; "archivedWarning": string; "archivedImport": string; "reconnectImport": string; "target": string; "createNew": string; "targetSearch": string; "noTargets": string; "targetHelp": string; "linkedTarget": string; "previous": string; "next": string; "refreshPreview": string; "stalePreview": string; "identity": string; "addresses": string; "contactFields": string; "tax_identifiers": string; "name": string; "description": string; "sale_price": string; "tax_rate": string; "articleOptions": string; "sku": string; "kind": string; "choose": string; "finished": string; "trade": string; "service": string; "unit": string; "stockSource": string; "own": string; "material": string; "none": string; "materialTarget": string; "materialSearch": string; "sourceUnit": string; "currentUnit": string; "confirmUnit": string; "unitBasisHelp": string; "articleHelp": string; "materialHelp": string; "missingOptions": string; "requiredIdentity": string; "externalType": string; "product": string; "unsupportedType": string; "permissionImport": string; "error": string; "forbidden": string; "conflict": string; "rateLimited": string; "unavailable": string; "validation": string; "authError": string; };

export function useLexwareMessages() {
  const { t, i18n } = useTranslation();
  return { text: t('orders.runtimeDomain.lexwareSettings', { returnObjects: true }) as unknown as LexwareMessages, locale: i18n.language };
}

// Never render credential request errors verbatim: provider errors can contain secrets.
export function lexwareError(error: unknown, text: LexwareMessages, preview = false): string {
  if (!(error instanceof ApiError)) return text.error;
  if (error.code === 'customer_number_conflict') return text.customerNumberConflict;
  if (error.status === 409) return preview ? text.stalePreview : text.conflict;
  if (error.status === 403) return text.forbidden;
  if (error.status === 401) return text.authError;
  if (error.status === 429) return text.rateLimited;
  if (error.status === 422 || error.status === 400) return text.validation;
  if (error.status >= 500) return text.unavailable;
  return text.error;
}

export function formatLexwareDate(value: string | null, locale: string, empty: string) {
  if (!value) return empty;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? empty : date.toLocaleString(locale);
}

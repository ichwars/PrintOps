import type { BusinessProfileOption } from '../../../api/client';
import type { DocumentType } from '../../../api/documentManagement';

export interface DocumentContext {
  profileId: number;
  documentType: DocumentType;
  language: string;
}

export function initialDocumentContext(profiles: BusinessProfileOption[]): DocumentContext {
  const activeProfiles = profiles.filter((profile) => profile.is_active);
  const profile = activeProfiles.find((item) => item.is_default) ?? activeProfiles[0];
  return {
    profileId: profile?.id ?? 0,
    documentType: 'invoice',
    language: profile?.default_locale || 'de',
  };
}

function sortedValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortedValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, sortedValue(entry)]),
    );
  }
  return value;
}

export function stableStringify(value: unknown): string {
  return JSON.stringify(sortedValue(value));
}

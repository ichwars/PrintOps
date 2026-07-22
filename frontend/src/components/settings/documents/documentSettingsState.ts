import type { BusinessProfileOption } from '../../../api/client';
import type { DocumentConfigurationDraft, DocumentType } from '../../../api/documentManagement';

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

export function updateDocumentDraft(
  draft: DocumentConfigurationDraft,
  path: string,
  value: unknown,
): DocumentConfigurationDraft {
  const keys = path.split('.');
  const root = structuredClone(draft) as unknown as Record<string, unknown>;
  let target: Record<string, unknown> | unknown[] = root;
  for (let index = 0; index < keys.length - 1; index += 1) {
    const key = keys[index];
    const next = Array.isArray(target) ? target[Number(key)] : target[key];
    if (!next || typeof next !== 'object') throw new Error(`Unknown document policy path: ${path}`);
    target = next as Record<string, unknown> | unknown[];
  }
  const leaf = keys.at(-1)!;
  if (Array.isArray(target)) target[Number(leaf)] = value;
  else target[leaf] = value;
  return root as unknown as DocumentConfigurationDraft;
}

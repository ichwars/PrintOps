import type { LexwareArticleOptions, LexwareConnection } from '../../../api/client/lexware';

export function isLexwareSyncActive(connection: LexwareConnection) {
  return connection.connected && connection.enabled && ['queued', 'running', 'syncing'].includes(connection.sync_status);
}

export interface ArticleSetupDraft {
  sku: string;
  kind: LexwareArticleOptions['kind'] | '';
  unit_code: string;
  stock_source: LexwareArticleOptions['stock_source'] | '';
  small_part_id: number | null;
}

export const emptyArticleSetup: ArticleSetupDraft = { sku: '', kind: '', unit_code: '', stock_source: '', small_part_id: null };

export function articleSetupOptions(draft: ArticleSetupDraft): LexwareArticleOptions | undefined {
  if (!draft.sku.trim() || !draft.kind || !draft.unit_code || !draft.stock_source) return undefined;
  if (draft.kind === 'service' ? draft.stock_source !== 'none' : draft.stock_source === 'none') return undefined;
  if (draft.stock_source === 'material' && !draft.small_part_id) return undefined;
  return { ...draft, sku: draft.sku.trim(), kind: draft.kind, stock_source: draft.stock_source,
    small_part_id: draft.stock_source === 'material' ? draft.small_part_id : null };
}

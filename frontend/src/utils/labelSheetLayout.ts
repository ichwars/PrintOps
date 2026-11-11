import type { LabelSheetLayout } from '../api/client';

export const SHEET_DIMENSIONS = [
  'label_w_mm', 'label_h_mm', 'cols', 'rows', 'top_mm', 'left_mm', 'col_gap_mm', 'row_gap_mm',
] as const;
type Dimension = typeof SHEET_DIMENSIONS[number];
export type SheetDraft = Record<Dimension, string> & Pick<LabelSheetLayout, 'page'>;

export const PAPER_MM = { a4: [210, 297], letter: [215.9, 279.4] } as const;

export const DEFAULT_SHEET: LabelSheetLayout = {
  page: 'a4', label_w_mm: 63.5, label_h_mm: 38.1, cols: 3, rows: 7,
  top_mm: 15.15, left_mm: 7, col_gap_mm: 2.5, row_gap_mm: 0,
};

export function toSheetDraft(layout: LabelSheetLayout): SheetDraft {
  return { page: layout.page, ...Object.fromEntries(SHEET_DIMENSIONS.map(key => [key, String(layout[key])])) } as SheetDraft;
}

export const DEFAULT_SHEET_DRAFT = toSheetDraft(DEFAULT_SHEET);

export function isSheetDraft(value: unknown): value is SheetDraft {
  if (!value || typeof value !== 'object') return false;
  const draft = value as Partial<SheetDraft>;
  return (draft.page === 'a4' || draft.page === 'letter')
    && SHEET_DIMENSIONS.every(key => typeof draft[key] === 'string' && draft[key].length <= 30);
}

export function sheetBounds(layout: LabelSheetLayout) {
  return {
    width: layout.cols * layout.label_w_mm + (layout.cols - 1) * layout.col_gap_mm,
    height: layout.rows * layout.label_h_mm + (layout.rows - 1) * layout.row_gap_mm,
  };
}

export function parseSheetDraft(draft: SheetDraft): LabelSheetLayout | null {
  if (SHEET_DIMENSIONS.some(key => draft[key].trim() === '')) return null;
  const fields = Object.fromEntries(SHEET_DIMENSIONS.map(key => [key, Number(draft[key])])) as Record<Dimension, number>;
  const layout = { ...fields, page: draft.page };
  if (Object.values(fields).some(value => !Number.isFinite(value) || value < 0 || value > 300)) return null;
  if (layout.label_w_mm < 40 || layout.label_h_mm < 20
    || !Number.isInteger(layout.cols) || layout.cols < 1 || layout.cols > 20
    || !Number.isInteger(layout.rows) || layout.rows < 1 || layout.rows > 40) return null;
  const [width, height] = PAPER_MM[layout.page];
  const grid = sheetBounds(layout);
  if (layout.left_mm + grid.width > width + 0.01 || layout.top_mm + grid.height > height + 0.01) return null;
  return layout;
}

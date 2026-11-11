import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { LabelSheetLayout } from '../api/client';
import { labelTemplatesApi } from '../api/client/label-templates';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { PAPER_MM, SHEET_DIMENSIONS, sheetBounds, toSheetDraft, type SheetDraft } from '../utils/labelSheetLayout';
import { Button } from './Button';
import { ConfirmModal } from './ConfirmModal';
import { LegacySelect, NumberField, TextField } from './ui';

interface Props {
  draft: SheetDraft;
  onChange: (draft: SheetDraft) => void;
  layout: LabelSheetLayout | null;
  labelCount: number;
  pngDpi?: number;
  printing: boolean;
  onPrint: (layout: LabelSheetLayout, position: number) => void;
}

function SheetDiagram({ layout, position, labelCount }: {
  layout: LabelSheetLayout; position: number; labelCount: number;
}) {
  const { t } = useTranslation();
  const [width, height] = PAPER_MM[layout.page];
  const grid = sheetBounds(layout);
  const percentage = (value: number, total: number) => `${100 * value / total}%`;
  return (
    <div role="img" aria-label={t('inventory.labels.custom.diagram')}
      className="relative w-full max-w-36 overflow-hidden rounded border border-gray-400 bg-white"
      style={{ aspectRatio: width / height }}>
      <div className="absolute grid" style={{
        left: percentage(layout.left_mm, width), top: percentage(layout.top_mm, height),
        width: percentage(grid.width, width), height: percentage(grid.height, height),
        gridTemplateColumns: `repeat(${layout.cols}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${layout.rows}, minmax(0, 1fr))`,
        columnGap: percentage(layout.col_gap_mm, grid.width), rowGap: percentage(layout.row_gap_mm, grid.height),
      }}>
        {Array.from({ length: layout.cols * layout.rows }, (_, index) => (
          <span key={index} className={index >= position - 1 && index < position - 1 + labelCount
            ? 'border border-green-700 bg-green-200' : 'border border-gray-400'} />
        ))}
      </div>
    </div>
  );
}

export function LabelSheetLayoutEditor({ draft, onChange, layout, labelCount, pngDpi, printing, onPrint }: Props) {
  const { t } = useTranslation();
  const { user, hasPermission } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const queryKey = ['label-templates', user?.id ?? null];
  const templates = useQuery({
    queryKey, queryFn: labelTemplatesApi.list, enabled: hasPermission('inventory:read'),
  });
  const canEdit = hasPermission('inventory:update');
  const [selected, setSelected] = useState<number>();
  const [name, setName] = useState('');
  const [start, setStart] = useState('1');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const saved = templates.data?.find(template => template.id === selected);
  const save = useMutation({
    mutationFn: ({ name, layout: geometry, id }: { name: string; layout: LabelSheetLayout; id?: number }) =>
      labelTemplatesApi.save({ name, layout: geometry }, id),
    onSuccess: template => {
      queryClient.setQueryData<NonNullable<typeof templates.data>>(queryKey, previous => [
        ...(previous ?? []).filter(row => row.id !== template.id), template,
      ]);
      void queryClient.invalidateQueries({ queryKey });
      setSelected(template.id);
      setName(template.name);
    },
    onError: error => showToast(t('inventory.labels.custom.saveFailed', { message: error.message }), 'error'),
  });
  const remove = useMutation({
    mutationFn: (id: number) => labelTemplatesApi.remove(id),
    onSuccess: (_, id) => {
      queryClient.setQueryData<NonNullable<typeof templates.data>>(queryKey, previous =>
        previous?.filter(template => template.id !== id));
      void queryClient.invalidateQueries({ queryKey });
      setSelected(undefined);
      setName('');
      setConfirmDelete(false);
    },
    onError: error => showToast(t('inventory.labels.custom.deleteFailed', { message: error.message }), 'error'),
  });
  const capacity = layout ? layout.cols * layout.rows : 0;
  const position = Number(start);
  const validPosition = Number.isInteger(position) && position >= 1 && position <= capacity;
  const maxPngPages = pngDpi ? Math.floor(15000 / pngDpi) : 0;
  const tooManyPages = Boolean(pngDpi && validPosition && Math.ceil((labelCount + position - 1) / capacity) > maxPngPages);
  const busy = printing || save.isPending || remove.isPending;
  const templateName = name.trim();

  return (
    <section className="space-y-3 border-t border-bambu-dark-tertiary px-4 py-3">
      <label className="block text-sm text-white">
        {t('inventory.labels.custom.savedGroup')}
        <LegacySelect aria-label={t('inventory.labels.custom.savedGroup')} value={saved?.id ?? ''} disabled={busy}
          className="mt-1 w-full" onChange={event => {
            const template = templates.data?.find(row => row.id === Number(event.target.value));
            setSelected(template?.id);
            setName(template?.name ?? '');
            setStart('1');
            if (template) onChange(toSheetDraft(template.layout));
          }}>
          <option value="">{t('inventory.labels.custom.option')}</option>
          {templates.data?.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}
        </LegacySelect>
      </label>
      {templates.error && <p role="status" className="text-sm text-red-400">
        {t('inventory.labels.custom.loadFailed', { message: templates.error.message })}
      </p>}
      <div className="grid items-start gap-4 sm:grid-cols-[1fr_9rem]">
        <div className="grid grid-cols-2 gap-2">
          <label className="col-span-2 block text-sm text-white">
            {t('inventory.labels.custom.page')}
            <LegacySelect aria-label={t('inventory.labels.custom.page')} className="mt-1 w-full" value={draft.page}
              disabled={busy} onChange={event => onChange({ ...draft, page: event.target.value === 'letter' ? 'letter' : 'a4' })}>
              <option value="a4">A4 (210 × 297 mm)</option>
              <option value="letter">{t('inventory.labels.custom.pageLetter')}</option>
            </LegacySelect>
          </label>
          {SHEET_DIMENSIONS.map(key => {
            const count = key === 'cols' || key === 'rows';
            const min = count ? 1 : key === 'label_w_mm' ? 40 : key === 'label_h_mm' ? 20 : 0;
            const max = key === 'cols' ? 20 : key === 'rows' ? 40 : 300;
            return <NumberField key={key} label={t(`inventory.labels.custom.${key}`)} value={draft[key]}
              min={min} max={max} step={count ? 1 : 'any'} disabled={busy}
              onValueChange={value => onChange({ ...draft, [key]: value })} />;
          })}
        </div>
        {layout && <SheetDiagram layout={layout} position={validPosition ? position : 1} labelCount={labelCount} />}
      </div>
      {!layout && <p role="status" className="text-sm text-red-400">{t('inventory.labels.custom.invalid')}</p>}
      {layout && <NumberField label={t('inventory.labels.startPosition')} value={start} onValueChange={setStart}
        min={1} max={capacity} step={1} disabled={busy}
        helperText={t('inventory.labels.startPositionHint', { max: capacity })}
        error={validPosition ? undefined : t('inventory.labels.startPositionError', { max: capacity })} />}
      {tooManyPages && <p role="status" className="text-sm text-red-400">
        {t('inventory.labels.custom.pngLimit', { max: maxPngPages, dpi: pngDpi })}
      </p>}
      {canEdit && <div className="space-y-2">
        <TextField label={t('inventory.labels.custom.name')} maxLength={100} disabled={busy}
          value={name} onChange={event => setName(event.target.value)} />
        <div className="flex flex-wrap gap-2">
          {saved && <Button variant="secondary" disabled={busy || !layout || !templateName}
            onClick={() => layout && save.mutate({ name: templateName, layout, id: saved.id })}>
            {t('inventory.labels.custom.saveChanges')}
          </Button>}
          <Button variant="secondary" disabled={busy || !layout || !templateName}
            onClick={() => layout && save.mutate({ name: templateName, layout })}>
            {t('inventory.labels.custom.saveAsNew')}
          </Button>
          {saved && <Button variant="danger" disabled={busy} onClick={() => setConfirmDelete(true)}>
            {t('common.delete')}
          </Button>}
        </div>
      </div>}
      <Button disabled={busy || !layout || !validPosition || !labelCount || tooManyPages}
        onClick={() => layout && onPrint(layout, position)}>
        {t('inventory.labels.custom.print')}
      </Button>
      {canEdit && confirmDelete && saved && <ConfirmModal title={t('inventory.labels.custom.deleteTitle')}
        message={t('inventory.labels.custom.deleteMessage', { name: saved.name })}
        confirmText={t('common.delete')} variant="danger" overlayZIndex="z-[110]" isLoading={remove.isPending}
        onCancel={() => setConfirmDelete(false)} onConfirm={() => remove.mutate(saved.id)} />}
    </section>
  );
}

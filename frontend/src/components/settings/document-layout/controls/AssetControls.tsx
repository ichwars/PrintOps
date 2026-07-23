import { FileText, Image as ImageIcon, LoaderCircle, Trash2, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  documentLayoutsApi,
  type LayoutAsset,
  type LayoutAssetRole,
  type LayoutAssetType,
} from '../../../../api/documentLayouts';
import { Button } from '../../../ui/Button';
import { FileInput } from '../../../ui/FileInput';
import { Select } from '../../../ui/Select';

interface AssetControlsProps {
  businessProfileId: number;
  layoutId: number;
  assets: LayoutAsset[];
  readOnly: boolean;
  onChanged: () => void;
}

const roleOptions: Array<{ value: LayoutAssetRole; label: string }> = [
  { value: 'logo', label: 'Logo' },
  { value: 'letterhead_first', label: 'Letterhead - first page' },
  { value: 'letterhead_following', label: 'Letterhead - following pages' },
  { value: 'font_regular', label: 'Font - regular' },
  { value: 'font_bold', label: 'Font - bold' },
  { value: 'font_italic', label: 'Font - italic' },
  { value: 'font_bold_italic', label: 'Font - bold italic' },
];

function assetTypeForRole(role: LayoutAssetRole): LayoutAssetType {
  if (role === 'logo') return 'logo';
  if (role === 'letterhead_first') return 'letterhead_first';
  if (role === 'letterhead_following') return 'letterhead_following';
  return 'font';
}

async function sha256(file: File): Promise<string> {
  const bytes = await file.arrayBuffer();
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), (value) => value.toString(16).padStart(2, '0')).join('');
}

function AssetPreview({ asset }: { asset: LayoutAsset }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!asset.mime_type.startsWith('image/')) return undefined;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    void documentLayoutsApi.downloadAsset(asset.id, controller.signal).then(({ blob }) => {
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => undefined);
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [asset.id, asset.mime_type]);
  if (url) return <img src={url} alt="" className="h-14 w-20 rounded bg-white object-contain" />;
  return <div className="flex h-14 w-20 items-center justify-center rounded bg-bambu-dark-secondary text-bambu-gray">
    {asset.mime_type === 'application/pdf' ? <FileText className="h-6 w-6" /> : <ImageIcon className="h-6 w-6" />}
  </div>;
}

export function AssetControls({ businessProfileId, layoutId, assets, readOnly, onChanged }: AssetControlsProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [role, setRole] = useState<LayoutAssetRole>('logo');
  const [state, setState] = useState<'idle' | 'hashing' | 'uploading'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<number | null>(null);

  const uploadFile = async (file: File) => {
    setError(null);
    if (file.size > 10 * 1024 * 1024) {
      setError(t('settings.documentLayout.assets.allowed', 'Maximum file size is 10 MiB.'));
      return;
    }
    try {
      setState('hashing');
      const declaredSha256 = await sha256(file);
      setState('uploading');
      const asset = await documentLayoutsApi.uploadAsset({
        businessProfileId,
        assetType: assetTypeForRole(role),
        declaredSha256,
        file,
        fontEmbeddingRightsConfirmed: role.startsWith('font_'),
      });
      await documentLayoutsApi.attachAsset(layoutId, asset.id, role);
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setState('idle');
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const remove = async (assetId: number) => {
    setDeleteError(null);
    try {
      await documentLayoutsApi.deleteAsset(assetId);
      onChanged();
    } catch {
      setDeleteError(assetId);
    }
  };

  return <div className="space-y-3">
    <p className="text-xs text-bambu-gray">{t('settings.documentLayout.assets.allowed', 'SVG, PNG, JPEG, PDF letterhead, WOFF2 or TTF; maximum 10 MiB.')}</p>
    <div
      className="rounded-xl border border-dashed border-bambu-dark-tertiary bg-bambu-dark p-4"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const file = event.dataTransfer.files[0];
        if (file && !readOnly && state === 'idle') void uploadFile(file);
      }}
    >
      <label className="mb-2 block text-xs text-bambu-gray">{t('settings.documentLayout.assets.usedBy', 'Asset role')}</label>
      <Select
        ariaLabel={t('settings.documentLayout.assets.usedBy', 'Asset role')}
        value={role}
        options={roleOptions}
        disabled={readOnly || state !== 'idle'}
        onValueChange={(value) => setRole(value)}
      />
      <FileInput
        ref={inputRef}
        className="sr-only"
        accept=".svg,.png,.jpg,.jpeg,.pdf,.woff2,.ttf"
        disabled={readOnly || state !== 'idle'}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void uploadFile(file);
        }}
      />
      <Button className="mt-3 w-full" variant="secondary" disabled={readOnly || state !== 'idle'} onClick={() => inputRef.current?.click()}>
        {state === 'idle' ? <Upload className="h-4 w-4" /> : <LoaderCircle className="h-4 w-4 animate-spin" />}
        {state === 'hashing' ? 'SHA-256...' : state === 'uploading' ? t('settings.documentLayout.assets.uploading', 'Uploading...') : t('settings.documentLayout.assets.drop', 'Drop file here or choose')}
      </Button>
      {error ? <p role="alert" className="mt-2 text-xs text-red-400">{error}</p> : null}
    </div>
    <div className="space-y-2">
      {assets.map((asset) => <article key={asset.id} className="flex min-w-0 items-center gap-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3">
        <AssetPreview asset={asset} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">{asset.original_name}</p>
          <p className="text-xs text-bambu-gray">{Math.ceil(asset.size_bytes / 1024)} KiB - {asset.asset_type}</p>
          <p className="truncate font-mono text-[10px] text-bambu-gray" title={asset.sha256}>{asset.sha256}</p>
          <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[10px] ${asset.preflight_status === 'valid' ? 'bg-emerald-500/20 text-emerald-300' : asset.preflight_status === 'invalid' ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300'}`}>
            {t(`settings.documentLayout.assets.preflight.${asset.preflight_status}`, asset.preflight_status)}
          </span>
          {deleteError === asset.id ? <p className="mt-1 text-xs text-red-400">{t('settings.documentLayout.assets.deleteBlocked', 'This asset is still assigned and cannot be deleted.')}</p> : null}
        </div>
        {!readOnly ? <button type="button" className="flex h-11 w-11 shrink-0 items-center justify-center rounded text-bambu-gray hover:bg-red-500/10 hover:text-red-400" aria-label={t('settings.documentLayout.actions.delete', 'Delete')} onClick={() => void remove(asset.id)}><Trash2 className="h-4 w-4" /></button> : null}
      </article>)}
      {assets.length === 0 ? <p className="rounded-lg bg-bambu-dark p-3 text-sm text-bambu-gray">No assets assigned.</p> : null}
    </div>
  </div>;
}

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Wrench } from 'lucide-react';
import { Button, TextField } from '../ui';

type CameraUrlBuilderFields = { host: string; port: string; path: string; username: string; password: string };
const emptyBuilderFields: CameraUrlBuilderFields = { host: '', port: '', path: '', username: '', password: '' };

function buildCameraUrl(cameraType: string, fields: CameraUrlBuilderFields): string {
  if (!fields.host) return '';
  const scheme = cameraType === 'rtsp' ? 'rtsp' : 'http';
  const auth = fields.username ? `${encodeURIComponent(fields.username)}${fields.password ? `:${encodeURIComponent(fields.password)}` : ''}@` : '';
  const port = fields.port ? `:${fields.port}` : '';
  const path = fields.path ? (fields.path.startsWith('/') ? fields.path : `/${fields.path}`) : '';
  return `${scheme}://${auth}${fields.host}${port}${path}`;
}

/**
 * External camera URL input plus a guided builder (#102). The builder composes
 * a URL from host/port/path/auth and writes it into the same field — and
 * therefore the same save/validate path — as manual entry, so it never opens a
 * new input path around the backend's SSRF checks. USB cameras take a device
 * path rather than a URL, so the builder is hidden for them.
 */
export function ExternalCameraUrlField({ cameraType, value, onUrlChange }: { cameraType: string; value: string; onUrlChange: (url: string) => void }) {
  const { t } = useTranslation();
  const [show, setShow] = useState(false);
  const [fields, setFields] = useState<CameraUrlBuilderFields>(emptyBuilderFields);

  const handleFieldChange = (field: keyof CameraUrlBuilderFields, value: string) => {
    const nextFields = { ...fields, [field]: value };
    setFields(nextFields);
    onUrlChange(buildCameraUrl(cameraType, nextFields));
  };

  return (
    <div className="flex flex-wrap gap-2 items-start">
      <TextField
        type="text"
        placeholder={cameraType === 'usb' ? t('settings.cameraPlaceholderUsb') : t('settings.cameraPlaceholderUrl')}
        value={value}
        onChange={(e) => onUrlChange(e.target.value)}
        className="flex-1 px-3 py-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
      />
      {cameraType !== 'usb' && (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setShow((prev) => !prev)}
          title={t('settings.cameraUrlBuilderToggle')}
          aria-pressed={show}
        >
          <Wrench className="w-4 h-4" />
        </Button>
      )}
      {show && cameraType !== 'usb' && (
        <div className="w-full p-3 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <TextField
              type="text"
              placeholder={t('settings.cameraUrlBuilderHost')}
              value={fields.host}
              onChange={(e) => handleFieldChange('host', e.target.value)}
              className="col-span-2 px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
            />
            <TextField
              type="text"
              placeholder={t('settings.cameraUrlBuilderPort')}
              value={fields.port}
              onChange={(e) => handleFieldChange('port', e.target.value.replace(/\D/g, ''))}
              className="px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
            />
          </div>
          <TextField
            type="text"
            placeholder={t('settings.cameraUrlBuilderPath')}
            value={fields.path}
            onChange={(e) => handleFieldChange('path', e.target.value)}
            className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
          />
          <div className="grid grid-cols-2 gap-2">
            <TextField
              type="text"
              placeholder={t('settings.cameraUrlBuilderUsername')}
              value={fields.username}
              onChange={(e) => handleFieldChange('username', e.target.value)}
              className="px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
            />
            <TextField
              type="password"
              placeholder={t('settings.cameraUrlBuilderPassword')}
              value={fields.password}
              onChange={(e) => handleFieldChange('password', e.target.value)}
              className="px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-sm focus:border-bambu-green focus:outline-none"
            />
          </div>
          <p className="text-xs text-bambu-gray opacity-75">
            {t('settings.cameraUrlBuilderHelp')}
          </p>
        </div>
      )}
    </div>
  );
}

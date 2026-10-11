import { useTranslation } from 'react-i18next';
import type { CameraViewPreference } from '../hooks/useCameraViewPreference';
import { Select } from './ui';

interface CameraViewPreferenceSelectProps {
  preference: CameraViewPreference | null;
  onPreferenceChange: (preference: CameraViewPreference | null) => void;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
  controlClassName?: string;
}

export function CameraViewPreferenceSelect({ preference, onPreferenceChange, ariaLabel, disabled, className, controlClassName }: CameraViewPreferenceSelectProps) {
  const { t } = useTranslation();
  return (
    <Select<CameraViewPreference | 'default'>
      ariaLabel={ariaLabel ?? t('camera.defaultView')}
      value={preference ?? 'default'}
      disabled={disabled}
      onValueChange={(value) => onPreferenceChange(value === 'default' ? null : value)}
      className={className}
      controlClassName={controlClassName}
      options={[
        { value: 'default', label: t('camera.defaultStream') },
        { value: 'stream', label: t('camera.stream') },
        { value: 'snapshot', label: t('camera.snapshot') },
      ]}
    />
  );
}

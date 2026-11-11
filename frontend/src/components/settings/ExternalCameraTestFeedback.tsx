import { CheckCircle, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ExternalCameraTestResult } from '../../api/client/printers-files';
import { cameraTestMessage } from '../../utils/cameraTestMessage';

export function ExternalCameraTestFeedback({ result }: { result: ExternalCameraTestResult | null | undefined }) {
  const { t } = useTranslation();
  if (!result) return null;

  const Icon = result.success ? CheckCircle : XCircle;
  const color = result.success ? 'text-green-500' : 'text-red-500';
  return (
    <div className={`text-xs flex items-center gap-1 ${color}`}>
      <Icon className="w-3 h-3" />
      {cameraTestMessage(result, t)}
    </div>
  );
}

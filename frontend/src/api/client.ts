export {
  ApiError,
  getAuthToken,
  getStreamToken,
  request,
  setAuthToken,
  setStreamToken,
  withStreamToken,
} from './client/core';
export type { ApiValidationIssue, TokenPersistence } from './client/core';
export type * from './client/types';
export * from './client/specialized';

import { authUsersMethods } from './client/auth-users';
import { printersFilesMethods } from './client/printers-files';
import { archivesPrintLogMethods } from './client/archives-print-log';
import { settingsCloudPlugsMethods } from './client/settings-cloud-plugs';
import { queueProfilesNotificationsMethods } from './client/queue-profiles-notifications';
import { inventoryMaintenanceMethods } from './client/inventory-maintenance';
import { businessProjectsMethods } from './client/business-projects';
import { historyLibraryMethods } from './client/history-library';
import { backupsSlicerMethods } from './client/backups-slicer';

export const api = {
  ...authUsersMethods,
  ...printersFilesMethods,
  ...archivesPrintLogMethods,
  ...settingsCloudPlugsMethods,
  ...queueProfilesNotificationsMethods,
  ...inventoryMaintenanceMethods,
  ...businessProjectsMethods,
  ...historyLibraryMethods,
  ...backupsSlicerMethods,
};

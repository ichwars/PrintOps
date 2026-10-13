export {
  ApiError,
  getAuthToken,
  getStreamToken,
  getMediaToken,
  getAuthSessionId,
  subscribeAuthSession,
  getTokenExpiry,
  getTokenPersistence,
  request,
  setAuthToken,
  setStreamToken,
  setMediaToken,
  withStreamToken,
  withMediaToken,
} from './client/core';
export type { ApiValidationIssue, TokenPersistence } from './client/core';
export type * from './client/types';
export * from './client/specialized';
export { warehouseArticlesApi } from './client/warehouse-articles';
export { connectedAppsApi } from './client/connected-apps';
export type { ConnectedApp, ConnectedAppSecret, ConnectAuthorizeInfo } from './client/connected-apps';
export { lexwareApi } from './client/lexware';
export { lexwareDocumentsApi } from './client/lexware-documents';

export type { StorageHASensor, StorageHASensorCreate, StorageHASensorReading } from './client/storage-ha-sensors';
import { storageHASensorsMethods } from './client/storage-ha-sensors';
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
  ...storageHASensorsMethods,
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

import type { OrderManagementSubTab } from '../../lib/settingsNavigation';
import { BusinessProfileSettings } from './BusinessProfileSettings';
import { DocumentSettings } from './documents/DocumentSettings';
import { DocumentLayoutSettings } from './document-layout/DocumentLayoutSettings';
import { LexwareSettings } from './LexwareSettings';

/** Static order settings panels; calculation still receives the page's autosave state. */
export function OrderSettingsPanels({ tab }: { tab: OrderManagementSubTab }) {
  switch (tab) {
    case 'business-profile': return <div className="w-full"><BusinessProfileSettings /></div>;
    case 'documents': return <div className="w-full"><DocumentSettings /></div>;
    case 'format-preview': return <div id="card-document-layout-settings" className="w-full"><DocumentLayoutSettings /></div>;
    case 'lexware': return <LexwareSettings />;
    default: return null;
  }
}

import { useState } from 'react';
import { LoaderCircle, Plus } from 'lucide-react';

import type { BusinessProfileOption, CustomerListItem, ProjectCreate, ProjectListItem } from '../../../api/client';
import type { CalculationCreate } from '../../../api/calculations';
import { SUPPORTED_CURRENCIES } from '../../../utils/currency';
import { Modal, NumberField , LegacySelect, TextArea, TextField} from '../../ui';

const field = 'mt-1 h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white outline-none focus:border-bambu-green';
const numberField = 'h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white outline-none focus:border-bambu-green';
const CREATE_PROJECT_VALUE = '__create_project__';

export function RequestEditor({ draft, profiles, customers, projects, locale, onChange, onCreateProject }: { draft: CalculationCreate; profiles: BusinessProfileOption[]; customers: CustomerListItem[]; projects: ProjectListItem[]; locale: string; onChange: (draft: CalculationCreate) => void; onCreateProject?: (data: ProjectCreate) => Promise<number> }) {
  const de = locale.startsWith('de');
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [projectDescription, setProjectDescription] = useState('');
  const [projectSaving, setProjectSaving] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const set = <K extends keyof CalculationCreate>(key: K, value: CalculationCreate[K]) => onChange({ ...draft, [key]: value });
  const closeProjectModal = () => {
    if (projectSaving) return;
    setProjectModalOpen(false);
    setProjectName('');
    setProjectDescription('');
    setProjectError(null);
  };
  const createProject = async () => {
    if (!onCreateProject || !projectName.trim()) return;
    setProjectSaving(true); setProjectError(null);
    try {
      const id = await onCreateProject({ name: projectName.trim(), description: projectDescription.trim() || undefined });
      set('project_id', id);
      setProjectModalOpen(false);
      setProjectName('');
      setProjectDescription('');
      setProjectError(null);
    } catch (error) {
      setProjectError(error instanceof Error ? error.message : String(error));
    } finally { setProjectSaving(false); }
  };
  return <section><h3 className="mb-3 font-semibold text-white">1. {de ? 'Auftrag' : 'Request'}</h3><div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
    <label className="text-sm text-bambu-gray">{de ? 'Unternehmensprofil' : 'Business profile'}<LegacySelect value={draft.business_profile_id} onChange={e => set('business_profile_id', Number(e.target.value))} className={field}><option value={0}>{de ? 'Auswählen' : 'Select'}</option>{profiles.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</LegacySelect></label>
    <label className="text-sm text-bambu-gray">{de ? 'Kunde' : 'Customer'}<LegacySelect value={draft.customer_id ?? ''} onChange={e => set('customer_id', e.target.value ? Number(e.target.value) : null)} className={field}><option value="">{de ? 'Ohne Kundenzuordnung' : 'No customer'}</option>{customers.map(item => <option key={item.id} value={item.id}>{item.account_number} · {item.display_name}</option>)}</LegacySelect></label>
    <label className="text-sm text-bambu-gray">{de ? 'Projektbezug' : 'Project'}<LegacySelect value={draft.project_id ?? ''} onChange={e => { if (e.target.value === CREATE_PROJECT_VALUE) { setProjectModalOpen(true); return; } set('project_id', e.target.value ? Number(e.target.value) : null); }} className={field}><option value="">{de ? 'Kein Projekt' : 'No project'}</option>{onCreateProject ? <option value={CREATE_PROJECT_VALUE}>{de ? '+ Projekt anlegen ...' : '+ Create project ...'}</option> : null}{projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</LegacySelect></label>
    <label className="text-sm text-bambu-gray">{de ? 'Druckart' : 'Request kind'}<LegacySelect value={draft.request_kind} onChange={e => set('request_kind', e.target.value as CalculationCreate['request_kind'])} className={field}><option value="single">{de ? 'Einzeldruck' : 'Single print'}</option><option value="series">{de ? 'Serie' : 'Series'}</option><option value="prototype">{de ? 'Prototyp' : 'Prototype'}</option><option value="service">{de ? 'Dienstleistung' : 'Service'}</option></LegacySelect></label>
    <label className="text-sm text-bambu-gray">{de ? 'Gesamtstückzahl' : 'Total quantity'}<NumberField min="1" step="1" value={draft.quantity} onChange={e => set('quantity', Math.max(1, Number(e.target.value)))} containerClassName="mt-1" className={numberField} /></label>
    <label className="text-sm text-bambu-gray lg:col-span-2">{de ? 'Positionstitel' : 'Line title'}<TextField value={draft.title} onChange={e => set('title', e.target.value)} className={field} /></label>
    <label className="text-sm text-bambu-gray">{de ? 'Währung' : 'Currency'}<LegacySelect value={draft.currency} onChange={e => set('currency', e.target.value)} className={field}>{SUPPORTED_CURRENCIES.map(item => <option key={item.code} value={item.code}>{item.label}</option>)}</LegacySelect></label>
    <label className="text-sm text-bambu-gray md:col-span-2">{de ? 'Positionsbeschreibung' : 'Description'}<TextArea rows={3} value={draft.position_description ?? ''} onChange={e => set('position_description', e.target.value || null)} className="mt-1 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-white" /></label>
    <label className="text-sm text-bambu-gray md:col-span-2">{de ? 'Notizen / gesonderte Absprachen' : 'Notes / special terms'}<TextArea rows={3} value={draft.special_terms ?? ''} onChange={e => set('special_terms', e.target.value || null)} className="mt-1 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-white" /></label>
  </div><Modal open={projectModalOpen} onClose={closeProjectModal} closeDisabled={projectSaving} title={de ? 'Projekt anlegen' : 'Create project'} description={de ? 'Das Projekt wird angelegt und direkt dieser Kalkulation zugeordnet.' : 'The project is created and assigned to this calculation.'}>
    <div className="space-y-4">
      {projectError ? <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">{projectError}</div> : null}
      <label className="block text-sm text-bambu-gray">{de ? 'Projektname' : 'Project name'}<TextField autoFocus value={projectName} onChange={(event) => setProjectName(event.target.value)} className={field} /></label>
      <label className="block text-sm text-bambu-gray">{de ? 'Beschreibung' : 'Description'}<TextArea rows={3} value={projectDescription} onChange={(event) => setProjectDescription(event.target.value)} className="mt-1 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-white" /></label>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={closeProjectModal} disabled={projectSaving} className="h-10 rounded-lg bg-bambu-dark px-4 text-white disabled:opacity-50">{de ? 'Abbrechen' : 'Cancel'}</button>
        <button type="button" onClick={() => void createProject()} disabled={projectSaving || !projectName.trim()} className="inline-flex h-10 items-center gap-2 rounded-lg bg-bambu-green px-4 font-medium text-black disabled:opacity-50">{projectSaving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}{de ? 'Anlegen' : 'Create'}</button>
      </div>
    </div>
  </Modal></section>;
}

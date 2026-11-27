import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import { Button, Checkbox, Modal, TextField } from './ui';
import { LdapUserPicker } from './LdapUserPicker';
import type { Group, Printer, UserCreate, UserResponse } from '../api/client';

interface AdvancedAuthFormData extends UserCreate {
  group_ids: number[];
  allowed_printer_ids?: number[];
  confirmPassword: string;
  email?: string;
}

interface CreateUserAdvancedAuthModalProps {
  formData: AdvancedAuthFormData;
  setFormData: (data: AdvancedAuthFormData) => void;
  groups: Group[];
  printers?: Printer[];
  onClose: () => void;
  onCreate: () => void;
  isCreating: boolean;
  isCreateButtonDisabled: boolean;
  // When LDAP is enabled in settings, the modal shows a "LDAP" tab beside
  // "Local"; the picker handles its own provision call and reports success
  // back through onLdapProvisioned.
  ldapEnabled?: boolean;
  onLdapProvisioned?: (user: UserResponse) => void;
}

type Tab = 'local' | 'ldap';

export function CreateUserAdvancedAuthModal({
  formData,
  setFormData,
  groups,
  printers = [],
  onClose,
  onCreate,
  isCreating,
  isCreateButtonDisabled,
  ldapEnabled = false,
  onLdapProvisioned,
}: CreateUserAdvancedAuthModalProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('local');

  const toggleGroup = (groupId: number) => {
    setFormData({
      ...formData,
      group_ids: formData.group_ids.includes(groupId)
        ? formData.group_ids.filter(id => id !== groupId)
        : [...formData.group_ids, groupId],
    });
  };

  const togglePrinter = (printerId: number) => {
    const current = formData.allowed_printer_ids ?? [];
    setFormData({
      ...formData,
      allowed_printer_ids: current.includes(printerId)
        ? current.filter(id => id !== printerId)
        : [...current, printerId],
    });
  };

  return (
    <Modal open onClose={onClose} closeLabel={t('common.close')}
      title={t('users.modal.createUser')} description={t('users.modal.advancedAuthSubtitle')}
      className="max-w-md"
      footer={<>
        <Button variant="secondary" onClick={onClose}>{t('users.modal.cancel')}</Button>
        {tab === 'local' && (
          <Button onClick={onCreate} disabled={isCreateButtonDisabled} loading={isCreating}>
            {!isCreating && <Plus className="w-4 h-4" />}
            {t(isCreating ? 'users.modal.creating' : 'users.modal.createUser')}
          </Button>
        )}
      </>}
    >
          {ldapEnabled && (
            <div
              className="mb-4 flex items-center gap-1 p-1 bg-bambu-dark-secondary rounded-lg"
              role="tablist"
              aria-label={t('users.modal.tabsAriaLabel')}
            >
              <Button variant="unstyled"
                type="button"
                role="tab"
                aria-selected={tab === 'local'}
                onClick={() => setTab('local')}
                className={`flex-1 px-3 py-2 text-sm rounded-md transition-colors ${
                  tab === 'local'
                    ? 'bg-bambu-green/15 text-bambu-green'
                    : 'text-bambu-gray hover:text-white'
                }`}
              >
                {t('users.modal.localTab')}
              </Button>
              <Button variant="unstyled"
                type="button"
                role="tab"
                aria-selected={tab === 'ldap'}
                onClick={() => setTab('ldap')}
                className={`flex-1 px-3 py-2 text-sm rounded-md transition-colors ${
                  tab === 'ldap'
                    ? 'bg-bambu-green/15 text-bambu-green'
                    : 'text-bambu-gray hover:text-white'
                }`}
              >
                {t('users.modal.ldapTab')}
              </Button>
            </div>
          )}

          {tab === 'ldap' && ldapEnabled ? (
            <LdapUserPicker
              onSuccess={(user) => {
                onLdapProvisioned?.(user);
              }}
            />
          ) : (
          <div className="space-y-4">
            {/* Username Field */}
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                {t('users.form.username')} <span className="text-red-600 dark:text-red-400">*</span>
              </label>
              <TextField
                type="text"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                className="w-full px-4 py-3 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:outline-none focus:ring-2 focus:ring-bambu-green/50 focus:border-bambu-green transition-colors"
                placeholder={t('users.form.usernamePlaceholder')}
                autoComplete="username"
                required
              />
            </div>

            {/* Email Field */}
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                {t('users.form.email') || 'Email'} <span className="text-red-600 dark:text-red-400">*</span>
              </label>
              <TextField
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="w-full px-4 py-3 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:outline-none focus:ring-2 focus:ring-bambu-green/50 focus:border-bambu-green transition-colors"
                placeholder={t('users.form.emailPlaceholder') || 'user@example.com'}
                required
              />
            </div>

            {/* Info box about auto-generated password */}
            <div className="bg-bambu-dark-secondary/50 border border-bambu-green/20 rounded-lg p-3">
              <p className="text-sm text-bambu-gray">
                {t('users.form.autoGeneratedPassword') || 'A secure password will be automatically generated and emailed to the user.'}
              </p>
            </div>

            {/* Groups Field */}
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                {t('users.form.groups')}
              </label>
              <div className="space-y-2 max-h-40 overflow-y-auto p-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg">
                {groups.map(group => (
                  <label
                    key={group.id}
                    className="flex items-center gap-3 px-2 py-1.5 rounded hover:bg-bambu-dark-tertiary cursor-pointer"
                  >
                    <Checkbox
                      checked={formData.group_ids.includes(group.id)}
                      onChange={() => toggleGroup(group.id)}
                      className="w-4 h-4 rounded border-bambu-gray text-bambu-green focus:ring-bambu-green focus:ring-offset-0 bg-bambu-dark"
                    />
                    <span className="text-sm text-white">{group.name}</span>
                    {group.is_system && (
                      <span className="text-xs text-yellow-700 dark:text-yellow-400">({t('users.system')})</span>
                    )}
                  </label>
                ))}
                {groups.length === 0 && (
                  <p className="text-sm text-bambu-gray">{t('users.noGroupsAvailable')}</p>
                )}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-white mb-2">
                {t('users.form.printerScope', 'Printer access')}
              </label>
              <div className="space-y-2 max-h-40 overflow-y-auto p-2 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg">
                <label className="flex items-center gap-3 px-2 py-1.5 rounded hover:bg-bambu-dark-tertiary cursor-pointer">
                  <Checkbox
                    checked={formData.allowed_printer_ids == null}
                    onChange={() => setFormData({ ...formData, allowed_printer_ids: undefined })}
                    className="w-4 h-4 rounded border-bambu-gray text-bambu-green focus:ring-bambu-green focus:ring-offset-0 bg-bambu-dark"
                  />
                  <span className="text-sm text-white">{t('users.form.allPrinters', 'All printers')}</span>
                </label>
                {printers.map(printer => (
                  <label
                    key={printer.id}
                    className="flex items-center gap-3 px-2 py-1.5 rounded hover:bg-bambu-dark-tertiary cursor-pointer"
                  >
                    <Checkbox
                      checked={formData.allowed_printer_ids?.includes(printer.id) ?? false}
                      onChange={() => togglePrinter(printer.id)}
                      className="w-4 h-4 rounded border-bambu-gray text-bambu-green focus:ring-bambu-green focus:ring-offset-0 bg-bambu-dark"
                    />
                    <span className="text-sm text-white">{printer.name}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          )}
    </Modal>
  );
}

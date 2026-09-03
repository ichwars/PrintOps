import { useTranslation } from 'react-i18next';

const en = {
  connected: 'Connected', readonly: 'Read only', profile: 'Profile',
  actions: 'Connection actions', manageKey: 'Manage key', setup: 'Connect Lexware Office',
  setupHelp: 'Select a business profile and test your API key before saving the connection.',
  keyHelp: 'Test a new API key for this organization before replacing the saved key.',
  close: 'Close connection setup', cancel: 'Cancel',
  verified: 'Organization verified', secure: 'Your API key stays private',
  savedRefreshFailed: 'The connection was saved, but the view could not be refreshed. Close this dialog and reload the page.',
};

const de: typeof en = {
  connected: 'Verbunden', readonly: 'Nur lesend', profile: 'Profil',
  actions: 'Verbindungsaktionen', manageKey: 'Schlüssel verwalten', setup: 'Lexware Office verbinden',
  setupHelp: 'Wähle ein Unternehmensprofil und teste deinen API-Schlüssel, bevor du die Verbindung speicherst.',
  keyHelp: 'Teste einen neuen API-Schlüssel für diese Organisation, bevor du den gespeicherten Schlüssel ersetzt.',
  close: 'Verbindungseinrichtung schließen', cancel: 'Abbrechen',
  verified: 'Organisation geprüft', secure: 'Dein API-Schlüssel bleibt geschützt',
  savedRefreshFailed: 'Die Verbindung wurde gespeichert, die Ansicht konnte aber nicht aktualisiert werden. Schließe diesen Dialog und lade die Seite neu.',
};

export function useLexwareConnectionMessages() {
  const { i18n } = useTranslation();
  return i18n.language.startsWith('de') ? de : en;
}

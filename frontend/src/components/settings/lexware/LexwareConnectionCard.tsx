import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, KeyRound, MoreVertical, Pause, Play, RefreshCw, Unplug } from 'lucide-react';
import { lexwareApi, type LexwareConnection } from '../../../api/client/lexware';
import { useToast } from '../../../contexts/ToastContext';
import { Button, IconButton } from '../../ui';
import { LexwareConnectionDialog } from './LexwareConnectionDialog';
import { formatLexwareDate, lexwareError, useLexwareMessages } from './lexwareMessages';
import { useLexwareConnectionMessages } from './lexwareConnectionMessages';
import { isLexwareSyncActive } from './lexwareState';

export function LexwareConnectionCard({ connection, profileName }: { connection: LexwareConnection; profileName: string }) {
  const { text, locale } = useLexwareMessages();
  const copy = useLexwareConnectionMessages();
  const { showToast } = useToast();
  const client = useQueryClient();
  const [replaceKey, setReplaceKey] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);
  const focusLastItem = useRef(false);

  useEffect(() => {
    if (!menuOpen) return;
    const items = menuRef.current?.querySelectorAll<HTMLButtonElement>('button[role="menuitem"]:not(:disabled)');
    if (items?.length) items[focusLastItem.current ? items.length - 1 : 0].focus();
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !actionsRef.current?.contains(event.target)) setMenuOpen(false);
    };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [menuOpen]);

  const closeMenu = () => {
    setMenuOpen(false);
    // Focus the persistent trigger before opening a Modal; menu items will unmount.
    triggerRef.current?.focus();
  };
  const handleMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' || event.key === 'Tab') {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); }
      closeMenu();
      return;
    }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('button[role="menuitem"]:not(:disabled)') ?? []);
    if (!items.length) return;
    const current = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
      : (current + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
    items[next].focus();
  };
  const refresh = () => client.invalidateQueries({ queryKey: ['lexware'] });
  const action = useMutation({
    mutationFn: async (operation: 'toggle' | 'disconnect' | 'sync') => {
      if (operation === 'sync') await lexwareApi.sync(connection.id);
      else if (operation === 'disconnect') await lexwareApi.disconnect(connection.id);
      else await lexwareApi.update(connection.id, { enabled: !connection.enabled });
      return operation;
    },
    onSuccess: async (operation) => {
      // Reflect queued/disconnected immediately, including while a refetch is still in flight.
      client.setQueryData<LexwareConnection[]>(['lexware', 'connections'], (connections) => connections?.map((item) => (
        item.id !== connection.id ? item : operation === 'sync' ? { ...item, sync_status: 'queued' }
          : operation === 'disconnect' ? { ...item, connected: false, enabled: false, sync_status: 'disconnected' }
            : { ...item, enabled: !connection.enabled }
      )));
      showToast(operation === 'sync' ? text.queuedMessage : operation === 'disconnect' ? text.disconnectedMessage : text.changed, 'success');
      await refresh();
    },
  });
  const status = !connection.connected ? text.disconnected : !connection.enabled ? text.paused
    : ({ queued: text.queued, running: text.running, syncing: text.running, idle: copy.connected,
      success: copy.connected, complete: copy.connected, completed: copy.connected, error: text.failed, failed: text.failed }[connection.sync_status] ?? text.unknown);
  const failed = Boolean(connection.last_error) || ['error', 'failed'].includes(connection.sync_status);
  const active = connection.connected && connection.enabled;
  const menuItemClass = 'flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white focus:bg-bambu-dark-tertiary focus:text-white focus:outline-none disabled:cursor-not-allowed disabled:opacity-50';

  return (
    <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark text-white" aria-label={`${profileName}: ${connection.company_name}`}>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-4 rounded-xl bg-bambu-green/5 px-5 py-5">
        <div className="flex shrink-0 items-center gap-3 sm:gap-4">
          <span className="text-xl font-semibold tracking-tight">Lexware</span>
          <ArrowRight className="h-5 w-5 shrink-0 text-bambu-gray" aria-hidden="true" />
          <img src="/img/printops_logo.svg" alt="PrintOps" className="h-10 w-28 object-contain" />
        </div>
        <div className="min-w-0 text-sm sm:border-l sm:border-bambu-dark-tertiary sm:pl-6">
          <p role="status" className="flex items-center gap-2 font-medium">
            <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${!active ? 'bg-bambu-gray' : failed ? 'bg-amber-400' : 'bg-bambu-green'}`} />{status}
          </p>
          <p className="mt-1 text-bambu-gray">{copy.readonly}</p>
        </div>
        <dl className="flex w-full min-w-0 flex-none flex-wrap gap-x-6 gap-y-3 text-sm sm:w-auto sm:flex-1">
          <div className="min-w-0 sm:border-l sm:border-bambu-dark-tertiary sm:pl-6">
            <dt className="text-xs text-bambu-gray">{copy.profile}</dt>
            <dd className="mt-1 max-w-56 truncate font-medium" title={`${profileName} — ${connection.company_name}`}>{profileName}</dd>
          </div>
          <div className="min-w-0 sm:border-l sm:border-bambu-dark-tertiary sm:pl-6">
            <dt className="text-xs text-bambu-gray">{text.lastSuccess}</dt>
            <dd className="mt-1 whitespace-nowrap tabular-nums">{formatLexwareDate(connection.last_success_at, locale, text.never)}</dd>
          </div>
        </dl>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="secondary" disabled={action.isPending || !active || isLexwareSyncActive(connection)}
            onClick={() => action.mutate('sync')}>
            <RefreshCw className={`h-4 w-4 ${isLexwareSyncActive(connection) ? 'animate-spin' : ''}`} aria-hidden="true" />{text.sync}
          </Button>
          <div className="relative" ref={actionsRef}
            onBlur={(event) => { if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget)) setMenuOpen(false); }}>
            <IconButton ref={triggerRef} label={copy.actions} icon={MoreVertical} disabled={action.isPending}
              aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuOpen ? menuId : undefined}
              onClick={() => { focusLastItem.current = false; setMenuOpen(!menuOpen); }}
              onKeyDown={(event) => {
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                  event.preventDefault(); focusLastItem.current = event.key === 'ArrowUp'; setMenuOpen(true);
                } else if (event.key === 'Escape' && menuOpen) { event.preventDefault(); closeMenu(); }
              }} />
            {menuOpen && <div id={menuId} ref={menuRef} role="menu" aria-label={copy.actions} onKeyDown={handleMenuKey}
              className="absolute right-0 top-full z-30 mt-2 w-72 max-w-[calc(100vw-3rem)] rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-1.5 shadow-xl">
              <button type="button" role="menuitem" tabIndex={-1} className={menuItemClass} disabled={action.isPending}
                onClick={() => { closeMenu(); setReplaceKey(true); }}><KeyRound className="h-4 w-4 shrink-0" aria-hidden="true" />{copy.manageKey}</button>
              <button type="button" role="menuitem" tabIndex={-1} className={menuItemClass} disabled={action.isPending || !connection.connected}
                onClick={() => { closeMenu(); action.mutate('toggle'); }}>
                {connection.enabled ? <Pause className="h-4 w-4 shrink-0" aria-hidden="true" /> : <Play className="h-4 w-4 shrink-0" aria-hidden="true" />}
                {connection.enabled ? text.pause : text.resume}
              </button>
              <button type="button" role="menuitem" tabIndex={-1} className={`${menuItemClass} text-red-400 hover:text-red-300 focus:text-red-300`}
                disabled={action.isPending || !connection.connected} aria-describedby={`${menuId}-disconnect-help`}
                onClick={() => { closeMenu(); action.mutate('disconnect'); }}><Unplug className="h-4 w-4 shrink-0" aria-hidden="true" />{text.disconnect}</button>
              <p id={`${menuId}-disconnect-help`} className="mt-1 border-t border-bambu-dark-tertiary px-3 pb-2 pt-3 text-xs leading-relaxed text-bambu-gray">{text.disconnectHelp}</p>
            </div>}
          </div>
        </div>
      </div>
      {(failed || !active || action.isError) && <div className="space-y-1 border-t border-bambu-dark-tertiary px-5 py-3 text-sm">
        {failed && <p role="alert" className="text-amber-300">{text.stale}</p>}
        {!active && <p className="text-bambu-gray">{text.inactive}</p>}
        {action.isError && <p role="alert" className="text-red-300">{lexwareError(action.error, text)}</p>}
      </div>}
      {replaceKey && <LexwareConnectionDialog connection={connection}
        profiles={[{ id: connection.business_profile_id, name: profileName }]}
        onClose={() => setReplaceKey(false)} onSaved={refresh} />}
    </section>
  );
}

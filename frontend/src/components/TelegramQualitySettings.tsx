import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { getTelegramQuality, saveTelegramQuality } from '../api/telegram-quality';
import type { TelegramQualityConfig } from '../api/telegram-quality';
import { Button } from './Button';
import { Checkbox } from './ui/Checkbox';
import { TextArea } from './ui/TextArea';

export function TelegramQualitySettings({ providerId }: { providerId: number }) {
  const { user, authEnabled } = useAuth();
  const { t } = useTranslation();
  const allowed = authEnabled && user?.is_admin === true;
  const query = useQuery({ queryKey: ['telegram-quality', providerId], queryFn: () => getTelegramQuality(providerId), enabled: allowed, refetchInterval: 15000 });
  if (!allowed) return <p className="text-xs text-bambu-gray">{t('telegramQuality.adminOnly')}</p>;
  if (query.isError) return <p role="alert">{t('telegramQuality.error')}</p>;
  if (!query.data) return <p>{t('common.loading')}</p>;
  return <QualityForm key={providerId} providerId={providerId} config={query.data} />;
}

function QualityForm({ providerId, config }: { providerId: number; config: TelegramQualityConfig }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [draft, setDraft] = useState<{ enabled: boolean; actors: string } | null>(null);
  const { enabled, actors } = draft ?? { enabled: config.enabled, actors: config.actors.map(a => `${a.actor_id}=${a.user_id}`).join('\n') };
  const [invalid, setInvalid] = useState(false);
  const mutation = useMutation({
    mutationFn: (data: Pick<TelegramQualityConfig, 'enabled' | 'actors'>) => saveTelegramQuality(providerId, data),
    onSuccess: (data) => { client.setQueryData(['telegram-quality', providerId], data); setDraft(null); },
  });
  function save() {
    const lines = actors.trim() ? actors.trim().split('\n') : [];
    const bindings: TelegramQualityConfig['actors'] = [];
    const seen = new Set<number>();
    for (const line of lines) {
      const match = /^([1-9][0-9]*)\s*=\s*([1-9][0-9]*)$/.exec(line.trim());
      const actor = Number(match?.[1]), user = Number(match?.[2]);
      if (!match || !Number.isSafeInteger(actor) || actor >= 2 ** 52 || !Number.isSafeInteger(user) || seen.has(actor)) {
        setInvalid(true); return;
      }
      bindings.push({ actor_id: actor, user_id: user }); seen.add(actor);
    }
    if ((enabled && !bindings.length) || bindings.length > 100) { setInvalid(true); return; }
    setInvalid(false);
    mutation.mutate({ enabled, actors: bindings });
  }
  return <section className="space-y-3 border-t border-bambu-dark-tertiary pt-3">
    <h3 className="font-medium">{t('telegramQuality.title')}</h3>
    <p className="text-xs text-bambu-gray">{t('telegramQuality.instructions')}</p>
    <Checkbox checked={enabled} onCheckedChange={value => setDraft({ enabled: value, actors })}
      disabled={mutation.isPending} label={t('telegramQuality.enable')} />
    <TextArea label={t('telegramQuality.actors')} aria-label={t('telegramQuality.actors')} rows={3}
      value={actors} onValueChange={value => setDraft({ enabled, actors: value })}
      disabled={mutation.isPending} placeholder="123456789=7" />
    <p className="text-xs text-bambu-gray">{t('telegramQuality.format')}</p>
    <p role="status" className="text-sm">{t(`telegramQuality.status.${config.status}`)}</p>
    {invalid && <p role="alert" className="text-red-400">{t('telegramQuality.format')}</p>}
    {mutation.isError && <p role="alert" className="text-red-400">{t('telegramQuality.error')}</p>}
    <Button type="button" onClick={save} disabled={mutation.isPending}>{t('telegramQuality.save')}</Button>
  </section>;
}

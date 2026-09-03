import { Plug } from 'lucide-react';
import { LexwareSettings } from '../components/settings/LexwareSettings';
import { useLexwareMessages } from '../components/settings/lexware/lexwareMessages';

/** Delegated integration access must not mount the general settings queries. */
export default function LexwareSettingsPage() {
  const { text } = useLexwareMessages();
  return <div className="min-w-0 space-y-6 p-4 md:p-8">
    <header>
      <h1 className="flex items-center gap-3 text-2xl font-bold text-white">
        <Plug aria-hidden className="h-7 w-7 shrink-0 text-bambu-green" />{text.title}
      </h1>
      <p className="mt-1 text-bambu-gray">{text.readonly}</p>
    </header>
    <LexwareSettings />
  </div>;
}

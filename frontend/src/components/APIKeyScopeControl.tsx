import { Checkbox } from './ui';

export function APIKeyScopeControl({ checked, onChange, title, description }: {
  checked: boolean; onChange: (checked: boolean) => void; title: string; description: string;
}) {
  return <label className="flex items-center gap-3 cursor-pointer">
    <Checkbox checked={checked} onChange={(event) => onChange(event.target.checked)} />
    <div><span className="text-white">{title}</span><p className="text-xs text-bambu-gray">{description}</p></div>
  </label>;
}

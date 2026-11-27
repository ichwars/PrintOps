import { Checkbox } from './ui';

export function APIKeyScopeControl({ checked, onChange, title, description }: {
  checked: boolean; onChange: (checked: boolean) => void; title: string; description: string;
}) {
  return <label className="flex min-w-0 cursor-pointer items-start gap-2">
    <Checkbox checked={checked} onChange={(event) => onChange(event.target.checked)} />
    <div><span className="text-white">{title}</span><p className="text-xs text-table-secondary">{description}</p></div>
  </label>;
}

import { useId, useRef, useState } from 'react';
import {
  Globe,
  Link,
  ExternalLink,
  Book,
  FileText,
  Home,
  Star,
  Heart,
  Bookmark,
  ShoppingCart,
  Music,
  Video,
  Image,
  Camera,
  Map,
  Compass,
  Coffee,
  Gift,
  Wrench,
  Zap,
  Cloud,
  Database,
  Folder,
  Mail,
  Phone,
  User,
  Users,
  Server,
  Terminal,
  Code,
  type LucideIcon,
} from 'lucide-react';

// Available icons for external links
export const AVAILABLE_ICONS: { name: string; icon: LucideIcon }[] = [
  { name: 'globe', icon: Globe },
  { name: 'link', icon: Link },
  { name: 'external-link', icon: ExternalLink },
  { name: 'book', icon: Book },
  { name: 'file-text', icon: FileText },
  { name: 'home', icon: Home },
  { name: 'star', icon: Star },
  { name: 'heart', icon: Heart },
  { name: 'bookmark', icon: Bookmark },
  { name: 'shopping-cart', icon: ShoppingCart },
  { name: 'music', icon: Music },
  { name: 'video', icon: Video },
  { name: 'image', icon: Image },
  { name: 'camera', icon: Camera },
  { name: 'map', icon: Map },
  { name: 'compass', icon: Compass },
  { name: 'coffee', icon: Coffee },
  { name: 'gift', icon: Gift },
  { name: 'wrench', icon: Wrench },
  { name: 'zap', icon: Zap },
  { name: 'cloud', icon: Cloud },
  { name: 'database', icon: Database },
  { name: 'folder', icon: Folder },
  { name: 'mail', icon: Mail },
  { name: 'phone', icon: Phone },
  { name: 'user', icon: User },
  { name: 'users', icon: Users },
  { name: 'server', icon: Server },
  { name: 'terminal', icon: Terminal },
  { name: 'code', icon: Code },
];

// Helper to get icon component by name
export function getIconByName(name: string): LucideIcon {
  const found = AVAILABLE_ICONS.find((i) => i.name === name);
  return found?.icon || Link;
}

interface IconPickerProps {
  value: string;
  onChange: (value: string) => void;
}

export function IconPicker({ value, onChange }: IconPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const gridId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const SelectedIcon = getIconByName(value);

  return (
    <div
      className="space-y-2"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setIsOpen(false);
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={isOpen}
        aria-controls={gridId}
        onClick={() => setIsOpen(!isOpen)}
        className="flex min-h-[38px] w-full items-center gap-2 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-table-secondary hover:bg-bambu-dark-tertiary focus-visible:ring-2 focus-visible:ring-bambu-green max-[768px]:min-h-11"
      >
        <SelectedIcon className="h-5 w-5 shrink-0" aria-hidden="true" />
        <span className="flex-1 text-left text-sm">{value}</span>
      </button>

      {isOpen && (
        <div id={gridId} className="grid grid-cols-4 gap-1 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-2 min-[350px]:grid-cols-5">
          {AVAILABLE_ICONS.map(({ name, icon: Icon }) => (
            <button
              key={name}
              type="button"
              onClick={() => {
                onChange(name);
                setIsOpen(false);
                triggerRef.current?.focus();
              }}
              className={`flex min-h-[36px] items-center justify-center rounded-lg transition-colors focus-visible:ring-2 focus-visible:ring-bambu-green max-[768px]:min-h-11 ${
                value === name
                  ? 'bg-bambu-green/15 text-accent-foreground'
                  : 'text-table-secondary hover:bg-bambu-dark-tertiary hover:text-white'
              }`}
              title={name}
              aria-label={name}
              aria-pressed={value === name}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

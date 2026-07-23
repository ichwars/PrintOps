import { ChevronDown } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type {
  EffectiveDocumentLayout,
  LayoutDetail,
  LayoutFinding,
  LayoutPatch,
  LayoutRulePatch,
} from '../../../api/documentLayouts';
import { AssetControls } from './controls/AssetControls';
import { FooterControls } from './controls/FooterControls';
import { HeaderControls } from './controls/HeaderControls';
import { PageControls } from './controls/PageControls';
import { PositionControls } from './controls/PositionControls';
import { TextControls } from './controls/TextControls';
import { TitleControls } from './controls/TitleControls';
import { TotalsControls } from './controls/TotalsControls';
import { TypographyControls } from './controls/TypographyControls';
import type { LayoutSectionProps } from './controls/shared';

export type EditableLayoutSection = 'page' | 'typography' | 'header' | 'title' | 'positions' | 'totals' | 'technical' | 'notes' | 'footer';
export type LayoutEditorSection = EditableLayoutSection | 'assets';

export interface LayoutRuleChange {
  <S extends EditableLayoutSection, K extends keyof EffectiveDocumentLayout[S]>(
    section: S,
    key: K,
    value: EffectiveDocumentLayout[S][K],
  ): void;
}

export interface LayoutRuleReset {
  <S extends EditableLayoutSection, K extends keyof EffectiveDocumentLayout[S]>(
    section: S,
    key: K,
  ): void;
}

interface LayoutControlPanelProps {
  detail: LayoutDetail;
  patch: Omit<LayoutPatch, 'expected_lock_version' | 'edit_session_id'>;
  findings: LayoutFinding[];
  readOnly: boolean;
  focusSection?: LayoutEditorSection | null;
  onChange: LayoutRuleChange;
  onReset: LayoutRuleReset;
  onAssetsChanged: () => void;
}

function Accordion({
  section,
  title,
  open,
  onToggle,
  changed,
  findings,
  children,
}: {
  section: LayoutEditorSection;
  title: string;
  open: boolean;
  onToggle: () => void;
  changed: number;
  findings: LayoutFinding[];
  children: ReactNode;
}) {
  const blockers = findings.filter((finding) => finding.severity === 'blocker').length;
  const warnings = findings.filter((finding) => finding.severity === 'warning').length;
  return <section id={`layout-section-${section}`} className="scroll-mt-24 overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary">
    <button type="button" className="flex min-h-12 w-full items-center gap-2 px-4 py-3 text-left" aria-expanded={open} onClick={onToggle}>
      <span className="min-w-0 flex-1 font-semibold text-white">{title}</span>
      {changed ? <span className="rounded-full bg-bambu-green/20 px-2 py-0.5 text-[10px] text-bambu-green">{changed} changed</span> : <span className="rounded-full bg-bambu-dark px-2 py-0.5 text-[10px] text-bambu-gray">Inherited</span>}
      {blockers ? <span className="rounded-full bg-red-500/20 px-2 py-0.5 text-[10px] text-red-300">{blockers} blocker</span> : null}
      {warnings ? <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] text-amber-300">{warnings} warning</span> : null}
      <ChevronDown className={`h-4 w-4 shrink-0 text-bambu-gray transition ${open ? 'rotate-180' : ''}`} />
    </button>
    {open ? <div className="border-t border-bambu-dark-tertiary p-3">{children}</div> : null}
  </section>;
}

function changedCount(section: LayoutRulePatch<object> | null | undefined): number {
  return section ? Object.values(section).filter((value) => value !== undefined && value !== null).length : 0;
}

function findingsFor(section: LayoutEditorSection, findings: LayoutFinding[]): LayoutFinding[] {
  const aliases: Record<LayoutEditorSection, string[]> = {
    page: ['page'],
    typography: ['typography'],
    header: ['header'],
    title: ['title'],
    positions: ['positions'],
    totals: ['totals'],
    technical: ['technical'],
    notes: ['notes'],
    footer: ['footer'],
    assets: ['assets', 'asset'],
  };
  return findings.filter((finding) => aliases[section].some((prefix) => finding.field_path?.startsWith(prefix)));
}

export function LayoutControlPanel({
  detail,
  patch,
  findings,
  readOnly,
  focusSection,
  onChange,
  onReset,
  onAssetsChanged,
}: LayoutControlPanelProps) {
  const { t } = useTranslation();
  const [openSections, setOpenSections] = useState<Set<LayoutEditorSection>>(() => new Set(['page', 'header', 'positions', 'footer']));

  useEffect(() => {
    if (!focusSection) return;
    setOpenSections((current) => new Set(current).add(focusSection));
    window.setTimeout(() => document.getElementById(`layout-section-${focusSection}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  }, [focusSection]);

  const toggle = (section: LayoutEditorSection) => setOpenSections((current) => {
    const next = new Set(current);
    if (next.has(section)) next.delete(section);
    else next.add(section);
    return next;
  });

  const sectionProps = <S extends EditableLayoutSection>(section: S): LayoutSectionProps<EffectiveDocumentLayout[S]> => ({
    value: detail.effective[section],
    sources: detail.sourced[section].sources as unknown as LayoutSectionProps<EffectiveDocumentLayout[S]>['sources'],
    overrides: (patch[section] ?? {}) as LayoutRulePatch<EffectiveDocumentLayout[S]>,
    readOnly,
    onChange: (key, value) => onChange(section, key, value),
    onReset: (key) => onReset(section, key),
  });

  const sections = [
    { key: 'page' as const, title: t('settings.documentLayout.sections.basic', 'Basic layout'), content: <PageControls {...sectionProps('page')} /> },
    { key: 'typography' as const, title: t('settings.documentLayout.sections.typography', 'Typography and colors'), content: <TypographyControls {...sectionProps('typography')} /> },
    { key: 'header' as const, title: t('settings.documentLayout.sections.header', 'Header and table'), content: <HeaderControls {...sectionProps('header')} /> },
    { key: 'title' as const, title: t('settings.documentLayout.sections.title', 'Title and metadata'), content: <TitleControls {...sectionProps('title')} /> },
    { key: 'positions' as const, title: t('settings.documentLayout.sections.positions', 'Positions and technical data'), content: <PositionControls positions={sectionProps('positions')} technical={sectionProps('technical')} /> },
    { key: 'totals' as const, title: t('settings.documentLayout.sections.totals', 'Totals, tax and payment'), content: <TotalsControls {...sectionProps('totals')} /> },
    { key: 'notes' as const, title: t('settings.documentLayout.sections.notes', 'Document notes and text blocks'), content: <TextControls {...sectionProps('notes')} /> },
    { key: 'footer' as const, title: t('settings.documentLayout.sections.footer', 'Footer'), content: <FooterControls {...sectionProps('footer')} /> },
  ];

  return <div aria-label={t('settings.documentLayout.mobile.openControls', 'Layout controls')} className="space-y-3">
    {sections.map((section) => {
      const count = section.key === 'positions'
        ? changedCount(patch.positions as LayoutRulePatch<object>) + changedCount(patch.technical as LayoutRulePatch<object>)
        : changedCount(patch[section.key] as LayoutRulePatch<object>);
      const sectionFindings = section.key === 'positions'
        ? [...findingsFor('positions', findings), ...findingsFor('technical', findings)]
        : findingsFor(section.key, findings);
      return <Accordion key={section.key} section={section.key} title={section.title} open={openSections.has(section.key)} onToggle={() => toggle(section.key)} changed={count} findings={sectionFindings}>{section.content}</Accordion>;
    })}
    <Accordion section="assets" title={t('settings.documentLayout.sections.assets', 'Assets and fonts')} open={openSections.has('assets')} onToggle={() => toggle('assets')} changed={detail.assets.length} findings={findingsFor('assets', findings)}>
      <AssetControls businessProfileId={detail.summary.scope.business_profile_id} layoutId={detail.summary.id} assets={detail.assets} readOnly={readOnly} onChanged={onAssetsChanged} />
    </Accordion>
  </div>;
}

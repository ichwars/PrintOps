import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  LayoutControlPanel,
  type LayoutRuleChange,
  type LayoutRuleReset,
} from '../../../../components/settings/document-layout/LayoutControlPanel';
import { documentLayoutsApi } from '../../../../api/documentLayouts';
import { LayoutFindings } from '../../../../components/settings/document-layout/LayoutFindings';
import { layoutDetail } from './layoutFixtures';

describe('LayoutControlPanel', () => {
  it('renders the complete grouped editor with compact closed sections and source badges', () => {
    render(<LayoutControlPanel
      detail={layoutDetail()}
      patch={{}}
      findings={[]}
      readOnly={false}
      onChange={vi.fn() as LayoutRuleChange}
      onReset={vi.fn() as LayoutRuleReset}
      onAssetsChanged={vi.fn()}
    />);

    expect(screen.getByRole('button', { name: /Basic layout/i })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /Header and table/i })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /Positions and technical data/i })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /Footer/i })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /Typography and colors/i })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: /Totals, tax and payment/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Document notes and text blocks/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Assets and fonts/i })).toBeInTheDocument();
    expect(screen.getAllByText('System').length).toBeGreaterThan(0);
  });

  it('edits typed fields, removes overrides and exposes blocker badges', () => {
    const onChange = vi.fn() as LayoutRuleChange;
    const onReset = vi.fn() as LayoutRuleReset;
    render(<LayoutControlPanel
      detail={layoutDetail()}
      patch={{ page: { margin_top_mm: 22 } }}
      findings={[{
        code: 'margin_invalid',
        severity: 'blocker',
        field_path: 'page.margin_top_mm',
        message_key: 'layout.margin_invalid',
        message: 'Top margin is invalid',
        correction_hint: 'Use at least 5 mm',
        external_rule_id: null,
      }]}
      readOnly={false}
      onChange={onChange}
      onReset={onReset}
      onAssetsChanged={vi.fn()}
    />);

    expect(screen.getByRole('button', { name: /Basic layout.*1 changed.*1 blocker/i })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Top margin' }), { target: { value: '24' } });
    expect(onChange).toHaveBeenCalledWith('page', 'margin_top_mm', 24);

    fireEvent.click(screen.getByRole('button', { name: 'Remove override' }));
    expect(onReset).toHaveBeenCalledWith('page', 'margin_top_mm');

    fireEvent.click(screen.getByRole('button', { name: /Typography and colors/i }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Base font size' }), { target: { value: '11.5' } });
    expect(onChange).toHaveBeenCalledWith('typography', 'base_size_pt', 11.5);
  });

  it('disables every interactive rule in read-only mode', () => {
    render(<LayoutControlPanel
      detail={layoutDetail()}
      patch={{}}
      findings={[]}
      readOnly
      onChange={vi.fn() as LayoutRuleChange}
      onReset={vi.fn() as LayoutRuleReset}
      onAssetsChanged={vi.fn()}
    />);

    expect(screen.getByRole('combobox', { name: 'Template' })).toBeDisabled();
    expect(screen.getByRole('switch', { name: 'Show logo' })).toBeDisabled();
    expect(screen.getByRole('switch', { name: 'Use footer' })).toBeDisabled();
  });

  it('shows asset preflight evidence and uploads with a verified SHA-256 before assigning a role', async () => {
    const detail = layoutDetail();
    detail.assets = [{
      id: 44,
      business_profile_id: 2,
      asset_type: 'font',
      original_name: 'Corporate.woff2',
      mime_type: 'font/woff2',
      size_bytes: 2048,
      sha256: 'a'.repeat(64),
      preflight_status: 'invalid',
      preflight_report: { reason: 'embedding_forbidden' },
      created_at: '2026-07-23T08:00:00Z',
    }];
    const onChanged = vi.fn();
    const upload = vi.spyOn(documentLayoutsApi, 'uploadAsset').mockResolvedValue({ ...detail.assets[0], id: 45, preflight_status: 'valid' });
    const attach = vi.spyOn(documentLayoutsApi, 'attachAsset').mockResolvedValue({ layout_id: 17, asset_id: 45, role: 'logo' });
    vi.stubGlobal('crypto', {
      randomUUID: () => 'test-session',
      subtle: { digest: vi.fn(async () => new Uint8Array(32).buffer) },
    });

    const { container } = render(<LayoutControlPanel
      detail={detail}
      patch={{}}
      findings={[]}
      readOnly={false}
      onChange={vi.fn() as LayoutRuleChange}
      onReset={vi.fn() as LayoutRuleReset}
      onAssetsChanged={onChanged}
    />);
    fireEvent.click(screen.getByRole('button', { name: /Assets and fonts/i }));
    expect(screen.getByText('Preflight failed')).toBeInTheDocument();
    expect(screen.getByText('Corporate.woff2')).toBeInTheDocument();

    const file = new File(['logo'], 'logo.png', { type: 'image/png' });
    Object.defineProperty(file, 'arrayBuffer', { value: async () => new Uint8Array([1, 2, 3]).buffer });
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => expect(upload).toHaveBeenCalledWith(expect.objectContaining({
      businessProfileId: 2,
      assetType: 'logo',
      declaredSha256: '0'.repeat(64),
      file,
    })));
    expect(attach).toHaveBeenCalledWith(17, 45, 'logo');
    expect(onChanged).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('navigates blocker findings to their exact editor section', () => {
    const onNavigate = vi.fn();
    render(<LayoutFindings findings={[{
      code: 'font_missing',
      severity: 'blocker',
      field_path: 'typography.font_family',
      message_key: 'font_missing',
      message: 'Font is missing',
      correction_hint: 'Upload an embeddable font',
      external_rule_id: 'PDF/A-3u',
    }]} onNavigate={onNavigate} />);
    fireEvent.click(screen.getByRole('button', { name: 'Go to field' }));
    expect(onNavigate).toHaveBeenCalledWith('typography');
  });

});

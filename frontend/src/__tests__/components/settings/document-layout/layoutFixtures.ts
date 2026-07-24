import type {
  EffectiveDocumentLayout,
  LayoutDetail,
  LayoutRuleSources,
  LayoutSummary,
  SourcedDocumentLayout,
} from '../../../../api/documentLayouts';

function sourcesFor<T extends object>(value: T, configurationId: number | null = null): LayoutRuleSources<T> {
  return Object.fromEntries(Object.keys(value).map((key) => [key, {
    level: configurationId ? 'profile' : 'system',
    configuration_id: configurationId,
    version: configurationId ? 1 : null,
  }])) as LayoutRuleSources<T>;
}

export const effectiveLayout: EffectiveDocumentLayout = {
  schema_version: 1,
  template_version: '1.0.0',
  renderer_version: '1.0.0',
  validator_version: '1.0.0',
  page: {
    template_key: 'classic', page_format: 'A4', orientation: 'portrait',
    margin_top_mm: 18, margin_right_mm: 18, margin_bottom_mm: 18, margin_left_mm: 18,
    first_page_content_top_mm: 55, following_page_content_top_mm: 25,
    use_first_page_letterhead: false, use_following_page_letterhead: false, reuse_first_letterhead: false,
  },
  typography: {
    font_family: 'Noto Sans', base_size_pt: 10, table_size_pt: 9, metadata_size_pt: 8,
    heading_scale: 1.4, line_height: 1.25, paragraph_spacing_mm: 3,
    accent_color: '#5aec60', text_color: '#111111', muted_color: '#666666',
  },
  header: {
    show_logo: true, logo_width_mm: 24, logo_alignment: 'left', show_company_details: true,
    show_sender_line: true, recipient_window: 'left', recipient_top_mm: 45,
  },
  title: {
    show_title: true, show_document_number: true, show_issue_date: true, show_service_date: true,
    show_due_date: true, show_customer_number: true, metadata_alignment: 'right', title_spacing_mm: 5,
  },
  positions: {
    table_style: 'compact', show_position_number: true, show_description: true, show_quantity: true,
    show_unit: true, show_unit_price: true, show_net_amount: true, show_tax_rate: true, show_total: true,
    show_secondary_description: true, repeat_header: true,
  },
  totals: {
    show_subtotal: true, show_discount: true, show_tax_breakdown: true, show_gross_total: true,
    show_prepayments: true, show_payment_terms: true, show_bank_details: true, totals_alignment: 'right',
  },
  technical: {
    enabled: true, show_printer: true, show_plate: true, show_material: true, show_print_time: true,
    show_weight: true, show_file_name: true, placement: 'position',
  },
  notes: {
    show_intro_text: true, show_outro_text: true, show_payment_note: true, show_legal_note: true,
    intro_placement: 'before_positions', outro_placement: 'after_totals', keep_with_next: true,
  },
  footer: {
    enabled: true, column_layout: 'three', show_company_data: true, show_tax_data: true,
    show_bank_data: true, show_alternative_payment: true, show_additional_notes: true,
    show_page_numbers: true, page_number_format: '{page}/{pages}',
  },
};

export function layoutSummary(lockVersion = 3): LayoutSummary {
  return {
    id: 17,
    scope: { business_profile_id: 2, document_type: 'invoice', language: 'en' },
    version: 1,
    status: 'draft',
    lock_version: lockVersion,
    effective_from: null,
    created_at: '2026-07-23T08:00:00Z',
    updated_at: '2026-07-23T08:00:00Z',
  };
}

export function layoutDetail(lockVersion = 3): LayoutDetail {
  const sourced: SourcedDocumentLayout = {
    effective: effectiveLayout,
    page: { value: effectiveLayout.page, sources: sourcesFor(effectiveLayout.page) },
    typography: { value: effectiveLayout.typography, sources: sourcesFor(effectiveLayout.typography) },
    header: { value: effectiveLayout.header, sources: sourcesFor(effectiveLayout.header) },
    title: { value: effectiveLayout.title, sources: sourcesFor(effectiveLayout.title) },
    positions: { value: effectiveLayout.positions, sources: sourcesFor(effectiveLayout.positions) },
    totals: { value: effectiveLayout.totals, sources: sourcesFor(effectiveLayout.totals) },
    technical: { value: effectiveLayout.technical, sources: sourcesFor(effectiveLayout.technical) },
    notes: { value: effectiveLayout.notes, sources: sourcesFor(effectiveLayout.notes) },
    footer: { value: effectiveLayout.footer, sources: sourcesFor(effectiveLayout.footer) },
  };
  return {
    summary: layoutSummary(lockVersion),
    effective: effectiveLayout,
    sourced,
    validation_status: 'valid',
    validation_report: {},
    assets: [],
  };
}

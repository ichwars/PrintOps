import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { focusManager, QueryClient } from '@tanstack/react-query';
import { render } from '../utils';
import { server } from '../mocks/server';
import { OrdersCustomersPage } from '../../pages/OrdersCustomersPage';
import { setAuthToken } from '../../api/client';
import i18n from '../../i18n';

const profiles = [
  { id: 3, name: 'Inactive Profile', country_code: 'DE', default_currency: 'EUR', timezone: 'Europe/Berlin', default_locale: 'de', billing_mode: 'internal', is_default: false, is_active: false },
  { id: 7, name: 'Berlin Print Works', country_code: 'DE', default_currency: 'EUR', timezone: 'Europe/Berlin', default_locale: 'de', billing_mode: 'hybrid', is_default: true, is_active: true },
  { id: 8, name: 'Hamburg Lab', country_code: 'DE', default_currency: 'EUR', timezone: 'Europe/Berlin', default_locale: 'en', billing_mode: 'external', is_default: false, is_active: true },
] as const;

const listCustomer = {
  id: 11, business_profile_id: 7, account_number: 'C-0011', preferred_currency: 'EUR',
  payment_term_days: 14, delivery_terms: 'DAP', discount_percent: '2.50', account_is_active: true,
  display_name: 'Ada Example', company_name: null, first_name: 'Ada', last_name: 'Example', kind: 'person',
  status: 'active', preferred_locale: 'de', primary_contact_name: 'Ada Example',
  primary_contact_email: 'ada@example.test', billing_city: 'Berlin', billing_country_code: 'DE',
  tags: ['priority', 'prototype'], version: 4,
} as const;

const detailCustomer = {
  id: 11, kind: 'person', display_name: 'Ada Example', company_name: null, first_name: 'Ada', last_name: 'Example',
  status: 'active', preferred_locale: 'de', notes: 'Prefers email.',
  accounts: [
    { id: 102, business_profile_id: 8, number: 'HH-9', preferred_currency: 'EUR', payment_term_days: 30, delivery_terms: 'EXW', discount_percent: '0.00', is_active: true },
    { id: 101, business_profile_id: 7, number: 'C-0011', preferred_currency: 'EUR', payment_term_days: 14, delivery_terms: 'DAP', discount_percent: '2.50', is_active: true },
  ],
  contacts: [{ id: 201, salutation: 'Ms', first_name: 'Ada', last_name: 'Example', role: 'Owner', email: 'ada@example.test', phone: '+49 30 1', is_primary: true, include_on_documents: true }],
  addresses: [
    { id: 301, kind: 'billing', label: 'HQ', additional: null, street: 'Printstrasse 1', street_2: null, postal_code: '10115', city: 'Berlin', region: 'BE', country_code: 'DE', is_default: true },
    { id: 302, kind: 'delivery', label: 'Workshop', additional: 'Gate 2', street: 'Werkweg 4', street_2: null, postal_code: '10117', city: 'Berlin', region: 'BE', country_code: 'DE', is_default: true },
  ],
  tax_identifiers: [{ id: 401, kind: 'vat', value: 'DE123456789', country_code: 'DE', validation_status: 'valid' }],
  tags: ['priority', 'prototype'], version: 4, created_at: '2026-06-01T10:00:00Z', updated_at: '2026-07-01T12:30:00Z',
} as const;

function listResponse(items: readonly object[] = [listCustomer], overrides: Record<string, number> = {}) {
  return { items, total: items.length, limit: 25, offset: 0, ...overrides };
}

function useDefaultHandlers() {
  server.use(
    http.get('/api/v1/business-profiles/options', () => HttpResponse.json(profiles)),
    http.get('/api/v1/customers/', () => HttpResponse.json(listResponse())),
    http.get('/api/v1/customers/:id', () => HttpResponse.json(detailCustomer)),
  );
}

function enableAuth(permissions: string[]) {
  setAuthToken('customer-test-token');
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json({ id: 17, username: 'customer-user', role: 'user', is_active: true, is_admin: false, groups: [], permissions, created_at: '2026-01-01T00:00:00Z' })),
  );
}

async function openValidCreateEditor() {
  const user = userEvent.setup();
  render(<OrdersCustomersPage />);
  await screen.findByRole('button', { name: 'View Ada Example' });
  await user.click(screen.getByRole('button', { name: 'Add customer' }));
  await user.type(screen.getByRole('textbox', { name: 'Display name' }), 'Validation customer');
  await user.type(screen.getByRole('textbox', { name: 'First name' }), 'Validation');
  await user.type(screen.getByRole('textbox', { name: 'Last name' }), 'Customer');
  return user;
}

function trackCustomerMutations() {
  const counts = { post: 0, put: 0 };
  server.use(
    http.post('/api/v1/customers/', () => { counts.post += 1; return HttpResponse.json(detailCustomer, { status: 201 }); }),
    http.put('/api/v1/customers/:id', () => { counts.put += 1; return HttpResponse.json(detailCustomer); }),
  );
  return counts;
}

describe('OrdersCustomersPage', () => {
  beforeEach(() => {
    setAuthToken(null);
    useDefaultHandlers();
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage('en');
  });

  it('defaults to the active default profile and links no-profile state to settings', async () => {
    const requested: string[] = [];
    server.use(http.get('/api/v1/customers/', ({ request }) => {
      requested.push(new URL(request.url).searchParams.get('business_profile_id') ?? '');
      return HttpResponse.json(listResponse());
    }));
    const view = render(<OrdersCustomersPage />);
    expect(await screen.findByRole('button', { name: 'View Ada Example' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Business profile' })).toHaveValue('7');
    expect(screen.getByRole('option', { name: 'Inactive Profile' })).toBeDisabled();
    expect(requested).toEqual(['7']);
    view.unmount();

    let customerRequests = 0;
    server.use(
      http.get('/api/v1/business-profiles/options', () => HttpResponse.json([])),
      http.get('/api/v1/customers/', () => { customerRequests += 1; return HttpResponse.json(listResponse([])); }),
    );
    render(<OrdersCustomersPage />);
    expect(await screen.findByText('No active business profile is available.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Configure business profiles' })).toHaveAttribute('href', '/settings?tab=orders-calculation&sub=business-profile');
    expect(customerRequests).toBe(0);
  });

  it('clears a selected profile when refreshed options remove it', async () => {
    let optionRequests = 0;
    server.use(http.get('/api/v1/business-profiles/options', () => {
      optionRequests += 1;
      return HttpResponse.json(optionRequests === 1 ? profiles : []);
    }));

    render(<OrdersCustomersPage />);
    expect(await screen.findByRole('button', { name: 'Add customer' })).toBeInTheDocument();

    focusManager.setFocused(false);
    focusManager.setFocused(true);

    expect(await screen.findByText('No active business profile is available.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add customer' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Business profile' })).not.toBeInTheDocument();
  });

  it('debounces search for 300ms, sends status/kind, and resets offset on every selector', async () => {
    const user = userEvent.setup();
    const requests: Array<Record<string, string>> = [];
    server.use(http.get('/api/v1/customers/', ({ request }) => {
      const params = Object.fromEntries(new URL(request.url).searchParams);
      requests.push(params);
      return HttpResponse.json(listResponse([listCustomer], { total: 60, limit: 25, offset: Number(params.offset ?? 0) }));
    }));
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(requests.at(-1)?.offset).toBe('25'));
    await user.type(screen.getByRole('searchbox', { name: 'Search customers' }), 'Ada');
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(requests.at(-1)?.search).toBeUndefined();
    await waitFor(() => expect(requests.at(-1)).toMatchObject({ search: 'Ada', offset: '0' }), { timeout: 700 });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Customer status' }), 'inactive');
    await waitFor(() => expect(requests.at(-1)).toMatchObject({ status: 'inactive', offset: '0' }));
    await user.click(screen.getByRole('button', { name: 'Company' }));
    await waitFor(() => expect(requests.at(-1)).toMatchObject({ kind: 'company', offset: '0' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Business profile' }), '8');
    await waitFor(() => expect(requests.at(-1)).toMatchObject({ business_profile_id: '8', offset: '0' }));
  });

  it('renders flattened table fields, accessible actions, and backend pagination', async () => {
    server.use(http.get('/api/v1/customers/', ({ request }) => HttpResponse.json(listResponse([listCustomer], { total: 51, limit: 25, offset: Number(new URL(request.url).searchParams.get('offset') ?? 0) }))));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    const row = await screen.findByRole('row', { name: /C-0011 Ada Example/ });
    for (const value of ['C-0011', 'ada@example.test', 'Berlin, DE', 'Active', 'priority']) expect(within(row).getByText(value)).toBeInTheDocument();
    expect(within(row).getAllByText('Ada Example')).toHaveLength(2);
    for (const [name, title] of [['View Ada Example', 'View details'], ['Edit Ada Example', 'Edit customer'], ['Delete Ada Example', 'Delete customer']]) {
      expect(within(row).getByRole('button', { name })).toHaveAttribute('title', title);
    }
    expect(screen.getByText('1-25 of 51')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(await screen.findByText('26-50 of 51')).toBeInTheDocument();
  });

  it('keeps details usable for read-only users and shows every real aggregate', async () => {
    enableAuth(['customers:read']);
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'View Ada Example' }));
    const dialog = await screen.findByRole('dialog', { name: 'Customer details' });
    expect(screen.queryByRole('button', { name: 'Add customer' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit Ada Example' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete Ada Example' })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Edit customer' })).not.toBeInTheDocument();
    for (const value of ['Berlin Print Works', 'Hamburg Lab', 'Prefers email.', 'ada@example.test', 'Printstrasse 1', 'Werkweg 4', 'DE123456789', 'priority', 'Created Jun 1, 2026', 'Updated Jul 1, 2026']) {
      expect(within(dialog).getAllByText(value)[0]).toBeInTheDocument();
    }
    expect(within(dialog).queryByText(/revenue|receivable|history/i)).not.toBeInTheDocument();
  });

  it('localizes customer tax status and validation feedback in German', async () => {
    const user = userEvent.setup();
    await i18n.changeLanguage('de');
    const duplicatePrimary = {
      ...detailCustomer,
      contacts: [
        ...detailCustomer.contacts,
        { ...detailCustomer.contacts[0], id: 202, first_name: 'Berta', email: 'berta@example.test' },
      ],
    };
    server.use(http.get('/api/v1/customers/:id', () => HttpResponse.json(duplicatePrimary)));

    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Ada Example anzeigen' }));
    const details = await screen.findByRole('dialog', { name: 'Kundendetails' });
    const taxLine = within(details).getByText((_content, element) => element?.tagName === 'P' && element.textContent?.includes('DE123456789') === true);
    expect(taxLine).toHaveTextContent('Gültig');
    expect(taxLine).not.toHaveTextContent(/\bvalid\b/);
    await user.click(within(details).getByRole('button', { name: 'Schließen' }));

    await user.click(screen.getByRole('button', { name: 'Ada Example bearbeiten' }));
    await user.click(screen.getByRole('button', { name: 'Kunde speichern' }));
    expect(await screen.findAllByText('Es ist nur ein Hauptkontakt zulässig.')).toHaveLength(2);
  });

  it('submits complete nested data for create and normalizes tags', async () => {
    let submitted: Record<string, unknown> | null = null;
    server.use(http.post('/api/v1/customers/', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json(detailCustomer, { status: 201 });
    }));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Add customer' }));
    const editor = screen.getByRole('dialog', { name: 'Add customer' });
    await user.click(within(editor).getByRole('button', { name: 'Company' }));
    await user.type(screen.getByRole('textbox', { name: 'Display name' }), '  Nova Parts  ');
    await user.type(screen.getByRole('textbox', { name: 'Company name' }), 'Nova Parts GmbH');
    expect(screen.getByRole('combobox', { name: 'Account profile 1' })).toHaveValue('7');
    await user.type(screen.getByRole('textbox', { name: 'Customer number 1' }), 'N-42');
    await user.clear(screen.getByRole('spinbutton', { name: 'Payment days 1' }));
    await user.type(screen.getByRole('spinbutton', { name: 'Payment days 1' }), '21');
    await user.click(screen.getByRole('button', { name: 'Add contact' }));
    await user.type(screen.getByRole('textbox', { name: 'Contact first name 1' }), 'Lin');
    await user.type(screen.getByRole('textbox', { name: 'Contact email 1' }), 'lin@nova.test');
    await user.click(screen.getByRole('checkbox', { name: 'Primary contact 1' }));
    await user.click(screen.getByRole('checkbox', { name: 'Include contact 1 on documents' }));
    await user.click(screen.getByRole('button', { name: 'Add address' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Address kind 1' }), 'delivery');
    await user.type(screen.getByRole('textbox', { name: 'Street 1' }), 'Novaweg 8');
    await user.type(screen.getByRole('textbox', { name: 'Postal code 1' }), '20095');
    await user.type(screen.getByRole('textbox', { name: 'City 1' }), 'Hamburg');
    await user.click(screen.getByRole('checkbox', { name: 'Default address 1' }));
    await user.click(screen.getByRole('button', { name: 'Add tax identifier' }));
    await user.type(screen.getByRole('textbox', { name: 'Tax identifier value 1' }), 'DE999');
    await user.type(screen.getByRole('textbox', { name: 'Tags' }), ' VIP, prototype, vip, \u212b, A\u030a, new ');
    await user.type(screen.getByRole('textbox', { name: 'Notes' }), 'First order pending.');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await waitFor(() => expect(submitted).not.toBeNull());
    expect(submitted).toMatchObject({
      kind: 'company', display_name: 'Nova Parts', company_name: 'Nova Parts GmbH', status: 'active', preferred_locale: 'de', notes: 'First order pending.',
      accounts: [{ business_profile_id: 7, number: 'N-42', preferred_currency: 'EUR', payment_term_days: 21, delivery_terms: null, discount_percent: '0.00', is_active: true }],
      contacts: [{ first_name: 'Lin', email: 'lin@nova.test', is_primary: true, include_on_documents: true }],
      addresses: [{ kind: 'delivery', street: 'Novaweg 8', postal_code: '20095', city: 'Hamburg', country_code: 'DE', is_default: true }],
      tax_identifiers: [{ kind: 'vat', value: 'DE999', country_code: 'DE', validation_status: 'unchecked' }],
      tags: ['new', 'prototype', 'VIP', 'A\u030a'],
    });
  });

  it('matches backend tag display selection and display ordering for Unicode equivalents', async () => {
    let submitted: Record<string, unknown> | null = null;
    server.use(http.post('/api/v1/customers/', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json(detailCustomer, { status: 201 });
    }));
    const user = await openValidCreateEditor();
    await user.type(screen.getByRole('textbox', { name: 'Tags' }), '\u212b, A\u030a, \u00c5, vip, VIP, Stra\u00dfe, STRASSE');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await waitFor(() => expect(submitted).not.toBeNull());
    expect(submitted?.tags).toEqual(['STRASSE', 'VIP', 'A\u030a']);
  });

  it('rejects tag normalized keys above 512 UTF-8 bytes without a request and accepts the boundary', async () => {
    const counts = trackCustomerMutations();
    const user = await openValidCreateEditor();
    const tags = screen.getByRole('textbox', { name: 'Tags' });
    await user.type(tags, '\u0390'.repeat(100));
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('512');
    expect(tags).toHaveAccessibleDescription();
    expect(counts.post).toBe(0);

    await user.clear(tags);
    await user.type(tags, `${'\u0390'.repeat(85)}aa`);
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await waitFor(() => expect(counts.post).toBe(1));
  });

  it('maps nested 422 feedback and keeps the editor footer stable', async () => {
    server.use(http.post('/api/v1/customers/', () => HttpResponse.json({ detail: [{ loc: ['body', 'contacts', 0, 'email'], msg: 'Value error, Invalid email' }] }, { status: 422 })));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Add customer' }));
    await user.type(screen.getByRole('textbox', { name: 'Display name' }), 'Nova');
    await user.type(screen.getByRole('textbox', { name: 'First name' }), 'Nova');
    await user.type(screen.getByRole('textbox', { name: 'Last name' }), 'Customer');
    await user.click(screen.getByRole('button', { name: 'Add contact' }));
    await user.type(screen.getByRole('textbox', { name: 'Contact email 1' }), 'bad@example.test');
    const footer = screen.getByTestId('customer-editor-footer');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(await screen.findByText('Invalid email')).toBeInTheDocument();
    expect(footer).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Add customer' })).toBeInTheDocument();
  });

  it('uses a dedicated scroll viewport between the editor header and footer', async () => {
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Add customer' }));

    const dialog = screen.getByRole('dialog', { name: 'Add customer' });
    const viewport = within(dialog).getByTestId('customer-editor-scroll-viewport');
    const fieldset = viewport.firstElementChild;

    expect(dialog.children[1]).toBe(viewport);
    expect(viewport.previousElementSibling).toBe(dialog.firstElementChild);
    expect(viewport.nextElementSibling).toBe(dialog.lastElementChild);
    expect(viewport).toHaveClass('min-h-0', 'flex-1', 'overflow-y-auto');
    expect(fieldset).toHaveProperty('tagName', 'FIELDSET');
    expect(fieldset).not.toHaveClass('flex-1', 'overflow-y-auto');
  });

  it('blocks incomplete company and person identities before creating a customer', async () => {
    let createRequests = 0;
    server.use(http.post('/api/v1/customers/', () => { createRequests += 1; return HttpResponse.json(detailCustomer, { status: 201 }); }));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Add customer' }));
    await user.type(screen.getByRole('textbox', { name: 'Display name' }), 'Incomplete person');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(await screen.findAllByText('Required')).toHaveLength(2);
    expect(createRequests).toBe(0);

    await user.click(within(screen.getByRole('dialog', { name: 'Add customer' })).getByRole('button', { name: 'Company' }));
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(await screen.findByText('Required')).toBeInTheDocument();
    expect(createRequests).toBe(0);
  });

  it('blocks invalid account and tax payloads before creating a customer', async () => {
    const mutationRequests = trackCustomerMutations();
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Add customer' }));
    await user.type(screen.getByRole('textbox', { name: 'Display name' }), 'Invalid account');
    await user.type(screen.getByRole('textbox', { name: 'First name' }), 'Invalid');
    await user.type(screen.getByRole('textbox', { name: 'Last name' }), 'Account');
    await user.clear(screen.getByRole('textbox', { name: 'Customer number 1' }));
    await user.type(screen.getByRole('textbox', { name: 'Customer number 1' }), 'X'.repeat(51));
    await user.clear(screen.getByRole('textbox', { name: 'Currency 1' }));
    await user.type(screen.getByRole('textbox', { name: 'Currency 1' }), 'ZZZ');
    await user.clear(screen.getByRole('spinbutton', { name: 'Payment days 1' }));
    await user.type(screen.getByRole('spinbutton', { name: 'Payment days 1' }), '366');
    await user.clear(screen.getByRole('spinbutton', { name: 'Discount 1' }));
    await user.type(screen.getByRole('spinbutton', { name: 'Discount 1' }), '99.999');
    await user.click(screen.getByRole('button', { name: 'Add tax identifier' }));
    await user.clear(screen.getByRole('textbox', { name: 'Tax identifier kind 1' }));
    await user.clear(screen.getByRole('textbox', { name: 'Tax identifier value 1' }));
    await user.clear(screen.getByRole('textbox', { name: 'Tax country 1' }));
    await user.type(screen.getByRole('textbox', { name: 'Tax country 1' }), 'XX');
    await user.clear(screen.getByRole('textbox', { name: 'Locale' }));
    await user.type(screen.getByRole('textbox', { name: 'Locale' }), 'x');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(screen.getByRole('textbox', { name: 'Customer number 1' })).toHaveAccessibleDescription('Must be at most 50 characters.');
    expect(screen.getByRole('textbox', { name: 'Currency 1' })).toHaveAccessibleDescription('Enter a valid ISO 4217 currency code.');
    expect(screen.getByRole('spinbutton', { name: 'Payment days 1' })).toHaveAccessibleDescription('Must be between 0 and 365.');
    expect(screen.getByRole('spinbutton', { name: 'Discount 1' })).toHaveAccessibleDescription('Use no more than two decimal places.');
    expect(screen.getByRole('textbox', { name: 'Tax identifier kind 1' })).toHaveAccessibleDescription('Required');
    expect(screen.getByRole('textbox', { name: 'Tax identifier value 1' })).toHaveAccessibleDescription('Required');
    expect(screen.getByRole('textbox', { name: 'Tax country 1' })).toHaveAccessibleDescription('Enter a valid ISO 3166-1 alpha-2 country code.');
    expect(screen.getByRole('textbox', { name: 'Locale' })).toHaveAccessibleDescription('Required');
    expect(mutationRequests).toEqual({ post: 0, put: 0 });
  });

  it('rejects an Intl-only currency at the account field before mutation', async () => {
    const mutationRequests = trackCustomerMutations();
    const user = await openValidCreateEditor();
    const currency = screen.getByRole('textbox', { name: 'Currency 1' });
    await user.clear(currency);
    await user.type(currency, 'ANG');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(currency).toHaveAccessibleDescription('Enter a valid ISO 4217 currency code.');
    expect(mutationRequests).toEqual({ post: 0, put: 0 });
  });

  it('accepts a pycountry currency that is missing from Intl', async () => {
    const mutationRequests = trackCustomerMutations();
    const user = await openValidCreateEditor();
    const currency = screen.getByRole('textbox', { name: 'Currency 1' });
    await user.clear(currency);
    await user.type(currency, 'BOV');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await waitFor(() => expect(mutationRequests).toEqual({ post: 1, put: 0 }));
  });

  it('rejects an Intl-only address country at the field before mutation', async () => {
    const mutationRequests = trackCustomerMutations();
    const user = await openValidCreateEditor();
    await user.click(screen.getByRole('button', { name: 'Add address' }));
    await user.type(screen.getByRole('textbox', { name: 'Street 1' }), 'Example 1');
    await user.type(screen.getByRole('textbox', { name: 'Postal code 1' }), '10115');
    await user.type(screen.getByRole('textbox', { name: 'City 1' }), 'Berlin');
    const country = screen.getByRole('textbox', { name: 'Country 1' });
    await user.clear(country);
    await user.type(country, 'AC');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(country).toHaveAccessibleDescription('Enter a valid ISO 3166-1 alpha-2 country code.');
    expect(mutationRequests).toEqual({ post: 0, put: 0 });
  });

  it('rejects an Intl-only tax country at the field before mutation', async () => {
    const mutationRequests = trackCustomerMutations();
    const user = await openValidCreateEditor();
    await user.click(screen.getByRole('button', { name: 'Add tax identifier' }));
    await user.type(screen.getByRole('textbox', { name: 'Tax identifier value 1' }), 'DE123');
    const country = screen.getByRole('textbox', { name: 'Tax country 1' });
    await user.clear(country);
    await user.type(country, 'AC');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(country).toHaveAccessibleDescription('Enter a valid ISO 3166-1 alpha-2 country code.');
    expect(mutationRequests).toEqual({ post: 0, put: 0 });
  });

  it.each([
    ['Straße', 'STRASSE'],
    ['ΐ', 'ι\u0308\u0301'],
  ])('rejects backend-equivalent duplicate tax values %s and %s before mutation', async (first, second) => {
    const mutationRequests = trackCustomerMutations();
    const user = await openValidCreateEditor();
    await user.click(screen.getByRole('button', { name: 'Add tax identifier' }));
    await user.click(screen.getByRole('button', { name: 'Add tax identifier' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Tax identifier value 1' }), { target: { value: first } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Tax identifier value 2' }), { target: { value: second } });
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    const message = 'Duplicate tax identifiers are not allowed.';
    expect(screen.getByRole('textbox', { name: 'Tax identifier value 1' })).toHaveAccessibleDescription(message);
    expect(screen.getByRole('textbox', { name: 'Tax identifier value 2' })).toHaveAccessibleDescription(message);
    expect(mutationRequests).toEqual({ post: 0, put: 0 });
  });

  it('rejects a tax kind that exceeds the limit after Unicode normalization', async () => {
    const mutationRequests = trackCustomerMutations();
    const user = await openValidCreateEditor();
    await user.click(screen.getByRole('button', { name: 'Add tax identifier' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Tax identifier kind 1' }), { target: { value: 'ß'.repeat(17) } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Tax identifier value 1' }), { target: { value: 'DE123' } });

    await user.click(screen.getByRole('button', { name: 'Save customer' }));

    expect(screen.getByRole('textbox', { name: 'Tax identifier kind 1' })).toHaveAccessibleDescription('Must be at most 32 characters.');
    expect(mutationRequests).toEqual({ post: 0, put: 0 });
  });

  it('maps tags.0 validation feedback to the Tags control', async () => {
    let createRequests = 0;
    server.use(http.post('/api/v1/customers/', () => {
      createRequests += 1;
      return HttpResponse.json({ detail: [{ loc: ['body', 'tags', 0], msg: 'Tag is invalid' }] }, { status: 422 });
    }));
    const user = await openValidCreateEditor();
    await user.type(screen.getByRole('textbox', { name: 'Tags' }), 'invalid');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    const tags = screen.getByRole('textbox', { name: 'Tags' });
    await waitFor(() => expect(tags).toHaveAccessibleDescription('Tag is invalid'));
    expect(screen.getAllByText('Tag is invalid')).toHaveLength(1);
    expect(createRequests).toBe(1);
  });

  it('maps nested 422 feedback to its controls and keeps unmapped feedback visible', async () => {
    server.use(http.post('/api/v1/customers/', () => HttpResponse.json({ detail: [
      { loc: ['body', 'accounts', 0, 'payment_term_days'], msg: 'Payment terms are invalid' },
      { loc: ['body', 'version'], msg: 'Version cannot be changed' },
    ] }, { status: 422 })));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Add customer' }));
    await user.type(screen.getByRole('textbox', { name: 'Display name' }), 'Nested error');
    await user.type(screen.getByRole('textbox', { name: 'First name' }), 'Nested');
    await user.type(screen.getByRole('textbox', { name: 'Last name' }), 'Error');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(await screen.findByText('Payment terms are invalid')).toBeInTheDocument();
    expect(screen.getByText('Version cannot be changed')).toBeInTheDocument();
  });

  it('refetches authoritative list variants after edit instead of partially patching the visible row', async () => {
    let submitted: Record<string, unknown> | null = null;
    let updated = false;
    const requests: Array<Record<string, string>> = [];
    const updatedDetail = {
      ...detailCustomer,
      kind: 'company' as const, display_name: 'Nova GmbH', company_name: 'Nova GmbH', first_name: null, last_name: null,
      status: 'inactive' as const, version: 5,
      accounts: [{ ...detailCustomer.accounts[0] }, { ...detailCustomer.accounts[1], number: 'N-500' }],
      contacts: [{ ...detailCustomer.contacts[0], first_name: 'Lin', last_name: 'Updated', email: 'lin.updated@example.test' }],
      addresses: [{ ...detailCustomer.addresses[0], city: 'Hamburg' }, ...detailCustomer.addresses.slice(1)],
    };
    const updatedList = {
      ...listCustomer, account_number: 'N-500', display_name: 'Nova GmbH', company_name: 'Nova GmbH', first_name: null, last_name: null,
      kind: 'company', status: 'inactive', primary_contact_name: 'Lin Updated', primary_contact_email: 'lin.updated@example.test', billing_city: 'Hamburg', version: 5,
    };
    server.use(
      http.get('/api/v1/customers/', ({ request }) => {
        const params = Object.fromEntries(new URL(request.url).searchParams);
        requests.push(params);
        const matchesUpdated = updated && params.status === 'inactive' && params.kind === 'company';
        return HttpResponse.json(listResponse(matchesUpdated ? [updatedList] : updated ? [] : [listCustomer]));
      }),
      http.put('/api/v1/customers/11', async ({ request }) => {
        submitted = await request.json() as Record<string, unknown>;
        updated = true;
        return HttpResponse.json(updatedDetail);
      }),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Customer status' }), 'active');
    await user.click(screen.getByRole('button', { name: 'Person' }));
    await waitFor(() => expect(requests.at(-1)).toMatchObject({ status: 'active', kind: 'person' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Customer status' }), 'inactive');
    await user.click(screen.getByRole('button', { name: 'Company' }));
    await waitFor(() => expect(requests.at(-1)).toMatchObject({ status: 'inactive', kind: 'company' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Customer status' }), 'active');
    await user.click(screen.getByRole('button', { name: 'Person' }));
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    const editor = await screen.findByRole('dialog', { name: 'Edit customer' });
    const name = await screen.findByRole('textbox', { name: 'Display name' });
    await user.clear(name);
    await user.type(name, 'Nova GmbH');
    await user.click(within(editor).getByRole('button', { name: 'Company' }));
    await user.type(screen.getByRole('textbox', { name: 'Company name' }), 'Nova GmbH');
    await user.clear(screen.getByRole('textbox', { name: 'Customer number 2' }));
    await user.type(screen.getByRole('textbox', { name: 'Customer number 2' }), 'N-500');
    await user.clear(screen.getByRole('textbox', { name: 'Contact first name 1' }));
    await user.type(screen.getByRole('textbox', { name: 'Contact first name 1' }), 'Lin');
    await user.clear(screen.getByRole('textbox', { name: 'Contact last name 1' }));
    await user.type(screen.getByRole('textbox', { name: 'Contact last name 1' }), 'Updated');
    await user.clear(screen.getByRole('textbox', { name: 'Contact email 1' }));
    await user.type(screen.getByRole('textbox', { name: 'Contact email 1' }), 'lin.updated@example.test');
    await user.clear(screen.getByRole('textbox', { name: 'City 1' }));
    await user.type(screen.getByRole('textbox', { name: 'City 1' }), 'Hamburg');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'inactive');
    const activePersonRequestsBeforeEdit = requests.filter((params) => params.status === 'active' && params.kind === 'person').length;
    const inactiveCompanyRequestsBeforeReactivation = requests.filter((params) => params.status === 'inactive' && params.kind === 'company').length;
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await waitFor(() => expect(submitted).toMatchObject({ display_name: 'Nova GmbH', version: 4 }));
    await waitFor(() => expect(requests.filter((params) => params.status === 'active' && params.kind === 'person').length).toBeGreaterThan(activePersonRequestsBeforeEdit));
    expect(requests.filter((params) => params.status === 'inactive' && params.kind === 'company')).toHaveLength(inactiveCompanyRequestsBeforeReactivation);
    expect(await screen.findByText('No customers match the current filters.')).toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Customer status' }), 'inactive');
    await user.click(screen.getByRole('button', { name: 'Company' }));
    await waitFor(() => expect(requests.filter((params) => params.status === 'inactive' && params.kind === 'company').length).toBeGreaterThan(inactiveCompanyRequestsBeforeReactivation));
    const updatedRow = await screen.findByRole('row', { name: /N-500 Nova GmbH/ });
    for (const value of ['N-500', 'Lin Updated', 'lin.updated@example.test', 'Hamburg, DE', 'Inactive']) expect(within(updatedRow).getByText(value)).toBeInTheDocument();
  });

  it('retains editor input after 409 and reloads current data on command', async () => {
    let detailRequests = 0;
    const submittedVersions: number[] = [];
    server.use(
      http.get('/api/v1/customers/11', () => {
        detailRequests += 1;
        return HttpResponse.json(detailRequests === 1 ? detailCustomer : { ...detailCustomer, display_name: 'Server Current', version: 5 });
      }),
      http.put('/api/v1/customers/11', async ({ request }) => {
        submittedVersions.push((await request.json() as { version: number }).version);
        return submittedVersions.length === 1
          ? HttpResponse.json({ detail: 'Customer was changed by another user.' }, { status: 409 })
          : HttpResponse.json({ ...detailCustomer, version: 6 });
      }),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    const name = await screen.findByRole('textbox', { name: 'Display name' });
    await user.clear(name);
    await user.type(name, 'My Unsaved Name');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    expect(await screen.findByText('Customer was changed by another user.')).toBeInTheDocument();
    expect(name).toHaveValue('My Unsaved Name');
    await user.click(screen.getByRole('button', { name: 'Reload current data' }));
    expect(await screen.findByRole('textbox', { name: 'Display name' })).toHaveValue('Server Current');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await waitFor(() => expect(submittedVersions).toEqual([4, 5]));
  });

  it('keeps an accepted explicit reload ahead of an older background refetch', async () => {
    let detailRequests = 0;
    let resolveBackground: ((response: Response) => void) | undefined;
    let resolveExplicit: ((response: Response) => void) | undefined;
    const cancelQueries = vi.spyOn(QueryClient.prototype, 'cancelQueries');
    server.use(
      http.get('/api/v1/customers/11', () => {
        detailRequests += 1;
        if (detailRequests === 1) return HttpResponse.json(detailCustomer);
        if (detailRequests === 2) return new Promise<Response>((resolve) => { resolveBackground = resolve; });
        if (detailRequests === 3) return new Promise<Response>((resolve) => { resolveExplicit = resolve; });
        return new Promise<Response>(() => {});
      }),
      http.put('/api/v1/customers/11', () => HttpResponse.json({ detail: 'Customer was changed by another user.' }, { status: 409 })),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    await screen.findByRole('textbox', { name: 'Display name' });

    focusManager.setFocused(false);
    focusManager.setFocused(true);
    await waitFor(() => expect(resolveBackground).toBeTypeOf('function'));
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await user.click(await screen.findByRole('button', { name: 'Reload current data' }));
    await waitFor(() => expect(resolveExplicit).toBeTypeOf('function'));

    await act(async () => {
      resolveExplicit!(HttpResponse.json({ ...detailCustomer, display_name: 'Explicit winner', version: 8 }));
    });
    expect(await screen.findByRole('textbox', { name: 'Display name' })).toHaveValue('Explicit winner');
    expect(cancelQueries).toHaveBeenCalledWith({ queryKey: ['customer', 11], exact: true });

    const queryClient = cancelQueries.mock.contexts[0] as QueryClient;
    await act(async () => {
      resolveBackground!(HttpResponse.json({ ...detailCustomer, display_name: 'Old background', version: 7 }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(queryClient.getQueryData<CustomerDetail>(['customer', 11])?.display_name).toBe('Explicit winner');
    expect(screen.getByRole('textbox', { name: 'Display name' })).toHaveValue('Explicit winner');
  });

  it('locks editing and does not cache an older reload after close and reopen', async () => {
    let detailRequests = 0;
    const resolvers: Array<(response: Response) => void> = [];
    const setQueryData = vi.spyOn(QueryClient.prototype, 'setQueryData');
    server.use(
      http.get('/api/v1/customers/11', () => {
        detailRequests += 1;
        if (detailRequests === 1) return HttpResponse.json(detailCustomer);
        return new Promise<Response>((resolve) => resolvers.push(resolve));
      }),
      http.put('/api/v1/customers/11', () => HttpResponse.json({ detail: 'Customer was changed by another user.' }, { status: 409 })),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    const name = await screen.findByRole('textbox', { name: 'Display name' });
    await user.clear(name);
    await user.type(name, 'Unsaved');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    const reload = await screen.findByRole('button', { name: 'Reload current data' });
    await act(async () => {
      reload.click();
      reload.click();
    });
    await waitFor(() => expect(resolvers).toHaveLength(2));
    expect(name).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save customer' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled();
    await user.type(name, ' lost');
    expect(name).toHaveValue('Unsaved');

    await act(async () => {
      resolvers[1](HttpResponse.json({ ...detailCustomer, display_name: 'Newest', version: 6 }));
    });
    await waitFor(() => expect(name).toHaveValue('Newest'));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    await act(async () => {
      resolvers[0](HttpResponse.json({ ...detailCustomer, display_name: 'Stale', version: 5 }));
    });
    await waitFor(() => expect(setQueryData.mock.calls
      .filter(([queryKey]) => JSON.stringify(queryKey) === JSON.stringify(['customer', 11]))
      .map(([, customer]) => (customer as CustomerDetail).display_name)).toEqual(['Newest']));
    await user.click(screen.getByRole('button', { name: 'Edit Ada Example' }));
    expect(await screen.findByRole('dialog', { name: 'Loading customer editor' })).toBeInTheDocument();
  });

  it('completes and unlocks explicit reload under StrictMode', async () => {
    let detailRequests = 0;
    server.use(
      http.get('/api/v1/customers/11', () => {
        detailRequests += 1;
        return HttpResponse.json(detailRequests === 1 ? detailCustomer : { ...detailCustomer, display_name: 'Strict current', version: 8 });
      }),
      http.put('/api/v1/customers/11', () => HttpResponse.json({ detail: 'Customer was changed by another user.' }, { status: 409 })),
    );
    const user = userEvent.setup();
    render(<StrictMode><OrdersCustomersPage /></StrictMode>);
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    await user.click(await screen.findByRole('button', { name: 'Save customer' }));
    await user.click(await screen.findByRole('button', { name: 'Reload current data' }));
    expect(await screen.findByRole('textbox', { name: 'Display name' })).toHaveValue('Strict current');
    expect(screen.getByRole('button', { name: 'Close' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Save customer' })).toBeEnabled();
  });

  it('shows explicit reload failure and retries successfully', async () => {
    let detailRequests = 0;
    server.use(
      http.get('/api/v1/customers/11', () => {
        detailRequests += 1;
        if (detailRequests === 1) return HttpResponse.json(detailCustomer);
        if (detailRequests === 2) return HttpResponse.json({ detail: 'Reload unavailable.' }, { status: 503 });
        return HttpResponse.json({ ...detailCustomer, display_name: 'Recovered', version: 7 });
      }),
      http.put('/api/v1/customers/11', () => HttpResponse.json({ detail: 'Customer was changed by another user.' }, { status: 409 })),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await user.click(await screen.findByRole('button', { name: 'Reload current data' }));
    const reloadMessage = await screen.findByText('Reload unavailable.');
    const reloadAlert = reloadMessage.closest('[role="alert"]');
    expect(reloadAlert).toHaveTextContent('Reload unavailable.');
    expect(within(reloadAlert as HTMLElement).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close' })).toBeEnabled();
    await user.click(within(reloadAlert as HTMLElement).getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('textbox', { name: 'Display name' })).toHaveValue('Recovered');
  });

  it('keeps exactly one details dialog with an inline retry on retained-data refetch error', async () => {
    let detailRequests = 0;
    server.use(http.get('/api/v1/customers/11', () => {
      detailRequests += 1;
      return detailRequests === 1 ? HttpResponse.json(detailCustomer) : HttpResponse.json({ detail: 'Refresh failed.' }, { status: 500 });
    }));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'View Ada Example' }));
    await screen.findByRole('dialog', { name: 'Customer details' });
    focusManager.setFocused(false);
    focusManager.setFocused(true);
    expect(await screen.findByRole('alert')).toHaveTextContent('Refresh failed.');
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.getAllByRole('dialog').filter((dialog) => dialog.getAttribute('aria-modal') === 'true')).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(detailRequests).toBeGreaterThan(2));
  });

  it('submits the version snapshotted when editing began after a background detail refresh', async () => {
    let detailRequests = 0;
    let submittedVersion: number | null = null;
    server.use(
      http.get('/api/v1/customers/11', () => {
        detailRequests += 1;
        return HttpResponse.json(detailRequests === 1 ? detailCustomer : { ...detailCustomer, version: 9 });
      }),
      http.put('/api/v1/customers/11', async ({ request }) => {
        submittedVersion = (await request.json() as { version: number }).version;
        return HttpResponse.json({ ...detailCustomer, version: 5 });
      }),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    const name = await screen.findByRole('textbox', { name: 'Display name' });
    await user.clear(name);
    await user.type(name, 'Locally edited');
    focusManager.setFocused(false);
    focusManager.setFocused(true);
    await waitFor(() => expect(detailRequests).toBeGreaterThan(1));
    expect(name).toHaveValue('Locally edited');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await waitFor(() => expect(submittedVersion).toBe(4));
  });

  it('uses one customer dialog owner and traps/restores focus across details to edit', async () => {
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    const trigger = await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(trigger);
    const edit = await screen.findByRole('button', { name: 'Edit customer' });
    await waitFor(() => expect(edit).toHaveFocus());
    await user.click(edit);
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.queryByRole('dialog', { name: 'Customer details' })).not.toBeInTheDocument();
    const name = await screen.findByRole('textbox', { name: 'Display name' });
    await waitFor(() => expect(name).toHaveFocus());
    const close = screen.getByRole('button', { name: 'Close' });
    const save = screen.getByRole('button', { name: 'Save customer' });
    close.focus();
    await user.tab({ shift: true });
    expect(save).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    fireEvent.keyDown(close, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('preserves repeatable-row DOM identity and strips client keys from the payload', async () => {
    const threeContacts = {
      ...detailCustomer,
      contacts: [
        detailCustomer.contacts[0],
        { ...detailCustomer.contacts[0], id: 202, first_name: 'Middle', email: 'middle@example.test', is_primary: false },
        { ...detailCustomer.contacts[0], id: 203, first_name: 'Later', email: 'later@example.test', is_primary: false },
      ],
    };
    let submitted: Record<string, unknown> | null = null;
    server.use(
      http.get('/api/v1/customers/11', () => HttpResponse.json(threeContacts)),
      http.put('/api/v1/customers/11', async ({ request }) => {
        submitted = await request.json() as Record<string, unknown>;
        return HttpResponse.json(detailCustomer);
      }),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    const laterInput = await screen.findByRole('textbox', { name: 'Contact first name 3' });
    await user.click(screen.getByRole('button', { name: 'Remove contact 2' }));
    expect(screen.getByRole('textbox', { name: 'Contact first name 2' })).toBe(laterInput);
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    await waitFor(() => expect(submitted).not.toBeNull());
    expect((submitted?.contacts as Array<Record<string, unknown>>).map((contact) => contact.first_name)).toEqual(['Ada', 'Later']);
    expect(JSON.stringify(submitted)).not.toContain('_clientKey');
  });

  it('reaches delete from details, invalidates the list, and closes details', async () => {
    let listRequests = 0;
    let deleted = false;
    server.use(
      http.get('/api/v1/customers/', () => { listRequests += 1; return HttpResponse.json(listResponse(deleted ? [] : [listCustomer])); }),
      http.delete('/api/v1/customers/11', () => { deleted = true; return new HttpResponse(null, { status: 204 }); }),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'View Ada Example' }));
    expect(await screen.findByRole('dialog', { name: 'Customer details' })).toBeInTheDocument();
    await user.click(within(screen.getByRole('dialog', { name: 'Customer details' })).getByRole('button', { name: 'Delete customer' }));
    expect(screen.getByText('Delete Ada Example?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete customer' }));
    await waitFor(() => expect(listRequests).toBeGreaterThan(1));
    expect(screen.queryByRole('dialog', { name: 'Customer details' })).not.toBeInTheDocument();
    expect(await screen.findByText('No customers yet.')).toBeInTheDocument();
  });

  it('recovers to the previous last page after deleting its only row', async () => {
    const offsets: number[] = [];
    let deleted = false;
    server.use(
      http.get('/api/v1/customers/', ({ request }) => {
        const offset = Number(new URL(request.url).searchParams.get('offset') ?? 0);
        offsets.push(offset);
        if (offset === 25) return HttpResponse.json(listResponse(deleted ? [] : [listCustomer], { total: deleted ? 25 : 26, offset: 25 }));
        return HttpResponse.json(listResponse([listCustomer], { total: deleted ? 25 : 26, offset: 0 }));
      }),
      http.delete('/api/v1/customers/11', () => { deleted = true; return new HttpResponse(null, { status: 204 }); }),
    );
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await screen.findByText('26-26 of 26');
    await user.click(screen.getByRole('button', { name: 'Delete Ada Example' }));
    await user.click(screen.getByRole('button', { name: 'Delete customer' }));
    await waitFor(() => expect(offsets.at(-1)).toBe(0));
    expect(await screen.findByText('1-25 of 25')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
  });

  it('recovers detail and editor query errors with retry and close', async () => {
    let detailRequests = 0;
    server.use(http.get('/api/v1/customers/11', () => {
      detailRequests += 1;
      return detailRequests % 2 === 1 ? HttpResponse.json({ detail: 'failure' }, { status: 500 }) : HttpResponse.json(detailCustomer);
    }));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    const viewTrigger = await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(viewTrigger);
    expect(await screen.findByText('Unable to load customer details.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('dialog', { name: 'Customer details' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close' }));
    const editTrigger = screen.getByRole('button', { name: 'Edit Ada Example' });
    await user.click(editTrigger);
    expect(await screen.findByText('Unable to load the customer editor.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('dialog', { name: 'Edit customer' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(editTrigger).toHaveFocus();
  });

  it('keeps a failed delete visible with retry and dismiss actions', async () => {
    let attempts = 0;
    server.use(http.delete('/api/v1/customers/11', () => {
      attempts += 1;
      return attempts === 1 ? HttpResponse.json({ detail: 'Customer is referenced.' }, { status: 409 }) : new HttpResponse(null, { status: 204 });
    }));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'View Ada Example' }));
    await user.click(within(screen.getByRole('dialog', { name: 'Customer details' })).getByRole('button', { name: 'Delete customer' }));
    await user.click(screen.getByRole('button', { name: 'Delete customer' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Customer is referenced.');
    expect(screen.getByRole('button', { name: 'Dismiss' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(attempts).toBe(2));
    expect(screen.queryByText('Delete Ada Example?')).not.toBeInTheDocument();
  });

  it('localizes a structured not-found error in German', async () => {
    await i18n.changeLanguage('de');
    server.use(http.delete('/api/v1/customers/11', () => HttpResponse.json({
      detail: { code: 'not_found', message: 'Customer 11 was not found' },
    }, { status: 404 })));
    const user = userEvent.setup();

    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Ada Example löschen' }));
    await user.click(screen.getByRole('button', { name: 'Kunde löschen' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Der Datensatz wurde nicht gefunden.');
    expect(screen.queryByText('Customer 11 was not found')).not.toBeInTheDocument();
  });

  it('keeps Escape and the stable footer pending-safe', async () => {
    server.use(http.post('/api/v1/customers/', async () => { await delay('infinite'); return HttpResponse.json(detailCustomer); }));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await screen.findByRole('button', { name: 'View Ada Example' });
    await user.click(screen.getByRole('button', { name: 'Add customer' }));
    await user.type(screen.getByRole('textbox', { name: 'Display name' }), 'Pending Customer');
    await user.type(screen.getByRole('textbox', { name: 'First name' }), 'Pending');
    await user.type(screen.getByRole('textbox', { name: 'Last name' }), 'Customer');
    await user.click(screen.getByRole('button', { name: 'Save customer' }));
    const focusedControl = screen.getByRole('button', { name: 'Saving...' });
    focusedControl.focus();
    fireEvent.keyDown(focusedControl, { key: 'Escape' });
    expect(screen.getByRole('dialog', { name: 'Add customer' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
    expect(screen.getByRole('dialog', { name: 'Add customer' })).toContainElement(document.activeElement as HTMLElement);
    const dialog = screen.getByRole('dialog', { name: 'Add customer' });
    fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(dialog).toHaveFocus();
    expect(screen.getByTestId('customer-editor-footer')).toBeInTheDocument();
  });

  it('renders loading, empty filtered, error with retry, and denied distinctly', async () => {
    server.use(http.get('/api/v1/customers/', () => new Promise(() => {})));
    const loadingView = render(<OrdersCustomersPage />);
    await waitFor(() => expect(screen.getByLabelText('Loading customers')).toBeInTheDocument());
    loadingView.unmount();

    server.use(http.get('/api/v1/customers/', () => HttpResponse.json(listResponse([]))));
    const emptyView = render(<OrdersCustomersPage />);
    expect(await screen.findByText('No customers yet.')).toBeInTheDocument();
    emptyView.unmount();

    let requests = 0;
    server.use(http.get('/api/v1/customers/', () => {
      requests += 1;
      return requests === 1 ? HttpResponse.json({ detail: 'failure' }, { status: 500 }) : HttpResponse.json(listResponse());
    }));
    const errorView = render(<OrdersCustomersPage />);
    expect(await screen.findByText('Unable to load customers.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('button', { name: 'View Ada Example' })).toBeInTheDocument();
    errorView.unmount();

    enableAuth([]);
    let deniedQueries = 0;
    server.use(http.get('/api/v1/customers/', () => { deniedQueries += 1; return HttpResponse.json(listResponse()); }));
    render(<OrdersCustomersPage />);
    expect(await screen.findByText('You do not have permission to view customers.')).toBeInTheDocument();
    expect(deniedQueries).toBe(0);
  });

  it('makes editor loading a named, focus-trapped modal and keeps one modal owner', async () => {
    server.use(http.get('/api/v1/customers/11', () => new Promise(() => {})));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'Edit Ada Example' }));
    const dialog = await screen.findByRole('dialog', { name: 'Loading customer editor' });
    expect(within(dialog).getByRole('status', { name: 'Loading customer editor' })).toBeInTheDocument();
    await waitFor(() => expect(dialog).toHaveFocus());
    await user.tab();
    expect(dialog).toHaveFocus();
    await user.keyboard('{Escape}{Enter}');
    expect(screen.getByRole('dialog', { name: 'Loading customer editor' })).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Delete Ada Example' }));
    const deleteDialog = await screen.findByRole('dialog', { name: 'Delete Ada Example?' });
    expect(deleteDialog).toContainElement(document.activeElement as HTMLElement);
    expect(screen.queryByRole('dialog', { name: 'Loading customer editor' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });

  it('makes details loading a named, focus-trapped modal and keeps one modal owner', async () => {
    server.use(http.get('/api/v1/customers/11', () => new Promise(() => {})));
    const user = userEvent.setup();
    render(<OrdersCustomersPage />);
    await user.click(await screen.findByRole('button', { name: 'View Ada Example' }));
    const dialog = await screen.findByRole('dialog', { name: 'Loading customer details' });
    expect(within(dialog).getByRole('status', { name: 'Loading customer details' })).toBeInTheDocument();
    await waitFor(() => expect(dialog).toHaveFocus());
    await user.tab({ shift: true });
    expect(dialog).toHaveFocus();
    await user.keyboard('{Escape}{Enter}');
    expect(screen.getByRole('dialog', { name: 'Loading customer details' })).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Edit Ada Example' }));
    expect(await screen.findByRole('dialog', { name: 'Loading customer editor' })).toHaveFocus();
    expect(screen.queryByRole('dialog', { name: 'Loading customer details' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });
});

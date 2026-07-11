import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setAuthToken } from '../../api/client';
import { BusinessProfileSettings } from '../../components/settings/BusinessProfileSettings';
import { server } from '../mocks/server';
import { render } from '../utils';

const registeredAddress = {
  id: 11,
  kind: 'registered' as const,
  label: null,
  additional: null,
  street: 'Example Street 1',
  street_2: null,
  postal_code: '10115',
  city: 'Berlin',
  region: null,
  country_code: 'DE',
  is_default: true,
};

function profile(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    name: 'EU Operations',
    legal_name: 'EU Operations GmbH',
    trading_name: null,
    country_code: 'DE',
    default_currency: 'EUR',
    timezone: 'Europe/Berlin',
    default_locale: 'de',
    billing_mode: 'hybrid',
    is_active: true,
    is_default: true,
    version: 4,
    created_at: '2026-07-01T10:00:00Z',
    updated_at: '2026-07-01T10:00:00Z',
    addresses: [registeredAddress],
    tax_identifiers: [],
    bank_accounts: [],
    ...overrides,
  };
}

function useProfiles(profiles: Record<string, unknown>[]) {
  server.use(http.get('/api/v1/business-profiles/', () => HttpResponse.json(profiles)));
}

function usePermissions(permissions: string[]) {
  setAuthToken('business-profile-test-token');
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json({
      id: 1,
      username: 'profile-user',
      role: 'user',
      is_active: true,
      is_admin: false,
      groups: [],
      permissions,
      created_at: '2026-07-01T10:00:00Z',
    })),
  );
}

describe('BusinessProfileSettings', () => {
  beforeEach(() => {
    setAuthToken(null);
  });

  afterEach(() => {
    setAuthToken(null);
  });

  it('shows loading and an empty setup state', async () => {
    useProfiles([]);
    render(<BusinessProfileSettings />);

    expect(screen.getByText('Loading business profiles...')).toBeInTheDocument();
    expect(await screen.findByText('No business profiles yet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add business profile' })).toBeInTheDocument();
  });

  it('creates a valid profile with a registered address', async () => {
    const user = userEvent.setup();
    let submitted: Record<string, unknown> | undefined;
    useProfiles([]);
    server.use(http.post('/api/v1/business-profiles/', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json(profile({ id: 8, is_default: false }), { status: 201 });
    }));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Add business profile' }));
    await user.type(screen.getByLabelText('Profile name'), 'North America');
    await user.type(screen.getByLabelText('Legal name'), 'North America LLC');
    await user.selectOptions(screen.getByLabelText('Profile country'), 'US');
    await user.type(screen.getByLabelText('Street'), '100 Main Street');
    await user.type(screen.getByLabelText('Postal code'), '10001');
    await user.type(screen.getByLabelText('City'), 'New York');
    await user.selectOptions(screen.getByLabelText('Country'), 'GB');
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    await waitFor(() => expect(submitted).toMatchObject({
      name: 'North America',
      legal_name: 'North America LLC',
      country_code: 'US',
      addresses: [expect.objectContaining({ kind: 'registered', street: '100 Main Street', city: 'New York', country_code: 'GB' })],
    }));
  });

  it('uses a dedicated scroll viewport between the editor header and footer', async () => {
    const user = userEvent.setup();
    useProfiles([]);
    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Add business profile' }));

    const dialog = screen.getByRole('dialog', { name: 'Add business profile' });
    const viewport = within(dialog).getByTestId('business-profile-editor-scroll-viewport');
    const fieldset = viewport.firstElementChild;

    expect(dialog.children[1]).toBe(viewport);
    expect(viewport.previousElementSibling).toBe(dialog.firstElementChild);
    expect(viewport.nextElementSibling).toBe(dialog.lastElementChild);
    expect(viewport).toHaveClass('min-h-0', 'flex-1', 'overflow-y-auto');
    expect(fieldset).toHaveProperty('tagName', 'FIELDSET');
    expect(fieldset).not.toHaveClass('flex-1', 'overflow-y-auto');
  });

  it('edits nested identity and locale data with the current version', async () => {
    const user = userEvent.setup();
    let submitted: Record<string, unknown> | undefined;
    useProfiles([profile({ trading_name: 'EU Print', country_code: 'GB', default_locale: 'en', billing_mode: 'internal' })]);
    server.use(http.put('/api/v1/business-profiles/7', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json(profile({ trading_name: 'EU Print Shop', default_locale: 'de', billing_mode: 'hybrid' }));
    }));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    await user.clear(screen.getByLabelText('Trading name'));
    await user.type(screen.getByLabelText('Trading name'), 'EU Print Shop');
    await user.selectOptions(screen.getByLabelText('Profile country'), 'US');
    await user.selectOptions(screen.getByLabelText('Billing mode'), 'hybrid');
    await user.selectOptions(screen.getByLabelText('Locale'), 'de');
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    await waitFor(() => expect(submitted).toMatchObject({
      version: 4,
      trading_name: 'EU Print Shop',
      country_code: 'US',
      addresses: [expect.objectContaining({ country_code: 'DE' })],
      billing_mode: 'hybrid',
      default_locale: 'de',
    }));
  });

  it('adds and removes repeatable tax IDs and bank accounts', async () => {
    const user = userEvent.setup();
    let submitted: Record<string, unknown> | undefined;
    useProfiles([profile()]);
    server.use(http.put('/api/v1/business-profiles/7', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json(profile());
    }));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    await user.click(screen.getByRole('button', { name: 'Add tax ID' }));
    await user.type(screen.getByLabelText('Tax ID value 1'), 'DE123456789');
    await user.click(screen.getByRole('button', { name: 'Add bank account' }));
    await user.type(screen.getByLabelText('Bank account label 1'), 'Main account');
    await user.type(screen.getByLabelText('Account holder 1'), 'EU Operations GmbH');
    await user.click(screen.getByRole('button', { name: 'Remove tax ID 1' }));
    await user.click(screen.getByRole('button', { name: 'Remove bank account 1' }));
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    await waitFor(() => expect(submitted).toMatchObject({ tax_identifiers: [], bank_accounts: [] }));
  });

  it('submits a newly added bank account with usable identifiers and routing data', async () => {
    const user = userEvent.setup();
    let submitted: Record<string, unknown> | undefined;
    useProfiles([profile({ country_code: 'US', default_currency: 'USD' })]);
    server.use(http.put('/api/v1/business-profiles/7', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json(profile());
    }));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    await user.click(screen.getByRole('button', { name: 'Add bank account' }));
    await user.type(screen.getByLabelText('Bank account label 1'), 'US operating account');
    await user.type(screen.getByLabelText('Account holder 1'), 'EU Operations Inc.');
    await user.type(screen.getByLabelText('Bank name 1'), 'Example Bank');
    await user.selectOptions(screen.getByLabelText('Bank country 1'), 'US');
    await user.selectOptions(screen.getByLabelText('Bank currency 1'), 'USD');
    await user.type(screen.getByLabelText('IBAN 1'), 'GB82WEST12345698765432');
    await user.type(screen.getByLabelText('BIC 1'), 'DABAIE2D');
    await user.type(screen.getByLabelText('Account number 1'), '000123456789');
    await user.type(screen.getByLabelText('Routing number 1'), '021000021');
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    await waitFor(() => expect(submitted).toMatchObject({
      bank_accounts: [{
        label: 'US operating account', account_holder: 'EU Operations Inc.', bank_name: 'Example Bank',
        country_code: 'US', currency: 'USD', iban: 'GB82WEST12345698765432', bic: 'DABAIE2D',
        account_number: '000123456789', routing_number: '021000021',
      }],
    }));
  });

  it('sets a non-default profile as default', async () => {
    const user = userEvent.setup();
    let defaultedId: number | undefined;
    useProfiles([profile(), profile({ id: 8, name: 'North America', legal_name: 'North America LLC', is_default: false })]);
    server.use(http.post('/api/v1/business-profiles/8/default', () => {
      defaultedId = 8;
      return HttpResponse.json(profile({ id: 8, name: 'North America', is_default: true }));
    }));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Set North America as default' }));
    await waitFor(() => expect(defaultedId).toBe(8));
  });

  it('keeps a row-action 409 visible during retry and clears it only after success', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    let resolveRetry!: () => void;
    const retryGate = new Promise<void>((resolve) => { resolveRetry = resolve; });
    useProfiles([profile(), profile({ id: 8, name: 'North America', legal_name: 'North America LLC', is_default: false })]);
    server.use(http.post('/api/v1/business-profiles/8/default', async () => {
      attempts += 1;
      if (attempts === 1) return HttpResponse.json({ detail: 'Default profile changed elsewhere.' }, { status: 409 });
      await retryGate;
      return HttpResponse.json(profile({ id: 8, name: 'North America', is_default: true }));
    }));

    render(<BusinessProfileSettings />);
    const setDefault = await screen.findByRole('button', { name: 'Set North America as default' });
    await user.click(setDefault);
    expect(await screen.findByText('Default profile changed elsewhere.')).toBeInTheDocument();

    await user.click(setDefault);
    await waitFor(() => expect(setDefault).toBeDisabled());
    expect(screen.getByText('Default profile changed elsewhere.')).toBeInTheDocument();
    resolveRetry();
    await waitFor(() => expect(screen.queryByText('Default profile changed elsewhere.')).not.toBeInTheDocument());
  });

  it('dismisses a persistent row-action 409 explicitly', async () => {
    const user = userEvent.setup();
    useProfiles([profile(), profile({ id: 8, name: 'North America', legal_name: 'North America LLC', is_default: false })]);
    server.use(http.post('/api/v1/business-profiles/8/default', () =>
      HttpResponse.json({ detail: 'Default profile changed elsewhere.' }, { status: 409 }),
    ));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Set North America as default' }));
    expect(await screen.findByText('Default profile changed elsewhere.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByText('Default profile changed elsewhere.')).not.toBeInTheDocument();
  });

  it('does not query and shows permission denied without order settings read access', async () => {
    let requests = 0;
    usePermissions([]);
    server.use(http.get('/api/v1/business-profiles/', () => {
      requests += 1;
      return HttpResponse.json([]);
    }));

    render(<BusinessProfileSettings />);
    expect(await screen.findByText('You do not have permission to view business profiles.')).toBeInTheDocument();
    expect(requests).toBe(0);
  });

  it('keeps profile data read-only without order settings manage access', async () => {
    usePermissions(['order_settings:read']);
    useProfiles([profile()]);

    render(<BusinessProfileSettings />);
    expect(await screen.findByText('EU Operations')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add business profile' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit EU Operations' })).not.toBeInTheDocument();
  });

  it('keeps unsaved input visible when an edit conflicts', async () => {
    const user = userEvent.setup();
    useProfiles([profile()]);
    server.use(http.put('/api/v1/business-profiles/7', () =>
      HttpResponse.json({ detail: 'This profile was changed by another user.' }, { status: 409 }),
    ));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    await user.clear(screen.getByLabelText('Legal name'));
    await user.type(screen.getByLabelText('Legal name'), 'Unsaved EU Operations GmbH');
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    expect(await screen.findByText('This profile was changed by another user.')).toBeInTheDocument();
    expect(screen.getByLabelText('Legal name')).toHaveValue('Unsaved EU Operations GmbH');
  });

  it('maps a top-level 422 problem detail next to its field', async () => {
    const user = userEvent.setup();
    useProfiles([profile()]);
    server.use(http.put('/api/v1/business-profiles/7', () => HttpResponse.json({
      detail: [{ type: 'string_too_short', loc: ['body', 'legal_name'], msg: 'Legal name is required', input: '' }],
    }, { status: 422 })));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    const legalName = screen.getByLabelText('Legal name');
    expect(await screen.findByText('Legal name is required')).toBeInTheDocument();
    expect(legalName.parentElement).toHaveTextContent('Legal name is required');
  });

  it('maps a nested 422 problem detail next to the matching bank field', async () => {
    const user = userEvent.setup();
    useProfiles([profile({ bank_accounts: [{
      id: 21, label: 'Main', account_holder: 'EU Operations GmbH', bank_name: null, country_code: 'DE',
      currency: 'EUR', iban: 'INVALID', bic: null, account_number: null, routing_number: null, is_default: true,
    }] })]);
    server.use(http.put('/api/v1/business-profiles/7', () => HttpResponse.json({
      detail: [{ type: 'value_error', loc: ['body', 'bank_accounts', 0, 'iban'], msg: 'IBAN format is invalid', input: 'INVALID' }],
    }, { status: 422 })));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    const iban = screen.getByLabelText('IBAN 1');
    expect(await screen.findByText('IBAN format is invalid')).toBeInTheDocument();
    expect(iban.parentElement).toHaveTextContent('IBAN format is invalid');
  });

  it('shows an unmapped 422 location in the top-level validation fallback', async () => {
    const user = userEvent.setup();
    useProfiles([profile({ tax_identifiers: [{
      id: 31, kind: 'vat', value: 'DE123456789', country_code: 'DE', is_primary: true,
      valid_from: null, valid_until: null,
    }] })]);
    server.use(http.put('/api/v1/business-profiles/7', () => HttpResponse.json({
      detail: [{ type: 'date_from_datetime_parsing', loc: ['body', 'tax_identifiers', 0, 'valid_from'], msg: 'Valid-from date is invalid', input: 'bad-date' }],
    }, { status: 422 })));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Valid-from date is invalid');
  });

  it('submits repeatable default and primary checkbox state while enforcing one selection', async () => {
    const user = userEvent.setup();
    let submitted: Record<string, unknown> | undefined;
    useProfiles([profile({
      addresses: [
        registeredAddress,
        { ...registeredAddress, id: 12, label: 'Branch', street: 'Second Street 2', is_default: false },
      ],
      tax_identifiers: [
        { id: 31, kind: 'vat', value: 'DE111111111', country_code: 'DE', is_primary: true, valid_from: null, valid_until: null },
        { id: 32, kind: 'tax', value: 'DE222222222', country_code: 'DE', is_primary: false, valid_from: null, valid_until: null },
      ],
      bank_accounts: [
        { id: 41, label: 'Primary', account_holder: 'EU Operations GmbH', bank_name: null, country_code: 'DE', currency: 'EUR', iban: 'DE111', bic: null, account_number: null, routing_number: null, is_default: true },
        { id: 42, label: 'Secondary', account_holder: 'EU Operations GmbH', bank_name: null, country_code: 'DE', currency: 'EUR', iban: 'DE222', bic: null, account_number: null, routing_number: null, is_default: false },
      ],
    })]);
    server.use(http.put('/api/v1/business-profiles/7', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json(profile());
    }));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    expect(screen.getByRole('checkbox', { name: 'Default address 1' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Primary tax ID 1' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Default bank account 1' })).toBeChecked();

    await user.click(screen.getByRole('checkbox', { name: 'Default address 2' }));
    await user.click(screen.getByRole('checkbox', { name: 'Primary tax ID 2' }));
    await user.click(screen.getByRole('checkbox', { name: 'Default bank account 2' }));
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    await waitFor(() => expect(submitted).toMatchObject({
      addresses: [{ is_default: false }, { is_default: true }],
      tax_identifiers: [{ is_primary: true }, { is_primary: true }],
      bank_accounts: [{ is_default: false }, { is_default: true }],
    }));
  });

  it('replaces a primary tax ID only within the same kind', async () => {
    const user = userEvent.setup();
    let submitted: Record<string, unknown> | undefined;
    useProfiles([profile({ tax_identifiers: [
      { id: 31, kind: 'vat', value: 'DE111111111', country_code: 'DE', is_primary: true, valid_from: null, valid_until: null },
      { id: 32, kind: 'tax', value: 'DE222222222', country_code: 'DE', is_primary: true, valid_from: null, valid_until: null },
      { id: 33, kind: 'vat', value: 'DE333333333', country_code: 'DE', is_primary: false, valid_from: null, valid_until: null },
    ] })]);
    server.use(http.put('/api/v1/business-profiles/7', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json(profile());
    }));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    await user.click(screen.getByRole('checkbox', { name: 'Primary tax ID 3' }));
    await user.click(screen.getByRole('button', { name: 'Save business profile' }));

    await waitFor(() => expect(submitted).toMatchObject({
      tax_identifiers: [
        { kind: 'vat', is_primary: false },
        { kind: 'tax', is_primary: true },
        { kind: 'vat', is_primary: true },
      ],
    }));
  });

  it('does not allow removing the final registered address', async () => {
    const user = userEvent.setup();
    useProfiles([profile({ addresses: [
      registeredAddress,
      { ...registeredAddress, id: 12, kind: 'billing', label: 'Billing', is_default: false },
    ] })]);

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));

    expect(screen.queryByRole('button', { name: 'Remove address 1' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove address 2' })).toBeInTheDocument();
  });

  it('locks every draft control and Escape while submission is pending', async () => {
    const user = userEvent.setup();
    let resolveUpdate!: () => void;
    const updateGate = new Promise<void>((resolve) => { resolveUpdate = resolve; });
    useProfiles([profile({
      addresses: [registeredAddress, { ...registeredAddress, id: 12, kind: 'billing', is_default: false }],
      tax_identifiers: [{ id: 31, kind: 'vat', value: 'DE123', country_code: 'DE', is_primary: true, valid_from: null, valid_until: null }],
      bank_accounts: [{ id: 41, label: 'Main', account_holder: 'EU Operations GmbH', bank_name: null, country_code: 'DE', currency: 'EUR', iban: 'DE111', bic: null, account_number: null, routing_number: null, is_default: true }],
    })]);
    server.use(http.put('/api/v1/business-profiles/7', async () => {
      await updateGate;
      return HttpResponse.json(profile());
    }));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));
    const dialog = screen.getByRole('dialog');
    const name = within(dialog).getByLabelText('Profile name');
    await user.click(within(dialog).getByRole('button', { name: 'Save business profile' }));
    await waitFor(() => expect(name).toBeDisabled());

    expect(within(dialog).getByLabelText('Profile country')).toBeDisabled();
    expect(within(dialog).getByRole('checkbox', { name: 'Default address 1' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Add address' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Remove address 2' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Add tax ID' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Remove tax ID 1' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Add bank account' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Remove bank account 1' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled();

    await user.type(name, ' changed');
    expect(name).toHaveValue('EU Operations');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    resolveUpdate();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('closes an idle editor on Escape', async () => {
    const user = userEvent.setup();
    useProfiles([profile()]);
    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Edit EU Operations' }));

    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('keeps a failed action error through unrelated success and clears it on matching success', async () => {
    const user = userEvent.setup();
    let defaultAttempts = 0;
    let releaseDeactivate!: () => void;
    const deactivateGate = new Promise<void>((resolve) => { releaseDeactivate = resolve; });
    useProfiles([profile(), profile({ id: 8, name: 'North America', legal_name: 'North America LLC', is_default: false })]);
    server.use(
      http.post('/api/v1/business-profiles/8/default', () => {
        defaultAttempts += 1;
        return defaultAttempts === 1
          ? HttpResponse.json({ detail: 'Default action failed.' }, { status: 409 })
          : HttpResponse.json(profile({ id: 8, name: 'North America', is_default: true }));
      }),
      http.put('/api/v1/business-profiles/7', async () => {
        await deactivateGate;
        return HttpResponse.json(profile({ is_active: false }));
      }),
    );

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Set North America as default' }));
    expect(await screen.findByText('Default action failed.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Deactivate EU Operations' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Deactivate EU Operations' })).toBeDisabled());
    expect(screen.getByText('Default action failed.')).toBeInTheDocument();

    releaseDeactivate();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Deactivate EU Operations' })).toBeEnabled());
    expect(screen.getByText('Default action failed.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Set North America as default' }));
    await waitFor(() => expect(screen.queryByText('Default action failed.')).not.toBeInTheDocument());
  });

  it('invalidates both profile-list variants with exact query matching', async () => {
    const user = userEvent.setup();
    const invalidate = vi.spyOn(QueryClient.prototype, 'invalidateQueries');
    useProfiles([profile(), profile({ id: 8, name: 'North America', legal_name: 'North America LLC', is_default: false })]);
    server.use(http.post('/api/v1/business-profiles/8/default', () =>
      HttpResponse.json(profile({ id: 8, name: 'North America', is_default: true })),
    ));

    render(<BusinessProfileSettings />);
    await user.click(await screen.findByRole('button', { name: 'Set North America as default' }));

    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['business-profiles', false], exact: true });
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['business-profiles', true], exact: true });
    });
    invalidate.mockRestore();
  });

  it('shows server detail for a failed profile list query', async () => {
    server.use(http.get('/api/v1/business-profiles/', () =>
      HttpResponse.json({ detail: 'Profile database unavailable.' }, { status: 503 }),
    ));

    render(<BusinessProfileSettings />);
    expect(await screen.findByText('Profile database unavailable.')).toBeInTheDocument();
  });

  it('keeps list-query detail visible during a pending retry and clears it after success', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    let resolveRetry!: () => void;
    const retryGate = new Promise<void>((resolve) => { resolveRetry = resolve; });
    server.use(http.get('/api/v1/business-profiles/', async () => {
      attempts += 1;
      if (attempts === 1) return HttpResponse.json({ detail: 'Profile database unavailable.' }, { status: 503 });
      await retryGate;
      return HttpResponse.json([]);
    }));

    render(<BusinessProfileSettings />);
    expect(await screen.findByText('Profile database unavailable.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(screen.getByText('Profile database unavailable.')).toBeInTheDocument();
    resolveRetry();
    expect(await screen.findByText('No business profiles yet.')).toBeInTheDocument();
    expect(screen.queryByText('Profile database unavailable.')).not.toBeInTheDocument();
  });

  it('shows inactive profiles only after the inactive toggle is enabled', async () => {
    const user = userEvent.setup();
    server.use(http.get('/api/v1/business-profiles/', ({ request }) => {
      const includeInactive = new URL(request.url).searchParams.get('includeInactive') === 'true';
      return HttpResponse.json(includeInactive ? [profile(), profile({ id: 9, name: 'Legacy EU', is_active: false })] : [profile()]);
    }));

    render(<BusinessProfileSettings />);
    expect(await screen.findByText('EU Operations')).toBeInTheDocument();
    expect(screen.queryByText('Legacy EU')).not.toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'Include inactive profiles' }));
    expect(await screen.findByText('Legacy EU')).toBeInTheDocument();
  });

  it('does not offer deletion for the default profile', async () => {
    useProfiles([profile(), profile({ id: 8, name: 'North America', legal_name: 'North America LLC', is_default: false })]);
    render(<BusinessProfileSettings />);

    expect(await screen.findByText('EU Operations')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete EU Operations' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete North America' })).toBeInTheDocument();
  });
});

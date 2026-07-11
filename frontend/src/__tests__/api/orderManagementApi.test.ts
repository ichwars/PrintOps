import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import {
  ApiError,
  api,
  type BusinessProfileAddress,
  type BusinessProfileBankAccount,
  type BusinessProfileCreate,
  type BusinessProfileTaxIdentifier,
  type BusinessProfileUpdate,
  type CustomerAccount,
  type CustomerAddress,
  type CustomerContact,
  type CustomerCreate,
  type CustomerTaxIdentifier,
  type CustomerUpdate,
} from '../../api/client';

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('order management API contracts', () => {
  it('serializes valid minimal business-profile create and update payloads', async () => {
    const address: BusinessProfileAddress = {
      kind: 'registered',
      street: 'Example Street 1',
      postal_code: '10115',
      city: 'Berlin',
      country_code: 'DE',
    };
    const taxIdentifier: BusinessProfileTaxIdentifier = { kind: 'vat', value: 'DE123' };
    const bankAccount: BusinessProfileBankAccount = {
      label: 'Main',
      account_holder: 'Example GmbH',
      currency: 'EUR',
      iban: 'DE02120300000000202051',
    };
    const createPayload: BusinessProfileCreate = {
      name: 'Example',
      legal_name: 'Example GmbH',
      country_code: 'DE',
      default_currency: 'EUR',
      addresses: [address],
    };
    const updatePayload: BusinessProfileUpdate = { ...createPayload, version: 1 };
    const bodies: unknown[] = [];

    server.use(
      http.post('/api/v1/business-profiles/', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({});
      }),
      http.put('/api/v1/business-profiles/9', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({});
      }),
    );

    await api.createBusinessProfile(createPayload);
    await api.updateBusinessProfile(9, updatePayload);

    expect(taxIdentifier).toEqual({ kind: 'vat', value: 'DE123' });
    expect(bankAccount).toEqual({
      label: 'Main',
      account_holder: 'Example GmbH',
      currency: 'EUR',
      iban: 'DE02120300000000202051',
    });
    expect(bodies).toEqual([createPayload, updatePayload]);
  });

  it('serializes valid minimal customer create and update payloads', async () => {
    const account: CustomerAccount = { business_profile_id: 7, preferred_currency: 'EUR' };
    const contact: CustomerContact = {};
    const address: CustomerAddress = {
      kind: 'billing',
      street: 'Customer Street 2',
      postal_code: '10117',
      city: 'Berlin',
      country_code: 'DE',
    };
    const taxIdentifier: CustomerTaxIdentifier = { kind: 'vat', value: 'DE456' };
    const createPayload: CustomerCreate = {
      kind: 'company',
      display_name: 'Customer GmbH',
      company_name: 'Customer GmbH',
      accounts: [account],
    };
    const updatePayload: CustomerUpdate = { ...createPayload, version: 2 };
    const bodies: unknown[] = [];

    server.use(
      http.post('/api/v1/customers/', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({});
      }),
      http.put('/api/v1/customers/12', async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({});
      }),
    );

    await api.createCustomer(createPayload);
    await api.updateCustomer(12, updatePayload);

    expect(contact).toEqual({});
    expect(address).toEqual({
      kind: 'billing',
      street: 'Customer Street 2',
      postal_code: '10117',
      city: 'Berlin',
      country_code: 'DE',
    });
    expect(taxIdentifier).toEqual({ kind: 'vat', value: 'DE456' });
    expect(bodies).toEqual([createPayload, updatePayload]);
  });

  it('serializes customer filters without blank values and preserves offset zero', async () => {
    let requestUrl: URL | null = null;
    server.use(
      http.get('/api/v1/customers/', ({ request }) => {
        requestUrl = new URL(request.url);
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      }),
    );

    await api.getCustomers({
      businessProfileId: 7,
      search: '  ',
      status: undefined,
      kind: undefined,
      limit: 50,
      offset: 0,
    });

    expect(requestUrl).not.toBeNull();
    expect(requestUrl!.searchParams.get('business_profile_id')).toBe('7');
    expect(requestUrl!.searchParams.get('limit')).toBe('50');
    expect(requestUrl!.searchParams.get('offset')).toBe('0');
    expect(requestUrl!.searchParams.has('search')).toBe(false);
    expect(requestUrl!.searchParams.has('status')).toBe(false);
    expect(requestUrl!.searchParams.has('kind')).toBe(false);
  });

  it('requests inactive profiles only when explicitly asked', async () => {
    let includeInactive: string | null | undefined;
    server.use(
      http.get('/api/v1/business-profiles/', ({ request }) => {
        includeInactive = new URL(request.url).searchParams.get('includeInactive');
        return HttpResponse.json([]);
      }),
    );

    await api.getBusinessProfiles(true);

    expect(includeInactive).toBe('true');
  });

  it('retains only sanitized validation metadata for 422 responses', async () => {
    server.use(http.get('/api/v1/business-profiles/', () => HttpResponse.json({
      detail: [{
        type: 'value_error', loc: ['body', 'legal_name'], msg: 'Value error, Legal name is invalid',
        input: 'secret legal name', ctx: { error: 'sensitive validator context' },
      }],
    }, { status: 422 })));

    const error = await api.getBusinessProfiles().catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe('Legal name is invalid');
    expect((error as ApiError).validationErrors).toEqual([
      { type: 'value_error', loc: ['body', 'legal_name'], msg: 'Legal name is invalid' },
    ]);
    expect(JSON.stringify((error as ApiError).validationErrors)).not.toContain('secret legal name');
    expect(JSON.stringify((error as ApiError).validationErrors)).not.toContain('sensitive validator context');
  });

  it('does not expose raw validation detail when 422 issue messages are empty', async () => {
    const bankSecret = 'DE89370400440532013000';
    const taxSecret = 'DE123456789';
    server.use(http.get('/api/v1/business-profiles/', () => HttpResponse.json({
      detail: [{
        type: 'value_error', loc: ['body', 'bank_accounts', 0, 'iban'], msg: '',
        input: bankSecret, ctx: { tax_identifier: taxSecret },
      }],
    }, { status: 422 })));

    const error = await api.getBusinessProfiles().catch((caught) => caught);
    const apiError = error as ApiError;

    expect(apiError).toBeInstanceOf(ApiError);
    expect(apiError.message).toBe('Validation failed.');
    expect(JSON.stringify(apiError.validationErrors)).not.toContain(bankSecret);
    expect(JSON.stringify(apiError.validationErrors)).not.toContain(taxSecret);
    expect(apiError.message).not.toContain(bankSecret);
    expect(apiError.message).not.toContain(taxSecret);
  });

  it('does not treat array detail on a non-422 response as validation metadata', async () => {
    server.use(http.get('/api/v1/business-profiles/', () => HttpResponse.json({
      detail: [{ type: 'conflict', loc: ['body'], msg: 'Profile conflict', input: 'secret' }],
    }, { status: 409 })));

    const error = await api.getBusinessProfiles().catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe('Profile conflict');
    expect((error as ApiError).validationErrors).toBeNull();
  });
});

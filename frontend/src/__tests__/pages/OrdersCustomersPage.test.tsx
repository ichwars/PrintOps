import { beforeEach, describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { OrdersCustomersPage } from '../../pages/OrdersCustomersPage';

describe('OrdersCustomersPage', () => {
  beforeEach(() => {
    server.use(
      http.get('/api/v1/business-profiles/options', () =>
        HttpResponse.json([
          {
            id: 7,
            name: 'Berlin Print Works',
            country_code: 'DE',
            default_currency: 'EUR',
            timezone: 'Europe/Berlin',
            default_locale: 'de',
            billing_mode: 'hybrid',
            is_default: true,
            is_active: true,
          },
        ]),
      ),
      http.get('/api/v1/customers/', ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get('business_profile_id') !== '7') {
          return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
        }
        return HttpResponse.json({
          items: [
            {
              id: 11,
              business_profile_id: 7,
              account_number: 'C-0011',
              preferred_currency: 'EUR',
              payment_term_days: 14,
              delivery_terms: null,
              discount_percent: '2.50',
              account_is_active: true,
              display_name: 'Ada Example',
              company_name: null,
              first_name: 'Ada',
              last_name: 'Example',
              kind: 'person',
              status: 'active',
              preferred_locale: 'de',
              primary_contact_name: null,
              primary_contact_email: null,
              billing_city: 'Berlin',
              billing_country_code: 'DE',
              tags: [],
              version: 1,
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        });
      }),
    );
  });

  it('loads the default business profile and its real customer list', async () => {
    render(<OrdersCustomersPage />);

    expect(await screen.findByText('Ada Example')).toBeInTheDocument();
    expect(screen.getByText('Berlin Print Works')).toBeInTheDocument();
    expect(screen.getByText('2.50%')).toBeInTheDocument();
  });

  it('shows no-profile state without starting or showing the customer query', async () => {
    let customerRequests = 0;
    server.use(
      http.get('/api/v1/business-profiles/options', () => HttpResponse.json([])),
      http.get('/api/v1/customers/', () => {
        customerRequests += 1;
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      }),
    );

    render(<OrdersCustomersPage />);

    expect(await screen.findByText('No active business profile is available.')).toBeInTheDocument();
    expect(screen.queryByText('Loading customers...')).not.toBeInTheDocument();
    expect(screen.queryByText('Unable to load customers.')).not.toBeInTheDocument();
    expect(customerRequests).toBe(0);
  });

  it('shows profile error without starting or showing the customer query', async () => {
    let customerRequests = 0;
    server.use(
      http.get('/api/v1/business-profiles/options', () =>
        HttpResponse.json({ detail: 'profile failure' }, { status: 500 }),
      ),
      http.get('/api/v1/customers/', () => {
        customerRequests += 1;
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      }),
    );

    render(<OrdersCustomersPage />);

    expect(await screen.findByText('Unable to load business profiles.')).toBeInTheDocument();
    expect(screen.queryByText('Loading customers...')).not.toBeInTheDocument();
    expect(screen.queryByText('Unable to load customers.')).not.toBeInTheDocument();
    expect(screen.queryByText('No active business profile is available.')).not.toBeInTheDocument();
    expect(customerRequests).toBe(0);
  });
});

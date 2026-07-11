import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import App from '../App';
import { server } from './mocks/server';

describe('App order customer routing', () => {
  it('renders the data-backed customer page at /orders/customers', async () => {
    let optionsRequests = 0;
    let customerRequests = 0;
    window.history.replaceState({}, '', '/orders/customers');

    server.use(
      http.get('/api/v1/auth/status', () =>
        HttpResponse.json({ auth_enabled: false, requires_setup: false }),
      ),
      http.get('/api/v1/business-profiles/options', () => {
        optionsRequests += 1;
        return HttpResponse.json([
          {
            id: 7,
            name: 'Route Profile',
            country_code: 'DE',
            default_currency: 'EUR',
            timezone: 'Europe/Berlin',
            default_locale: 'en',
            billing_mode: 'hybrid',
            is_default: true,
            is_active: true,
          },
        ]);
      }),
      http.get('/api/v1/customers/', () => {
        customerRequests += 1;
        return HttpResponse.json({
          items: [
            {
              id: 21,
              business_profile_id: 7,
              account_number: 'C-0021',
              preferred_currency: 'EUR',
              payment_term_days: 14,
              delivery_terms: null,
              discount_percent: '0.00',
              account_is_active: true,
              display_name: 'Route Customer',
              company_name: 'Route Customer GmbH',
              first_name: null,
              last_name: null,
              kind: 'company',
              status: 'active',
              preferred_locale: 'en',
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

    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Customers' })).toBeInTheDocument();
    expect(await screen.findByText('Route Customer')).toBeInTheDocument();
    expect(optionsRequests).toBe(1);
    expect(customerRequests).toBe(1);
  });
});

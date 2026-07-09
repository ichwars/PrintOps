import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Calculator, ClipboardList, FileText, Receipt, Users } from 'lucide-react';
import { Card, CardContent, CardHeader } from '../components/Card';

type OrderSectionId = 'overview' | 'customers' | 'calculation' | 'offers' | 'invoices';

const COPY = {
  en: {
    title: 'Orders',
    subtitle: 'Customer work, calculations, offers, and invoices in one workflow.',
    empty: 'No records yet',
    foundation: 'Foundation',
    sections: {
      overview: 'Overview',
      customers: 'Customers',
      calculation: 'Calculation',
      offers: 'Offers',
      invoices: 'Invoices',
    },
    page: {
      overview: {
        title: 'Order overview',
        subtitle: 'Pipeline, deadlines, reservations, and open commercial work.',
        columns: ['Area', 'Status', 'Next step'],
      },
      customers: {
        title: 'Customers',
        subtitle: 'Customer master data, contacts, addresses, and terms.',
        columns: ['Customer', 'Contact', 'Status'],
      },
      calculation: {
        title: 'Calculation',
        subtitle: 'Material, machine time, margin, and project-based pricing.',
        columns: ['Project', 'Cost basis', 'Result'],
      },
      offers: {
        title: 'Offers',
        subtitle: 'Draft, sent, accepted, and rejected offers.',
        columns: ['Offer', 'Customer', 'Status'],
      },
      invoices: {
        title: 'Invoices',
        subtitle: 'Invoices, due dates, payment status, and invoice history.',
        columns: ['Invoice', 'Customer', 'Due date'],
      },
    },
  },
  de: {
    title: 'Aufträge',
    subtitle: 'Kundenarbeit, Kalkulationen, Angebote und Rechnungen in einem Ablauf.',
    empty: 'Noch keine Datensätze',
    foundation: 'Basis',
    sections: {
      overview: 'Übersicht',
      customers: 'Kunden',
      calculation: 'Kalkulation',
      offers: 'Angebote',
      invoices: 'Rechnungen',
    },
    page: {
      overview: {
        title: 'Auftragsübersicht',
        subtitle: 'Pipeline, Termine, Reservierungen und offene kaufmännische Arbeit.',
        columns: ['Bereich', 'Status', 'Nächster Schritt'],
      },
      customers: {
        title: 'Kunden',
        subtitle: 'Kundenstammdaten, Kontakte, Adressen und Konditionen.',
        columns: ['Kunde', 'Kontakt', 'Status'],
      },
      calculation: {
        title: 'Kalkulation',
        subtitle: 'Material, Maschinenzeit, Marge und projektbezogene Preise.',
        columns: ['Projekt', 'Kostenbasis', 'Ergebnis'],
      },
      offers: {
        title: 'Angebote',
        subtitle: 'Entwürfe, versendete, angenommene und abgelehnte Angebote.',
        columns: ['Angebot', 'Kunde', 'Status'],
      },
      invoices: {
        title: 'Rechnungen',
        subtitle: 'Rechnungen, Fälligkeiten, Zahlungsstatus und Verlauf.',
        columns: ['Rechnung', 'Kunde', 'Fälligkeit'],
      },
    },
  },
} as const;

function getSection(pathname: string): OrderSectionId {
  if (pathname.endsWith('/customers')) return 'customers';
  if (pathname.endsWith('/calculation')) return 'calculation';
  if (pathname.endsWith('/offers')) return 'offers';
  if (pathname.endsWith('/invoices')) return 'invoices';
  return 'overview';
}

export function OrdersPage() {
  const { i18n } = useTranslation();
  const location = useLocation();
  const activeSection = getSection(location.pathname);
  const copy = i18n.resolvedLanguage?.startsWith('de') ? COPY.de : COPY.en;
  const columns = copy.page[activeSection].columns;

  const sections = [
    { id: 'overview' as const, to: '/orders', icon: ClipboardList },
    { id: 'customers' as const, to: '/orders/customers', icon: Users },
    { id: 'calculation' as const, to: '/orders/calculation', icon: Calculator },
    { id: 'offers' as const, to: '/orders/offers', icon: FileText },
    { id: 'invoices' as const, to: '/orders/invoices', icon: Receipt },
  ];

  const active = sections.find((section) => section.id === activeSection) ?? sections[0];
  const ActiveIcon = active.icon;

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <ClipboardList className="w-7 h-7 text-bambu-green" />
          {copy.title}
        </h1>
        <p className="text-bambu-gray mt-1">{copy.subtitle}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {sections.map(({ id, to, icon: Icon }) => (
          <Link
            key={id}
            to={to}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeSection === id
                ? 'bg-bambu-green text-white'
                : 'bg-bambu-dark-secondary text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white'
            }`}
          >
            <Icon className="w-4 h-4" />
            {copy.sections[id]}
          </Link>
        ))}
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <ActiveIcon className="w-5 h-5 text-bambu-green" />
              <div>
                <h2 className="text-lg font-semibold text-white">
                  {copy.page[activeSection].title}
                </h2>
                <p className="text-sm text-bambu-gray">
                  {copy.page[activeSection].subtitle}
                </p>
              </div>
            </div>
            <span className="text-xs px-2 py-1 rounded-full bg-bambu-dark-tertiary text-bambu-gray">
              {copy.foundation}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-lg border border-bambu-dark-tertiary">
            <table className="w-full text-sm">
              <thead className="bg-bambu-dark">
                <tr>
                  {columns.map((column) => (
                    <th key={column} className="px-4 py-3 text-left font-medium text-bambu-gray">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td colSpan={3} className="px-4 py-10 text-center text-bambu-gray">
                    {copy.empty}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

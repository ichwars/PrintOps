import { useEffect, useState } from 'react';
import { ClipboardList } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ordersApi, type CustomerOrder } from '../api/offers';

export function OrdersOverviewPage() {
  const { i18n } = useTranslation();
  const de = i18n.resolvedLanguage?.startsWith('de') ?? false;
  const locale = de ? 'de-DE' : 'en-US';
  const [orders, setOrders] = useState<CustomerOrder[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void ordersApi.list().then(setOrders).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason))); }, []);
  return <div className="space-y-5 p-4 md:p-8"><div><h1 className="flex items-center gap-3 text-2xl font-bold text-white"><ClipboardList className="h-7 w-7 text-bambu-green" />{de ? 'Aufträge' : 'Orders'}</h1><p className="mt-1 text-bambu-gray">{de ? 'Angenommene Angebote, Projekte und reserviertes Material.' : 'Accepted offers, projects, and reserved stock.'}</p></div>{error && <div className="rounded-lg border border-red-500/40 p-3 text-red-300">{error}</div>}<div className="overflow-hidden rounded-xl border border-bambu-dark-tertiary"><table className="w-full text-sm"><thead className="bg-bambu-dark"><tr>{[de ? 'Auftrag' : 'Order', 'Status', de ? 'Projekt' : 'Project', de ? 'Reservierungen' : 'Reservations', de ? 'Erstellt' : 'Created', ''].map((item) => <th key={item} className="px-4 py-3 text-left text-bambu-gray">{item}</th>)}</tr></thead><tbody className="divide-y divide-bambu-dark-tertiary">{orders.length === 0 ? <tr><td colSpan={6} className="p-10 text-center text-bambu-gray">{de ? 'Noch keine Aufträge.' : 'No orders yet.'}</td></tr> : orders.map((order) => <tr key={order.id} className="bg-bambu-dark-secondary"><td className="px-4 py-3 font-medium text-white">{order.number}</td><td className="px-4 py-3 text-bambu-gray">{order.status}</td><td className="px-4 py-3"><Link to={`/projects/${order.project_id}`} className="text-bambu-green">#{order.project_id}</Link></td><td className="px-4 py-3 text-bambu-gray">{order.reservations.filter((item) => item.status === 'active').length} / {order.reservations.length}</td><td className="px-4 py-3 text-bambu-gray">{new Date(order.created_at).toLocaleString(locale)}</td><td className="px-4 py-3 text-right"><Link to={`/orders/${order.id}`} className="rounded bg-bambu-green/10 px-3 py-2 text-bambu-green">{de ? 'Öffnen' : 'Open'}</Link></td></tr>)}</tbody></table></div></div>;
}

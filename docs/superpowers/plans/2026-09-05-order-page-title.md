# Dynamic Order Page Title Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the main heading, subtitle, and icon on `OrdersPage` describe the active order subsection.

**Architecture:** Keep `getSection()` as the single route-to-section mapping. Reuse the existing localized `copy.page[activeSection]` object and `ActiveIcon` in both the page heading and card heading, without adding state, routes, or translations.

**Tech Stack:** React 19, React Router, TanStack Query, Vitest, Testing Library, TypeScript

## Global Constraints

- Work exclusively inline; do not use subagents.
- Keep navigation, card content, filters, and data fetching unchanged.
- Support both the German and English copy already defined in `OrdersPage`.

---

### Task 1: Bind the page heading to the active order section

**Files:**
- Create: `frontend/src/__tests__/pages/OrdersPage.test.tsx`
- Modify: `frontend/src/pages/OrdersPage.tsx:410-420`

**Interfaces:**
- Consumes: `getSection(pathname): OrderSectionId`, `copy.page[activeSection]`, and `ActiveIcon` from `OrdersPage`.
- Produces: An `<h1>` and adjacent subtitle whose content follows the active route; no new exported interface.

- [ ] **Step 1: Write the failing route-heading test**

Create `frontend/src/__tests__/pages/OrdersPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { documentManagementApi } from '../../api/documentManagement';
import i18n from '../../i18n';
import { OrdersPage } from '../../pages/OrdersPage';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission: () => false }),
}));

function mount(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <OrdersPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
  vi.spyOn(documentManagementApi, 'listDocuments').mockResolvedValue([]);
});

describe('Orders page heading', () => {
it.each([
  ['/orders', 'Order overview', 'Pipeline, deadlines, reservations, and open commercial work.'],
  ['/orders/calculation', 'Calculation', 'Material, machine time, margin, and project-based pricing.'],
  ['/orders/offers', 'Offers', 'Draft, sent, accepted, and rejected offers.'],
  ['/orders/invoices', 'Invoices', 'Invoices, due dates, payment status, and invoice history.'],
])('shows the active section in the page heading for %s', (path, title, subtitle) => {
  mount(path);
  const heading = screen.getByRole('heading', { level: 1, name: title });
  expect(heading.nextElementSibling).toHaveTextContent(subtitle);
});
});
```

- [ ] **Step 2: Run the test and verify the regression is exposed**

Run: `npm.cmd run test -- --run src/__tests__/pages/OrdersPage.test.tsx`

Expected: The calculation, offers, and invoices cases fail because the level-one heading still reads `Orders`.

- [ ] **Step 3: Implement the minimal heading change**

Replace the fixed icon and module copy in the top heading with the active values:

```tsx
<ActiveIcon className="w-7 h-7 text-bambu-green" />
{copy.page[activeSection].title}
...
{copy.page[activeSection].subtitle}
```

- [ ] **Step 4: Run focused verification**

Run: `npm.cmd run test -- --run src/__tests__/pages/OrdersPage.test.tsx`

Expected: All four route cases pass.

Run: `npm.cmd run lint -- src/pages/OrdersPage.tsx src/__tests__/pages/OrdersPage.test.tsx`

Expected: Exit code 0 with no lint errors.

Run: `npx.cmd tsc -b`

Expected: Exit code 0 with no TypeScript errors.

- [ ] **Step 5: Verify the visible invoice page and commit**

Open `/orders/invoices`, confirm the level-one heading reads `Rechnungen`, and confirm the matching description and receipt icon are visible. Then run:

```powershell
git add -- frontend/src/pages/OrdersPage.tsx frontend/src/__tests__/pages/OrdersPage.test.tsx
git commit -m "fix: match order page title to content"
```

import { afterAll, afterEach, beforeAll, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { historyLibraryMethods } from '../../api/client/history-library';

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

it('sends the selected bulk target with the file IDs', async () => {
  let submitted: unknown;
  server.use(http.post('*/api/v1/library/files/add-to-queue', async ({ request }) => {
    submitted = await request.json();
    return HttpResponse.json({ added: [], errors: [] });
  }));

  await historyLibraryMethods.addLibraryFilesToQueue([11, 12], { target_model: 'C11' });

  expect(submitted).toEqual({ file_ids: [11, 12], target_model: 'C11' });
});

it('preserves the existing file-ID-only request', async () => {
  let submitted: unknown;
  server.use(http.post('*/api/v1/library/files/add-to-queue', async ({ request }) => {
    submitted = await request.json();
    return HttpResponse.json({ added: [], errors: [] });
  }));

  await historyLibraryMethods.addLibraryFilesToQueue([11]);

  expect(submitted).toEqual({ file_ids: [11] });
});

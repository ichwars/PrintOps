/**
 * Tests for FolderReadmePanel (#1268).
 */

import { describe, it, expect } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { FolderReadmePanel } from '../../components/FolderReadmePanel';
import { server } from '../mocks/server';

async function renderReadme(content: string) {
  server.use(http.get('/api/v1/library/folders/:id/readme', () =>
    HttpResponse.json({ filename: 'README.md', content, truncated: false }),
  ));
  const result = render(<FolderReadmePanel folderId={42} />);
  await screen.findByText('README.md');
  return result;
}

describe('FolderReadmePanel', () => {
  it('preserves GFM tables, task lists, strikethrough and footnotes', async () => {
    const { container } = await renderReadme([
      '| Part | Qty |', '| --- | ---: |', '| Gear | 2 |', '',
      '- [x] Printed', '- [ ] Packed', '', '~~Old revision~~', '',
      'Material note[^1]', '', '[^1]: Use PETG.',
    ].join('\n'));
    expect(screen.getByRole('table')).toHaveTextContent('Gear');
    expect(screen.getByRole('columnheader', { name: 'Qty' })).toBeInTheDocument();
    const tasks = screen.getAllByRole('checkbox');
    expect(tasks[0]).toBeChecked();
    expect(tasks[1]).not.toBeChecked();
    for (const task of tasks) expect(task).toBeDisabled();
    expect(container.querySelector('del')).toHaveTextContent('Old revision');
    expect(container.querySelector('[data-footnotes]')).toHaveTextContent('Use PETG.');
  });

  it('preserves explicit and angle links with URL filtering and opener protection', async () => {
    await renderReadme('[Docs](https://example.com/docs)\n\n<https://example.com>\n\n<print@example.com>');
    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      'https://example.com/docs', 'https://example.com', 'mailto:print@example.com',
    ]);
    for (const link of links) {
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    }
  });

  it('keeps bare URLs and email addresses as readable text', async () => {
    await renderReadme('https://example.com print@example.com');
    expect(screen.getByText('https://example.com print@example.com')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('does not interpret raw HTML or allow executable URL schemes', async () => {
    const { container } = await renderReadme([
      '<script>alert(1)</script>', '', '<img src=x onerror=alert(1)>', '',
      '[Bad](javascript:alert%281%29)', '', '[Data](data:text/html,bad)', '',
      '[Encoded](jav&#x61;script:alert%281%29)', '', '![Bad image](javascript:alert%281%29)',
    ].join('\n'));
    expect(container.querySelector('script, [onerror]')).toBeNull();
    expect(screen.getByText('Bad')).toHaveAttribute('href', '');
    expect(screen.getByText('Data')).toHaveAttribute('href', '');
    expect(screen.getByText('Encoded')).toHaveAttribute('href', '');
    expect(screen.getByAltText('Bad image')).not.toHaveAttribute('src');
  });

  it('preserves ordinary Markdown and can collapse and reopen the panel', async () => {
    const { container } = await renderReadme('# Assembly\n\n> Fit **carefully**.\n\n1. First\n2. Second\n\n```js\nconst qty = 2;\n```');
    expect(container.querySelector('blockquote strong')).toHaveTextContent('carefully');
    expect(container.querySelector('ol')).toHaveTextContent('Second');
    expect(container.querySelector('pre code')).toHaveTextContent('const qty = 2;');
    fireEvent.click(screen.getByRole('button', { name: 'README.md' }));
    expect(screen.queryByRole('heading', { name: 'Assembly' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'README.md' }));
    expect(screen.getByRole('heading', { name: 'Assembly' })).toBeInTheDocument();
  });

  it('renders nothing when the folder has no markdown (404)', async () => {
    server.use(
      http.get('/api/v1/library/folders/:id/readme', () =>
        HttpResponse.json({ detail: 'No markdown' }, { status: 404 }),
      ),
    );
    render(<FolderReadmePanel folderId={1} />);
    // Wait briefly so the query has time to resolve, then confirm no panel
    // chrome leaked into the DOM (the test render util mounts toast/provider
    // wrappers, so we can't assert `container.firstChild === null`).
    await waitFor(() => {
      expect(screen.queryByText('Truncated')).not.toBeInTheDocument();
      expect(document.querySelector('button[type="button"] svg.lucide-file-text')).toBeNull();
    });
  });

  it('renders markdown content and the filename when present', async () => {
    server.use(
      http.get('/api/v1/library/folders/:id/readme', () =>
        HttpResponse.json({
          filename: 'README.md',
          content: '# Robot model\n\nA cute robot.',
          truncated: false,
        }),
      ),
    );
    render(<FolderReadmePanel folderId={42} />);
    expect(await screen.findByText('README.md')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Robot model' })).toBeInTheDocument();
    expect(screen.getByText('A cute robot.')).toBeInTheDocument();
  });

  it('shows a Truncated chip when the API flags the content as clipped', async () => {
    server.use(
      http.get('/api/v1/library/folders/:id/readme', () =>
        HttpResponse.json({
          filename: 'description.md',
          content: 'very long content',
          truncated: true,
        }),
      ),
    );
    render(<FolderReadmePanel folderId={7} />);
    expect(await screen.findByText('Truncated')).toBeInTheDocument();
  });
});

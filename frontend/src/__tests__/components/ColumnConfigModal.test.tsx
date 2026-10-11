import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ColumnConfigModal, type ColumnConfig } from '../../components/ColumnConfigModal';
import i18n from '../../i18n';

const columns: ColumnConfig[] = [
  { id: 'a', label: 'Alpha', visible: true },
  { id: 'b', label: 'Beta', visible: true },
  { id: 'retired', label: 'Retired', visible: true },
];

const draftOrder = () => Array.from(document.querySelectorAll('[draggable="true"] span')).map(element => element.textContent);
const columnRow = (label: string) => screen.getByText(label).closest('[draggable="true"]') as HTMLElement;

beforeEach(async () => { await i18n.changeLanguage('en'); });

describe('ColumnConfigModal draft lifecycle', () => {
  it('refreshes labels and column membership while preserving dirty visibility and order', async () => {
    const onSave = vi.fn();
    const props = { isOpen: true, onClose: vi.fn(), columns, defaultColumns: columns, onSave };
    const view = render(<ColumnConfigModal {...props} />);
    const user = userEvent.setup();
    await user.click(within(columnRow('Beta')).getByTitle('Hide column'));
    await user.click(within(columnRow('Beta')).getByTitle('Move up'));
    const changedColumns: ColumnConfig[] = [
      { id: 'a', label: 'Alfa', visible: true },
      { id: 'b', label: 'Bravo', visible: true },
      { id: 'new', label: 'Gamma', visible: false },
    ];
    view.rerender(<ColumnConfigModal {...props} columns={changedColumns} defaultColumns={changedColumns} />);
    expect(draftOrder()).toEqual(['Bravo', 'Alfa', 'Gamma']);
    expect(within(columnRow('Bravo')).getByTitle('Show column')).toBeInTheDocument();
    expect(within(columnRow('Gamma')).getByTitle('Show column')).toBeInTheDocument();
    expect(screen.queryByText('Retired')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Apply Changes' }));
    expect(onSave).toHaveBeenCalledWith([
      { id: 'b', label: 'Bravo', visible: false },
      { id: 'a', label: 'Alfa', visible: true },
      { id: 'new', label: 'Gamma', visible: false },
    ]);
  });

  it('adopts an updated saved configuration when no local edits exist', async () => {
    const onSave = vi.fn();
    const props = { isOpen: true, onClose: vi.fn(), columns, defaultColumns: columns, onSave };
    const view = render(<ColumnConfigModal {...props} />);
    const incoming = [{ id: 'b', label: 'Beta', visible: false }, { id: 'a', label: 'Alpha', visible: true }];
    view.rerender(<ColumnConfigModal {...props} columns={incoming} />);
    expect(draftOrder()).toEqual(['Beta', 'Alpha']);
    expect(within(columnRow('Beta')).getByTitle('Show column')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Apply Changes' }));
    expect(onSave).toHaveBeenCalledWith(incoming);
  });

  it('discards a cancelled draft and restores the saved configuration on reopening', async () => {
    const onClose = vi.fn();
    const props = { isOpen: true, onClose, columns, defaultColumns: columns, onSave: vi.fn() };
    const view = render(<ColumnConfigModal {...props} />);
    const user = userEvent.setup();
    await user.click(within(columnRow('Beta')).getByTitle('Hide column'));
    await user.click(within(columnRow('Beta')).getByTitle('Move up'));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledOnce();
    view.rerender(<ColumnConfigModal {...props} isOpen={false} />);
    view.rerender(<ColumnConfigModal {...props} />);
    expect(draftOrder()).toEqual(['Alpha', 'Beta', 'Retired']);
    expect(within(columnRow('Beta')).getByTitle('Hide column')).toBeInTheDocument();
  });
});

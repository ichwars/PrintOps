import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { ToastProvider, useToast } from '../../contexts/ToastContext';

function Probe() {
  const { showToast, showPersistentToast } = useToast();
  return <>
    <button onClick={() => showToast('An operation failed. Read the details and retry.', 'error')}>Error</button>
    <button onClick={() => showToast('Inspect the configured printer before continuing.', 'warning')}>Warning</button>
    <button onClick={() => showToast('An operation failed. '.repeat(40), 'error')}>Long error</button>
    <button onClick={() => showToast('Saved', 'success')}>Success</button>
    <button onClick={() => showPersistentToast('persistent', 'Upload still running', 'loading')}>Persistent</button>
  </>;
}

function setup() {
  vi.useFakeTimers();
  render(<ToastProvider><Probe /></ToastProvider>);
}

afterEach(() => vi.useRealTimers());

describe('toast readability', () => {
  it.each(['Error', 'Warning'])('keeps %s readable beyond the previous 3-second window', (type) => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: type }));
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByRole('alert')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps short success notifications brief and persistent notifications until dismissed', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Success' }));
    fireEvent.click(screen.getByRole('button', { name: 'Persistent' }));
    expect(screen.getByText('Saved')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.queryByText('Saved')).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime(60000));
    expect(screen.getByText('Upload still running')).toBeInTheDocument();
  });

  it('gives long errors up to 30 seconds of reading time', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Long error' }));
    act(() => vi.advanceTimersByTime(29999));
    expect(screen.getByRole('alert')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('pauses while hovered, then resumes with reading time after leaving', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Error' }));
    const alert = screen.getByRole('alert');
    act(() => vi.advanceTimersByTime(9000));
    fireEvent.mouseEnter(alert);
    act(() => vi.advanceTimersByTime(30000));
    expect(alert).toBeInTheDocument();
    fireEvent.mouseLeave(alert);
    act(() => vi.advanceTimersByTime(1000));
    expect(alert).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(9000));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('pauses while the dismiss control has keyboard focus and dismisses accessibly', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Warning' }));
    const dismiss = screen.getByRole('button', { name: 'Dismiss' });
    fireEvent.focus(dismiss);
    act(() => vi.advanceTimersByTime(60000));
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.click(dismiss);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('resumes only after both hover and keyboard focus leave the toast', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Warning' }));
    const alert = screen.getByRole('alert');
    const dismiss = screen.getByRole('button', { name: 'Dismiss' });
    fireEvent.mouseEnter(alert);
    fireEvent.focus(dismiss);
    fireEvent.mouseLeave(alert);
    act(() => vi.advanceTimersByTime(30000));
    expect(alert).toBeInTheDocument();
    fireEvent.blur(dismiss, { relatedTarget: screen.getByRole('button', { name: 'Warning' }) });
    act(() => vi.advanceTimersByTime(10000));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

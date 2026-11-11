import { fireEvent, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { QrSpoolScanner } from '../../components/QrSpoolScanner';
import { render } from '../utils';

it('starts the camera on request and releases its stream when stopped', async () => {
  const stop = vi.fn();
  const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] });
  const original = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });
  const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  try {
    render(<QrSpoolScanner onPayload={vi.fn()} />);
    expect(getUserMedia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Start camera' }));
    await waitFor(() => expect(play).toHaveBeenCalled());
    expect(getUserMedia).toHaveBeenCalledWith({ video: { facingMode: { ideal: 'environment' } }, audio: false });
    fireEvent.click(screen.getByRole('button', { name: 'Stop camera' }));
    expect(stop).toHaveBeenCalledTimes(1);
  } finally {
    play.mockRestore();
    if (original) Object.defineProperty(navigator, 'mediaDevices', original);
    else Reflect.deleteProperty(navigator, 'mediaDevices');
  }
});

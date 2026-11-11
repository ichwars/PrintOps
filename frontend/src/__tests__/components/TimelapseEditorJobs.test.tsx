import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { TimelapseEditorModal } from '../../components/TimelapseEditorModal';
import { ExternalCameraUrlField } from '../../components/settings/CameraUrlBuilder';
import { render, selectComboboxOption } from '../utils';
import { server } from '../mocks/server';

const url = '/api/v1/archives/5/timelapse';
const running = { job_id: 'job-1', status: 'running', progress: 0.4, message: null, output_path: null };

beforeEach(() => {
  server.use(
    http.get(`${url}/info`, () => HttpResponse.json({
      duration: 8, width: 32, height: 32, fps: 25, codec: 'h264', file_size: 200,
      has_audio: false, source_version: 'revision-1',
    })),
    http.get(`${url}/thumbnails`, () => HttpResponse.json({ thumbnails: [], timestamps: [] })),
    http.get(`${url}/job`, () => HttpResponse.json(null)),
  );
});

it('starts an edit against the loaded version and cancels the exact background job', async () => {
  const submit = vi.fn();
  const stop = vi.fn();
  const saved = vi.fn();
  server.use(
    http.post(`${url}/process`, async ({ request }) => {
      const body = await request.formData();
      submit(new URL(request.url).searchParams.get('background'), body.get('source_version'), body.get('trim_end'));
      return HttpResponse.json(running, { status: 202 });
    }),
    http.delete(`${url}/job/:id`, ({ params }) => {
      stop(params.id);
      return HttpResponse.json({ ...running, status: 'cancelled' });
    }),
  );
  render(<TimelapseEditorModal archiveId={5} timelapseSrc="/sample.mp4" onClose={vi.fn()} onSave={saved} />);
  const save = await screen.findByRole('button', { name: 'Save' });
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.click(save);
  expect(await screen.findByRole('progressbar')).toHaveAttribute('value', '0.4');
  expect(submit).toHaveBeenCalledWith('true', 'revision-1', '8');
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
  expect(stop).toHaveBeenCalledWith('job-1');
  expect(saved).not.toHaveBeenCalled();
});

it('lets a user select an available USB device while retaining a missing configured path', async () => {
  const choose = vi.fn();
  server.use(http.get('/api/v1/printers/usb-cameras', () => HttpResponse.json({
    cameras: [{ device: '/dev/video2', name: 'Capture camera' }],
  })));
  render(<ExternalCameraUrlField cameraType="usb" value="/dev/video8" onUrlChange={choose} />);
  expect(await screen.findByText('USB camera /dev/video8 is not currently available.')).toBeInTheDocument();
  expect(screen.getByRole('textbox')).toHaveValue('/dev/video8');
  selectComboboxOption(screen.getByRole('combobox', { name: 'Choose a USB camera' }), 'Capture camera (/dev/video2)');
  expect(choose).toHaveBeenCalledWith('/dev/video2');
});

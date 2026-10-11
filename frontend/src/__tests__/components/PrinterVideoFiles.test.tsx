import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { FileManagerModal } from '../../components/FileManagerModal';
import { api } from '../../api/client';

const videos = [
  { name: 'video-c.mp4', path: '/ipcam/video-c.mp4', size: 300, is_directory: false },
  { name: 'folder', path: '/ipcam/folder', size: 0, is_directory: true },
  { name: 'video-a.mp4', path: '/ipcam/video-a.mp4', size: 100, is_directory: false },
  { name: 'video-b.avi', path: '/ipcam/video-b.avi', size: 200, is_directory: false },
];

function mount() {
  return render(<FileManagerModal printerId={1} printerName="Printer" onClose={vi.fn()} />);
}

describe('printer video files', () => {
  afterEach(() => vi.unstubAllGlobals());
  beforeEach(() => {
    vi.restoreAllMocks();
    server.use(
      http.get('/api/v1/printers/:id/files', () => HttpResponse.json({ files: videos })),
      http.get('/api/v1/printers/:id/storage', () => HttpResponse.json({})),
    );
  });

  it('offers video navigation and selects a contiguous range in the displayed sort order', async () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Videos' }));
    await screen.findByText('/ipcam');
    fireEvent.click(await screen.findByRole('checkbox', { name: 'video-a.mp4' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'video-c.mp4' }), { shiftKey: true });
    expect(screen.getByText('3 selected')).toBeInTheDocument();
    expect(screen.getAllByRole('checkbox', { checked: true })).toHaveLength(3);
    expect(screen.queryByRole('checkbox', { name: 'folder' })).not.toBeInTheDocument();
  });

  it('selects only visible filtered files and resets the range anchor after the filter changes', async () => {
    mount();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'video-a.mp4' }));
    fireEvent.change(screen.getByPlaceholderText('Filter files...'), { target: { value: 'video-c' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'video-c.mp4' }), { shiftKey: true });
    expect(screen.getByText('2 selected')).toBeInTheDocument();
  });

  it('downloads video ranges sequentially and keeps partial failures selected', async () => {
    const downloaded: string[] = [];
    vi.spyOn(api, 'downloadPrinterFile').mockImplementation((_printerId, path) => {
      downloaded.push(path);
      return {
        downloadId: path,
        cancel: vi.fn(),
        promise: path.endsWith('video-b.avi') ? Promise.reject(new Error('File not found')) : Promise.resolve(),
      };
    });
    const zip = vi.spyOn(api, 'downloadPrinterFilesAsZip');
    mount();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'video-a.mp4' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'video-c.mp4' }), { shiftKey: true });
    fireEvent.click(screen.getByRole('button', { name: 'Download (3)' }));
    await waitFor(() => expect(downloaded).toEqual(videos.filter(f => !f.is_directory).map(f => f.path).sort()));
    expect(zip).not.toHaveBeenCalled();
    expect(await screen.findByRole('alert', { name: 'Error', exact: true })).toHaveTextContent('video-b.avi');
    expect(screen.getByRole('checkbox', { name: 'video-b.avi' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'video-a.mp4' })).not.toBeChecked();
  });
  it('cancels the active video and leaves unfinished files selected', async () => {
    let rejectDownload: (error: Error) => void = () => {};
    const promise = new Promise<void>((_resolve, reject) => { rejectDownload = reject; });
    const cancel = vi.fn(() => rejectDownload(new DOMException('Cancelled', 'AbortError')));
    const download = vi.spyOn(api, 'downloadPrinterFile').mockReturnValue({ downloadId: 'cancel-test', promise, cancel });
    mount();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'video-a.mp4' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'video-c.mp4' }), { shiftKey: true });
    fireEvent.click(screen.getByRole('button', { name: 'Download (3)' }));
    await screen.findByRole('button', { name: 'Cancel' });
    window.dispatchEvent(new CustomEvent('printops:file-download-progress', {
      detail: { download_id: 'cancel-test', bytes_transferred: 50, total_bytes: 100 },
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument());
    expect(cancel).toHaveBeenCalledOnce();
    expect(download).toHaveBeenCalledOnce();
    expect(screen.getByText('3 selected')).toBeInTheDocument();
  });

  it('does not start a folder download if the manager closes while opening the destination', async () => {
    let resolveFile: (file: FileSystemFileHandle) => void = () => {};
    const file = new Promise<FileSystemFileHandle>(resolve => { resolveFile = resolve; });
    const getFileHandle = vi.fn().mockReturnValue(file);
    vi.stubGlobal('showDirectoryPicker', vi.fn().mockResolvedValue({ getFileHandle }));
    const download = vi.spyOn(api, 'downloadPrinterFile');
    const abort = vi.fn();
    const view = mount();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'video-a.mp4' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save videos to folder' }));
    await waitFor(() => expect(getFileHandle).toHaveBeenCalledOnce());
    view.unmount();
    resolveFile({ createWritable: vi.fn().mockResolvedValue({ abort }) } as unknown as FileSystemFileHandle);
    await waitFor(() => expect(abort).toHaveBeenCalledOnce());
    expect(download).not.toHaveBeenCalled();
  });

});

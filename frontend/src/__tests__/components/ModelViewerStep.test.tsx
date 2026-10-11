import { afterEach, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import * as THREE from 'three';
const mocks = vi.hoisted(() => ({ load:vi.fn(), scene:null as import('three').Scene | null }));
vi.mock('../../utils/stepPreview', () => ({ loadStepPreview:mocks.load }));
vi.mock('three', async importOriginal => {
  const actual = await importOriginal<typeof import('three')>();
  return {...actual, WebGLRenderer:class {
    domElement=document.createElement('canvas'); setSize() {} setPixelRatio() {} dispose() {}
    render(scene: import('three').Scene) { mocks.scene=scene; }
  }};
});
vi.mock('three/examples/jsm/controls/OrbitControls.js', () => ({OrbitControls:class {
  target = new THREE.Vector3(); update() {} dispose() {}
}}));
import { ModelViewer } from '../../components/ModelViewer';
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });
it('renders STEP mesh buffers using the existing build-plate framing', async () => {
  mocks.load.mockResolvedValue([{positions:new Float32Array([0,0,0,1,0,0,0,1,0]),indices:new Uint32Array([0,1,2])}]);
  render(<ModelViewer url="/part.step" fileType="step" />);
  await waitFor(() => expect(screen.queryByText(/Converting STEP/)).not.toBeInTheDocument());
  const group=mocks.scene!.children.find(child => child instanceof THREE.Group) as THREE.Group;
  expect(group.children).toHaveLength(1);
  const mesh=group.children[0] as THREE.Mesh;
  expect(mesh.geometry.getIndex()!.count).toBe(3);
  expect(mesh.geometry.getAttribute('position').count).toBe(3);
  expect(group.position.x).toBe(127.5);
});
it('counts conversion seconds and cancels when the viewer unmounts', () => {
  vi.useFakeTimers(); mocks.load.mockImplementation(() => new Promise(() => {}));
  const {unmount}=render(<ModelViewer url="/part.step" fileType="stp" />);
  expect(screen.getByText('Converting STEP model… 0 s')).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(3000));
  expect(screen.getByText('Converting STEP model… 3 s')).toBeInTheDocument();
  const signal=mocks.load.mock.calls[0][2] as AbortSignal;
  expect(signal.aborted).toBe(false); unmount(); expect(signal.aborted).toBe(true);
});
it('shows STEP conversion progress when the format is inferred from its URL', () => {
  mocks.load.mockImplementation(() => new Promise(() => {}));
  render(<ModelViewer url="/part.step" />);
  expect(screen.getByText('Converting STEP model… 0 s')).toBeInTheDocument();
});

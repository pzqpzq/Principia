import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DiscoveryActivityDialog } from './DiscoveryActivityDialog';
import { FocusDialog } from './FocusDialog';
import { dialogDimensions } from './DialogResizeHandle';

afterEach(cleanup);
it('shows the saved run scope, models and measured size; closing never stops discovery', () => {
  const stop = vi.fn(), close = vi.fn();
  render(<DiscoveryActivityDialog study={{state: 'running', phase: 'analyze', source_ids: ['source:run'], request: { objective: 'Explain dose response', reasoning_model: 'deepseek-test', vision_model: 'vision-test', budget: 'fast' }, coverage: { total_bytes: 3072, asset_count: 2, sources: [{source_id: 'source:run', total_bytes: 3072, asset_count: 2}] } }} sources={[{source_id: 'source:run', display_name: 'Run data'}, {source_id: 'source:unrelated', display_name: 'Unrelated data'}]} counts={{tests: 7}} cancelling={false} onStop={stop} onClose={close} onResults={vi.fn()} />);
  expect(screen.getByText('deepseek-test')).not.toBeNull();
  expect(screen.getByText('vision-test')).not.toBeNull();
  expect(screen.getByText('Run data')).not.toBeNull();
  expect(screen.queryByText('Unrelated data')).toBeNull();
  expect(screen.getByText('2 files · 3 KiB')).not.toBeNull();
  fireEvent.click(screen.getByLabelText('Close discovery activity'));
  expect(close).toHaveBeenCalledOnce(); expect(stop).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Stop discovery'})); expect(stop).toHaveBeenCalledOnce();
});
it('keeps a small screen dialog reachable after keyboard resizing and reset', () => {
  expect(dialogDimensions(1400, 1000, 390, 640)).toEqual({width: 366, height: 616});
  const view = render(<FocusDialog resizable title="Principle details" onClose={vi.fn()}><p>Scientific information</p></FocusDialog>);
  const frame = screen.getByRole('dialog'), handle = within(frame).getByLabelText('Resize dialog');
  vi.spyOn(frame, 'getBoundingClientRect').mockReturnValue({width: 500, height: 500} as DOMRect);
  fireEvent.keyDown(handle, {key: 'ArrowRight'}); expect(frame.style.width).toBe('520px');
  fireEvent.keyDown(handle, {key: 'ArrowDown'}); expect(frame.style.height).toBe('520px');
  fireEvent.keyDown(handle, {key: 'Home'}); expect(frame.style.width).toBe(''); expect(frame.style.height).toBe('');
  view.unmount();
});

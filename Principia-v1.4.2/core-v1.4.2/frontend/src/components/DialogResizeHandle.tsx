import { useEffect, useRef, type PointerEvent, type KeyboardEvent } from 'react';

export function dialogDimensions(width: number, height: number, viewportWidth: number, viewportHeight: number) {
  const maxWidth = Math.max(1, viewportWidth - 24), maxHeight = Math.max(1, viewportHeight - 24);
  return { width: Math.max(Math.min(340, maxWidth), Math.min(width, maxWidth)), height: Math.max(Math.min(260, maxHeight), Math.min(height, maxHeight)) };
}

/** Resize the dialog frame, so headers and scroll regions share the same bounds. */
export function DialogResizeHandle() {
  const ref = useRef<HTMLButtonElement>(null);
  const drag = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const resize = (width: number, height: number) => {
    const frame = ref.current?.closest<HTMLElement>('[role="dialog"]');
    if (!frame) return;
    const size = dialogDimensions(width, height, window.innerWidth, window.innerHeight);
    frame.style.width = `${size.width}px`; frame.style.height = `${size.height}px`;
    frame.dataset.resized = 'true';
  };
  useEffect(() => {
    const constrain = () => { const frame = ref.current?.closest<HTMLElement>('[role="dialog"]'); if (frame?.dataset.resized) { const rect = frame.getBoundingClientRect(); resize(rect.width, rect.height); } };
    window.addEventListener('resize', constrain);
    return () => window.removeEventListener('resize', constrain);
  }, []);
  const start = (event: PointerEvent<HTMLButtonElement>) => {
    const frame = event.currentTarget.closest('[role="dialog"]'); if (!frame) return;
    const rect = frame.getBoundingClientRect(); drag.current = { x: event.clientX, y: event.clientY, width: rect.width, height: rect.height };
    event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
  };
  const keyboard = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home'].includes(event.key)) return;
    event.preventDefault(); const frame = event.currentTarget.closest<HTMLElement>('[role="dialog"]'); if (!frame) return;
    if (event.key === 'Home') { frame.style.removeProperty('width'); frame.style.removeProperty('height'); delete frame.dataset.resized; return; }
    const rect = frame.getBoundingClientRect(), step = event.shiftKey ? 80 : 20;
    resize(rect.width + (event.key === 'ArrowRight' ? step : event.key === 'ArrowLeft' ? -step : 0), rect.height + (event.key === 'ArrowDown' ? step : event.key === 'ArrowUp' ? -step : 0));
  };
  return <button ref={ref} type="button" className="dialog-resize-handle" aria-label="Resize dialog" title="Drag to resize · arrow keys adjust size · Home resets" onPointerDown={start}
    onPointerMove={event => { if (drag.current) resize(drag.current.width + 2 * (event.clientX - drag.current.x), drag.current.height + 2 * (event.clientY - drag.current.y)); }}
    onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }} onKeyDown={keyboard}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 16 10-10M11 16l5-5" /></svg></button>;
}

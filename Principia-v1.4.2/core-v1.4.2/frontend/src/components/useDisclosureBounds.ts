import { useLayoutEffect, type RefObject } from 'react';

/** Measure the anchor rather than guessing toolbar height, including after folders are added. */
export function useDisclosureBounds(ref: RefObject<HTMLDetailsElement | null>) {
  useLayoutEffect(() => {
    const details = ref.current, summary = details?.querySelector('summary');
    if (!details || !summary) return;
    const update = () => {
      if (!details.open) return;
      const rect = summary.getBoundingClientRect(), anchor = details.getBoundingClientRect();
      const workspace = details.closest(".research-workspace")?.getBoundingClientRect();
      const minimumLeft = Math.max(12, (workspace?.left || 0) + 12);
      const width = Math.min(480, window.innerWidth - minimumLeft - 12);
      const top = Math.min(rect.bottom + 8, window.innerHeight - 100);
      details.style.setProperty('--options-left', `${Math.max(minimumLeft, Math.min(rect.right - width, window.innerWidth - width - 12)) - anchor.left}px`);
      details.style.setProperty('--options-top', `${Math.max(12, top) - anchor.top}px`);
      details.style.setProperty('--options-width', `${width}px`);
      details.style.setProperty('--options-height', `${Math.max(80, window.innerHeight - top - 12)}px`);
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update); observer?.observe(summary); observer?.observe(details.parentElement || details);
    details.addEventListener('toggle', update); window.addEventListener('resize', update); window.addEventListener('scroll', update, true); update();
    return () => { observer?.disconnect(); details.removeEventListener('toggle', update); window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true); };
  }, [ref]);
}

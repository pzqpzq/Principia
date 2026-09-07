import { useEffect, useRef, type ReactNode } from "react";
import { DialogResizeHandle } from "./DialogResizeHandle";
import { createPortal } from "react-dom";

export function trapDialogFocus(event: React.KeyboardEvent<HTMLElement>) {
  if (event.key !== "Tab") return;
  const elements = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href], [tabindex="0"]',
  ));
  const first = elements[0];
  const last = elements.at(-1);
  if (!first) { event.preventDefault(); return; }
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

export function FocusDialog({ title, children, onClose, returnFocus, resizable = false }: { title: string; children: ReactNode; onClose: () => void; returnFocus?: HTMLElement | null; resizable?: boolean }) {
  const ref = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const background = Array.from(document.body.children).filter((element): element is HTMLElement => element instanceof HTMLElement && !element.contains(ref.current));
    const originalInert = background.map((element) => element.inert);
    background.forEach((element) => { element.inert = true; });
    ref.current?.querySelector<HTMLElement>('input, button, [tabindex="0"]')?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
    };
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("keydown", escape); background.forEach((element, index) => { element.inert = originalInert[index]; }); (returnFocus?.isConnected ? returnFocus : previous)?.focus(); };
  }, []);
  return createPortal(
    <div className="project-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section ref={ref} role="dialog" aria-modal="true" aria-label={title} className={`project-dialog${resizable ? " resizable-dialog" : ""}`} onKeyDown={trapDialogFocus}>
        <h2>{title}</h2>{children}{resizable ? <DialogResizeHandle /> : null}
      </section>
    </div>, document.body,
  );
}

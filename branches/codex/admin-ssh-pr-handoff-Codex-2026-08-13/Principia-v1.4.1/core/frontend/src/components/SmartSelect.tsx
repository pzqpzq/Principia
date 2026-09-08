import { useEffect, useMemo, useRef, useState } from "react";

export type SmartSelectOption = {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
};

type SmartSelectProps = {
  value: string;
  options: SmartSelectOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  placeholder?: string;
  disabled?: boolean;
  searchable?: boolean;
};

export function SmartSelect({
  value,
  options,
  onChange,
  ariaLabel,
  placeholder = "Choose…",
  disabled = false,
  searchable,
}: SmartSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const search = searchable ?? options.length > 6;
  const selected = options.find((option) => option.value === value);
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return options;
    return options.filter((option) => `${option.label} ${option.description ?? ""}`.toLocaleLowerCase().includes(needle));
  }, [options, query]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return <div className={`smart-select ${open ? "open" : ""}`} ref={root}>
    <button
      type="button"
      className="smart-select-trigger"
      aria-label={ariaLabel}
      aria-haspopup="listbox"
      aria-expanded={open}
      disabled={disabled}
      onClick={() => { setOpen((current) => !current); setQuery(""); }}
      onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}
    >
      <span><strong>{selected?.label ?? placeholder}</strong>{selected?.description ? <small>{selected.description}</small> : null}</span>
      <span aria-hidden="true">⌄</span>
    </button>
    {open ? <div className="smart-select-popover">
      {search ? <input autoFocus aria-label={`Search ${ariaLabel}`} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Type to filter…" onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }} /> : null}
      <div className="smart-select-options" role="listbox" aria-label={ariaLabel}>
        {filtered.map((option) => <button
          type="button"
          role="option"
          aria-selected={option.value === value}
          disabled={option.disabled}
          key={option.value || "__empty__"}
          onClick={() => { onChange(option.value); setOpen(false); setQuery(""); }}
        ><span><strong>{option.label}</strong>{option.description ? <small>{option.description}</small> : null}</span>{option.value === value ? <span aria-hidden="true">✓</span> : null}</button>)}
        {!filtered.length ? <p className="smart-select-empty">No matching options</p> : null}
      </div>
    </div> : null}
  </div>;
}

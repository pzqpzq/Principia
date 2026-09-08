import { useEffect, useRef, useState } from "react";

type CloudStatus = Record<string, unknown>;

const numberValue = (value: unknown): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

const textValue = (value: unknown): string =>
  typeof value === "string" ? value : "";

const countLabel = (value: unknown): string =>
  numberValue(value).toLocaleString();

const dateLabel = (value: unknown): string => {
  const raw = textValue(value);
  if (!raw) return "Not available";
  const date = new Date(raw);
  return Number.isNaN(date.valueOf())
    ? raw
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
};

export function CloudStatusControl({
  status,
  fetching = false,
  refreshing = false,
  onRefresh,
}: {
  status: CloudStatus;
  fetching?: boolean;
  refreshing?: boolean;
  onRefresh: () => void;
}) {
  const [open, setOpen] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);
  const total =
    status.total_principle_count ?? status.principle_count ?? 0;
  const available = Boolean(status.available);

  useEffect(() => {
    if (!open) return;
    closeButton.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="research-cloud-state"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`${countLabel(total)} Principles ready, open Cloud status`}
        onClick={() => setOpen(true)}
      >
        <span
          className={`status-dot ${available ? "online" : "warning"}`}
          aria-hidden="true"
        />
        <strong>{countLabel(total)}</strong>
        <small>Principles ready</small>
      </button>

      {open ? (
        <div
          className="cloud-status-backdrop"
          role="presentation"
          onPointerDown={(event) => {
            if (event.target === event.currentTarget) setOpen(false);
          }}
        >
          <section
            className="cloud-status-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cloud-status-title"
          >
            <header>
              <div>
                <span className="eyebrow">Live Cloud status</span>
                <h2 id="cloud-status-title">Global Principles Cloud</h2>
                <p>
                  {available
                    ? "This verified snapshot powers Global search and the living map."
                    : "No verified Cloud snapshot is active in this workspace."}
                </p>
              </div>
              <button
                ref={closeButton}
                type="button"
                className="cloud-status-close"
                aria-label="Close Cloud status"
                onClick={() => setOpen(false)}
              >
                ×
              </button>
            </header>

            <div className="cloud-status-total">
              <span className={`status-dot ${available ? "online" : "warning"}`} />
              <div>
                <strong>{countLabel(total)}</strong>
                <small>active Principles in the unified Cloud</small>
              </div>
              {fetching || refreshing || Boolean(status.syncing) ? (
                <span className="cloud-live-indicator">Updating…</span>
              ) : (
                <span className="cloud-live-indicator ready">Live</span>
              )}
            </div>

            <dl className="cloud-status-metrics">
              <div>
                <dt>Literature Principles</dt>
                <dd>
                  {countLabel(
                    status.literature_principle_count ?? status.principle_count,
                  )}
                </dd>
              </div>
              <div>
                <dt>Meta-Principles</dt>
                <dd>{countLabel(status.meta_principle_count)}</dd>
              </div>
              <div>
                <dt>Scientific works</dt>
                <dd>{countLabel(status.work_count)}</dd>
              </div>
              <div>
                <dt>Provenance links</dt>
                <dd>{countLabel(status.principle_work_count)}</dd>
              </div>
              <div>
                <dt>Principle relations</dt>
                <dd>{countLabel(status.relation_count)}</dd>
              </div>
              <div>
                <dt>Foundation links</dt>
                <dd>{countLabel(status.foundation_link_count)}</dd>
              </div>
              <div>
                <dt>Scientific areas</dt>
                <dd>{countLabel(status.area_count)}</dd>
              </div>
              <div>
                <dt>Snapshot size</dt>
                <dd>
                  {numberValue(status.snapshot_bytes)
                    ? `${(numberValue(status.snapshot_bytes) / 1_048_576).toFixed(1)} MiB`
                    : "—"}
                </dd>
              </div>
            </dl>

            <div className="cloud-status-provenance">
              <div>
                <span>Verified release</span>
                <strong>{textValue(status.release_id) || "Not installed"}</strong>
              </div>
              <div>
                <span>Cloud updated</span>
                <strong>{dateLabel(status.updated_at)}</strong>
              </div>
              <div>
                <span>Embedding contract</span>
                <strong>{textValue(status.embedding_contract) || "FTS fallback"}</strong>
              </div>
            </div>

            {textValue(status.last_error) ? (
              <p className="cloud-status-warning" role="status">
                The last update check did not complete. The previous verified
                snapshot remains active and searchable.
              </p>
            ) : null}

            <footer>
              <small>
                Counts refresh automatically while Principia is open. Snapshot
                activation is atomic, so searches never see a partial update.
              </small>
              <button
                type="button"
                onClick={onRefresh}
                disabled={refreshing || Boolean(status.syncing)}
              >
                {refreshing || Boolean(status.syncing)
                  ? "Checking…"
                  : "Check for updates"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}

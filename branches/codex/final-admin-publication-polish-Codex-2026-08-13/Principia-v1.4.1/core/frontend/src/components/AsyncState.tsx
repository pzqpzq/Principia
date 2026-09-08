import type { ReactNode } from "react";
import { ApiError } from "../api/client";

export function LoadingState({ label = "Loading Principia…" }: { label?: string }) {
  return (
    <div className="state-card" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <p>Reading verified local state.</p>
      </div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-glyph" aria-hidden="true">◇</span>
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const apiError = error instanceof ApiError ? error : new ApiError(error);
  return (
    <div className={`state-card error ${apiError.retryable ? "retryable" : ""}`} role="alert">
      <span className="status-dot danger" aria-hidden="true" />
      <div>
        <strong>{apiError.message}</strong>
        <p>
          {apiError.category} · Request {apiError.requestId || "not available"}
        </p>
        {retry && apiError.retryable ? <button onClick={retry}>Retry</button> : null}
      </div>
    </div>
  );
}

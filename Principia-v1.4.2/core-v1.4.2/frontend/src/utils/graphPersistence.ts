import { api, ApiError, dataOrThrow } from "../api/client";

export const retryableGraphError = (error: unknown): boolean =>
  error instanceof TypeError || (error instanceof ApiError && error.retryable);
export class QueuedGraphSave extends Error {
  constructor() { super("Saved on this device. The map change will sync when the workspace reconnects."); }
}
export const graphSaveMessage = (error: unknown): string => error instanceof QueuedGraphSave
  ? error.message
  : `The map change could not be saved. ${error instanceof Error ? error.message : "Please try again."}`;

export async function persistGraphOperations(
  sessionId: string,
  operations: Array<Record<string, unknown>>,
  revisions: Map<string, number>,
): Promise<void> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const expected = revisions.get(sessionId) ?? 0;
    try {
      const receipt = dataOrThrow(await api.PATCH("/api/v1/research-sessions/{session_id}/graph", {
        params: { path: { session_id: sessionId } },
        body: { expected_revision: expected, operations },
      })) as Record<string, unknown>;
      revisions.set(sessionId, Number(receipt.revision ?? expected + 1));
      return;
    } catch (error) {
      if (attempt === 0 && error instanceof ApiError && error.category === "integrity" && error.message.includes("graph revision conflict")) {
        const graph = dataOrThrow(await api.GET("/api/v1/research-sessions/{session_id}/graph", {
          params: { path: { session_id: sessionId } },
        })) as Record<string, unknown>;
        revisions.set(sessionId, Number(graph.revision ?? 0));
        continue;
      }
      throw error;
    }
  }
}

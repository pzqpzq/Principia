import createClient from "openapi-fetch";
import type { paths } from "./schema";

const session =
  document.querySelector<HTMLMetaElement>('meta[name="principia-session"]')?.content ?? "";

export const api = createClient<paths>({
  baseUrl: "",
  headers: session ? { "X-Principia-Session": session } : undefined,
});

export class ApiError extends Error {
  requestId: string;
  retryable: boolean;
  category: string;

  constructor(error: unknown) {
    const raw = error as {
      error?: { message?: string; request_id?: string; retryable?: boolean; category?: string };
      message?: string; request_id?: string; retryable?: boolean; category?: string;
    };
    const body = raw?.error ?? raw;
    super(body?.message ?? "Principia could not complete the request.");
    this.name = "ApiError";
    this.requestId = body?.request_id ?? "";
    this.retryable = Boolean(body?.retryable);
    this.category = body?.category ?? "runtime";
  }
}

export function dataOrThrow<T>(result: { data?: T; error?: unknown }): T {
  if (result.error) throw new ApiError(result.error);
  if (result.data === undefined) throw new ApiError(undefined);
  return result.data;
}

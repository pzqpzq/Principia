import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ErrorState } from "./AsyncState";

afterEach(cleanup);

describe("ErrorState", () => {
  it("shows actionable persisted job errors instead of replacing them with a generic message", () => {
    render(<ErrorState error={{
      code: "provider_not_configured",
      category: "provider",
      message: "SiliconFlow is not configured in this server process.",
      retryable: true,
      request_id: "request-fixture",
    }} />);
    expect(screen.getByRole("alert").textContent).toContain("SiliconFlow is not configured");
    expect(screen.getByRole("alert").textContent).toContain("provider");
    expect(screen.getByRole("alert").textContent).toContain("request-fixture");
  });
});


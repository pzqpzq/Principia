import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchRunStatus } from "./ResearchRunStatus";

afterEach(() => { cleanup(); vi.useRealTimers(); });
describe("durable discovery status", () => {
  it("distinguishes a silent worker from live progress without inventing a percentage", () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date("2026-09-06T04:00:00Z"));
    render(<ResearchRunStatus kind="discovery" state="running" phase="synthesize"
      startedAt="2026-09-06T03:58:00Z" lastActivityAt="2026-09-06T03:58:40Z" />);
    expect(screen.getByText(/No new worker update for/)).not.toBeNull();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBeNull();
    expect(screen.getByText("Elapsed 2 min 00 sec")).not.toBeNull();
  });
  it("presents terminal failure and cancellation without a running spinner", () => {
    render(<ResearchRunStatus kind="discovery" state="failed" message="The provider rejected the request." onResults={() => {}} />);
    expect(screen.getByText("Discovery could not finish")).not.toBeNull();
    expect(screen.getByText("The provider rejected the request.")).not.toBeNull();
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("View results")).not.toBeNull();
  });
});

it("separates activity navigation from an explicitly named stop action", () => {
  const activity = vi.fn(), stop = vi.fn(), results = vi.fn();
  render(<ResearchRunStatus kind="discovery" state="running" onActivity={activity} onCancel={stop} onResults={results} />);
  fireEvent.click(screen.getByText("View activity"));
  expect(activity).toHaveBeenCalledOnce(); expect(stop).not.toHaveBeenCalled(); expect(results).not.toHaveBeenCalled();
  expect(screen.queryByText("Cancel")).toBeNull();
  fireEvent.click(screen.getByText("Stop discovery")); expect(stop).toHaveBeenCalledOnce();
});

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DataDiscoveryPhases } from "./DataDiscoveryPhases";
afterEach(cleanup);

describe("DataDiscoveryPhases", () => {
  it.each(["failed", "cancelled", "interrupted"])("keeps unexecuted phases pending after %s", (runState) => {
    const view = render(<DataDiscoveryPhases phase="analyze" complete runState={runState} />);
    expect(view.container.querySelectorAll("li.done")).toHaveLength(2);
    expect(view.container.querySelectorAll("li.stopped")).toHaveLength(1);
    expect(view.container.querySelectorAll("li.pending")).toHaveLength(2);
  });
  it("shows the five concise phases and exposes the current step accessibly", () => {
    render(<DataDiscoveryPhases phase="challenge" />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText("challenge").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
  });

  it("uses text states in addition to color", () => {
    const view = render(<DataDiscoveryPhases phase="analyze" />);
    expect(view.container.querySelectorAll("li.done")).toHaveLength(2);
    expect(view.container.querySelectorAll("li.active")).toHaveLength(1);
    expect(view.container.querySelectorAll("li.pending")).toHaveLength(2);
    expect(view.container.textContent).toContain("active");
  });

  it("marks every phase complete when a study reaches a terminal state", () => {
    const view = render(<DataDiscoveryPhases phase="synthesize" complete />);
    expect(view.container.querySelectorAll("li.done")).toHaveLength(5);
    expect(view.container.querySelectorAll("li.active")).toHaveLength(0);
    expect(view.container.querySelector("[aria-current='step']")).toBeNull();
  });
});

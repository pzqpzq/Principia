import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CloudStatusControl } from "./CloudStatusControl";

afterEach(cleanup);

describe("CloudStatusControl", () => {
  const status = {
    available: true,
    release_id: "20260823-example",
    updated_at: "2026-08-23T02:00:00Z",
    total_principle_count: 1245,
    literature_principle_count: 840,
    meta_principle_count: 405,
    work_count: 991,
    principle_work_count: 2342,
    relation_count: 468,
    foundation_link_count: 186,
    area_count: 18,
    snapshot_bytes: 4_509_722,
    embedding_contract: "qwen3-embedding-4b-1024-v1",
  };

  it("opens a human-readable live Cloud summary and refreshes on demand", () => {
    const refresh = vi.fn();
    render(<CloudStatusControl status={status} onRefresh={refresh} />);

    const trigger = screen.getByRole("button", {
      name: /1,245 principles ready, open cloud status/i,
    });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(
      screen.getByRole("dialog", { name: "Global Principles Cloud" }),
    ).toBeVisible();
    expect(screen.getByText("840")).toBeVisible();
    expect(screen.getByText("405")).toBeVisible();
    expect(screen.getByText("2,342")).toBeVisible();
    expect(screen.getByText("20260823-example")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Check for updates" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("closes with Escape", () => {
    render(<CloudStatusControl status={status} onRefresh={() => undefined} />);
    fireEvent.click(
      screen.getByRole("button", { name: /1,245 principles ready/i }),
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

import { createElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { components } from "../api/schema";
import { Shell, jobDestination } from "./Shell";

const getMock = vi.hoisted(() => vi.fn());
const deleteMock = vi.hoisted(() => vi.fn());
afterEach(cleanup);

vi.mock("../api/client", () => ({
  api: {
    GET: getMock,
    POST: vi.fn(),
    PATCH: vi.fn(),
    DELETE: deleteMock,
  },
  dataOrThrow: (result: { data?: unknown; error?: unknown }) => {
    if (result.error) throw result.error;
    return result.data;
  },
}));

type Job = components["schemas"]["JobRecord"];

const job = (kind: string, checkpoint: Record<string, unknown>): Job => ({
  job_id: "job:test",
  kind,
  state: "running",
  stage: "extracting",
  progress: 0.25,
  provider: "siliconflow",
  model: "fixture",
  checkpoint,
  created_at: "2026-08-20T00:00:00Z",
  updated_at: "2026-08-20T00:00:00Z",
  completed_units: 1,
  total_units: 4,
  elapsed_seconds: 10,
  last_activity_at: "2026-08-20T00:00:00Z",
  status_message: "running",
}) as Job;

describe("Activity Center destinations", () => {
  it("opens a goal run in its durable research session", () => {
    expect(jobDestination(job("research_goal_run", { run_id: "goalrun:one", session_id: "session:robotics" })).path)
      .toBe("/research/session%3Arobotics");
  });

  it("opens a completed research goal in its reproducible Results membership", () => {
    expect(jobDestination(job("research_goal_run", { run_id: "goalrun:one" })).path)
      .toBe("/map?scope=combined&goal_run=goalrun%3Aone");
  });
});

describe("mobile project navigation", () => {
  it("keeps unfinished and failed projects reachable before they have findings", async () => {
    const states = ["queued", "running", "paused", "failed", "interrupted", "data_insufficient"];
    getMock.mockImplementation(async (path: string) => ({data: path === "/api/v1/research-sessions" ? {items: [...states, "cancelled"].map(state => ({session_id: `session:${state}`, display_title: `Experiment ${state}`, state, revision: 1, is_empty: true}))} : {}}));
    const client = new QueryClient({defaultOptions: {queries: {retry: false}}});
    render(createElement(QueryClientProvider, {client}, createElement(MemoryRouter, null, createElement(Shell))));
    const projects = screen.getByRole("region", {name: "Research sessions"});
    await within(projects).findByRole("button", {name: "Delete Experiment running"});
    expect(within(projects).getAllByRole("link")).toHaveLength(states.length);
    expect(within(projects).queryByRole("button", {name: "Delete Experiment cancelled"})).toBeNull();
    fireEvent.click(within(projects).getByRole("button", {name: "All"}));
    expect(within(projects).getAllByRole("link")).toHaveLength(states.length + 1);
    client.clear();
  });
  it("offers direct deletion with a revision-checked confirmation", async () => {
    getMock.mockImplementation(async (path: string) => ({data: path === "/api/v1/research-sessions" ? {items: [{session_id: "session:remove", display_title: "My experiment", state: "succeeded", revision: 7, is_empty: false}]} : {}}));
    deleteMock.mockResolvedValue({data: {deleted: true, artifact_cleanup_pending: 0}});
    const client = new QueryClient({defaultOptions: {queries: {retry: false}}});
    render(createElement(QueryClientProvider, {client}, createElement(MemoryRouter, null, createElement(Shell))));
    fireEvent.click(await screen.findByRole("button", {name: "Delete My experiment"}));
    const dialog = screen.getByRole("dialog", {name: "Delete project"});
    expect(deleteMock).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/Original source files and shared Principles are kept/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", {name: "Delete permanently"}));
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith("/api/v1/research-sessions/{session_id}", {params: {path: {session_id: "session:remove"}, query: {expected_revision: 7}}}));
  });
  it.each([21, 100])("keeps all %i projects reachable in Recent", async (count) => {
    getMock.mockImplementation(async (path: string) => ({ data: path === "/api/v1/research-sessions" ? { items: Array.from({length: count}, (_, index) => ({session_id: `session:${index}`, display_title: `Experiment ${index + 1}`, summary: "Independent dataset", state: "succeeded", revision: 1, is_empty: false})) } : path === "/api/v1/runtime" ? {version: "1.4.2"} : {} }));
    const client = new QueryClient({defaultOptions: {queries: {retry: false}}});
    render(createElement(QueryClientProvider, {client}, createElement(MemoryRouter, null, createElement(Shell))));
    const projects = screen.getByRole("region", {name: "Research sessions"});
    await within(projects).findByRole("link", {name: "Experiment 1. Independent dataset"});
    while (within(projects).queryByRole("button", {name: /^Show \d+ more$/})) {
      fireEvent.click(within(projects).getByRole("button", {name: /^Show \d+ more$/}));
    }
    expect(within(projects).getAllByRole("link")).toHaveLength(count);
    fireEvent.change(within(projects).getByRole("searchbox"), {target: {value: `Experiment ${count}`}});
    expect(within(projects).getAllByRole("link")).toHaveLength(1);
  });
  it("opens the canonical saved-session list from New Research", async () => {
    getMock.mockImplementation(async (path: string) => {
      if (path === "/api/v1/runtime")
        return { data: { demo_mode: false, version: "1.4.2" } };
      if (path === "/api/v1/cloud/status")
        return { data: { available: true, total_principle_count: 42 } };
      if (path === "/api/v1/providers")
        return {
          data: {
            profiles: [
              {
                provider_id: "siliconflow",
                label: "SiliconFlow",
                configured: true,
                default_model: "deepseek-ai/DeepSeek-V4-Flash",
                models: ["deepseek-ai/DeepSeek-V4-Flash"],
              },
            ],
          },
        };
      if (path === "/api/v1/research-sessions")
        return {
          data: {
            items: [
              {
                session_id: "session:coral",
                display_title: "Ocean coral heat stress",
                summary: "Global sea-surface anomaly discovery",
                state: "succeeded",
                revision: 1,
                is_empty: false,
              },
            ],
          },
        };
      throw new Error(`Unexpected request: ${path}`);
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      createElement(
        QueryClientProvider,
        { client: queryClient },
        createElement(
          MemoryRouter,
          { initialEntries: ["/research/new"] },
          createElement(
            Routes,
            null,
            createElement(
              Route,
              { path: "/", element: createElement(Shell) },
              createElement(Route, {
                path: "research/new",
                element: createElement("div", null, "New research workspace"),
              }),
              createElement(Route, {
                path: "research/:sessionId",
                element: createElement("div", null, "Saved research workspace"),
              }),
            ),
          ),
        ),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Projects" }));
    const projectDialog = await screen.findByRole("dialog", { name: "Projects" });
    expect(projectDialog).toBeTruthy();
    const projectLink = await within(projectDialog).findByRole("link", {
      name: "Ocean coral heat stress. Global sea-surface anomaly discovery",
    });
    expect(projectLink).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Search projects…")).toBe(
        document.activeElement,
      ),
    );

    fireEvent.click(projectLink);
    expect(await screen.findByText("Saved research workspace")).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Projects" })).toBeNull();
  });
});

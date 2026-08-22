import { describe, expect, it } from "vitest";
import type { components } from "../api/schema";
import { jobDestination } from "./Shell";

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

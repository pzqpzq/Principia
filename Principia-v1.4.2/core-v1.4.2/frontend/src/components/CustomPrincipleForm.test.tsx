import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CustomPrincipleForm } from "./CustomPrincipleForm";

afterEach(cleanup);
function completeForm() {
  for (const label of ["Title", "Claim", "Scope statement", "Falsifier", "Synthesis summary", "Reliability rationale", "Novelty rationale"])
    fireEvent.change(screen.getByLabelText(label), { target: { value: `${label} describes a bounded scientific hypothesis.` } });
  fireEvent.change(screen.getByLabelText("Area"), { target: { value: "test-area" } });
  fireEvent.change(screen.getByLabelText("Conditions"), { target: { value: "Controlled inputs\nMeasured response" } });
  for (const label of ["Reliability score", "Novelty score"])
    fireEvent.change(screen.getByLabelText(label), { target: { value: "70" } });
}

it("submits the full proposal without parent selection and prevents duplicate saves", async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  render(<CustomPrincipleForm onSave={save} />);
  completeForm();
  expect(screen.getByRole("button", { name: "Save locally & add to graph" }).hasAttribute("disabled")).toBe(false);
  fireEvent.submit(screen.getByRole("button", { name: "Save locally & add to graph" }).closest("form")!);
  await screen.findByText("Custom Principle saved locally and added to the graph.");
  expect(save).toHaveBeenCalledTimes(1);
  expect(save.mock.calls[0][0]).toMatchObject({ area: "test-area", conditions: ["Controlled inputs", "Measured response"],
    exclusions: [], assumptions: [], contributing_principle_ids: [], derivation_level: "direct_composition",
    reliability_score: 70, novelty_score: 70 });
  expect(Object.keys(save.mock.calls[0][0])).toHaveLength(15);
  expect(screen.getByRole("button", { name: "Saved locally and added" }).closest("fieldset")?.disabled).toBe(true);
});

it("enforces list limits and retains input when save fails", async () => {
  const save = vi.fn().mockRejectedValue(new Error("Save unavailable"));
  render(<CustomPrincipleForm onSave={save} />);
  completeForm();
  fireEvent.change(screen.getByLabelText("Assumptions"), { target: { value: Array(13).fill("Assumption").join("\n") } });
  const form = screen.getByRole("button", { name: "Save locally & add to graph" }).closest("form")!;
  fireEvent.submit(form);
  expect(await screen.findByText("Assumptions may contain at most 12 entries.")).not.toBeNull();
  expect(save).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Assumptions"), { target: { value: "Controlled observations" } });
  fireEvent.submit(form);
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Save unavailable"));
  expect((screen.getByLabelText("Area") as HTMLInputElement).value).toBe("test-area");
  expect(screen.getByRole("button", { name: "Save locally & add to graph" }).hasAttribute("disabled")).toBe(false);
});

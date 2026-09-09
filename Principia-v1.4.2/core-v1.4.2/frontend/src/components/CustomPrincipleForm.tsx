import { useState } from "react";
import type { components } from "../api/schema";
import { ErrorState } from "./AsyncState";

type Proposal = components["schemas"]["CustomPrincipleProposal"];
const fields = [
  ["title", "Title", 8, 180],
  ["area", "Area", 2, 63],
  ["claim", "Claim", 20, 2400],
  ["scope_statement", "Scope statement", 12, 1200],
  ["falsifier", "Falsifier", 12, 1200],
  ["synthesis_summary", "Synthesis summary", 20, 1600],
  ["reliability_rationale", "Reliability rationale", 20, 1200],
  ["novelty_rationale", "Novelty rationale", 20, 1200],
] as const;
const lists = [["conditions", "Conditions"], ["exclusions", "Exclusions"], ["assumptions", "Assumptions"]] as const;
const levels: Array<[Proposal["derivation_level"], string]> = [
  ["direct_composition", "Direct composition"],
  ["cross_context_generalization", "Cross-context generalization"],
  ["boundary_hypothesis", "Boundary hypothesis"],
  ["mechanistic_bridge", "Mechanistic bridge"],
];

export function CustomPrincipleForm({ onSave }: {
  onSave: (proposal: Proposal) => Promise<void>;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({ derivation_level: "direct_composition" });
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const update = (key: string, value: string) => {
    setDraft(current => ({ ...current, [key]: value }));
    setSaved(false);
    setError(null);
  };
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending || saved) return;
    setError(null);
    try {
      const values = Object.fromEntries(fields.map(([key, label, min, max]) => {
        const value = (draft[key] || "").trim();
        if (value.length < min || value.length > max) throw new Error(`${label} must contain ${min}–${max} characters.`);
        return [key, value];
      })) as Pick<Proposal, (typeof fields)[number][0]>;
      if (!/^[a-z0-9][a-z0-9-]+$/.test(values.area)) throw new Error("Area must use lowercase letters, numbers, and hyphens.");
      const arrayValues = Object.fromEntries(lists.map(([key, label]) => {
        const value = (draft[key] || "").split(/\r?\n/).map(line => line.trim()).filter(Boolean);
        if (value.length > 12) throw new Error(`${label} may contain at most 12 entries.`);
        return [key, value];
      }));
      const scores = Object.fromEntries(["reliability_score", "novelty_score"].map(key => {
        const value = Number(draft[key]);
        if (!draft[key]?.trim() || !Number.isFinite(value) || value < 0 || value > 100)
          throw new Error("Enter reliability and novelty scores between 0 and 100.");
        return [key, value];
      })) as Pick<Proposal, "reliability_score" | "novelty_score">;
      setPending(true);
      await onSave({ ...values, ...arrayValues, ...scores, derivation_level: draft.derivation_level as Proposal["derivation_level"],
        contributing_principle_ids: [] });
      setSaved(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(false);
    }
  };
  return <form className="custom-principle-form" onSubmit={submit}>
    <p>Use the same scientific fields as AI Polish. No parent Principle selection is required. Saved Principles remain unreviewed hypotheses.</p>
    <fieldset disabled={pending || saved}>
      {fields.map(([key, label, min, max]) => <label key={key}>
        <span>{label} <small>{min}–{max} characters</small></span>
        {key === "title" || key === "area"
          ? <input aria-label={label} required minLength={min} maxLength={max} pattern={key === "area" ? "[a-z0-9][a-z0-9-]+" : undefined} value={draft[key] || ""} onChange={event => update(key, event.target.value)} />
          : <textarea aria-label={label} required minLength={min} maxLength={max} rows={3} value={draft[key] || ""} onChange={event => update(key, event.target.value)} />}
      </label>)}
      <label><span>Derivation level</span><select aria-label="Derivation level" value={draft.derivation_level} onChange={event => update("derivation_level", event.target.value)}>
        {levels.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      {lists.map(([key, label]) => <label key={key}><span>{label} <small>Optional · one per line, up to 12</small></span>
        <textarea aria-label={label} rows={2} value={draft[key] || ""} onChange={event => update(key, event.target.value)} />
      </label>)}
      <div className="custom-principle-scores">{([["reliability_score", "Reliability score"], ["novelty_score", "Novelty score"]] as const).map(([key, label]) => <label key={key}><span>{label}</span>
        <input aria-label={label} type="number" required min={0} max={100} step="any" value={draft[key] || ""} onChange={event => update(key, event.target.value)} />
      </label>)}</div>
      <button className="primary full" type="submit">{pending ? "Saving…" : saved ? "Saved locally and added" : "Save locally & add to graph"}</button>
    </fieldset>
    {error ? <ErrorState error={error} /> : null}
    {saved ? <p className="inline-success" role="status">Custom Principle saved locally and added to the graph.</p> : null}
  </form>;
}
